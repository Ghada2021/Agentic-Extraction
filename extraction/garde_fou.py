"""Garde-fou final : rejette phrases, artefacts LLM et valeurs absentes du texte.
Code repris tel quel de pmv_api.py (aucune modification)."""
from ._base import *  # noqa: F401,F403


# ====================================================================
#          GARDE-FOU FINAL : pas de phrase ni d'invention dans les colonnes
# ====================================================================
# Une valeur qui ne ressemble pas à une réponse valide devient "Non trouvé".
_ARTEFACT_LLM_RE = re.compile(
    r"(?i)^\s*(?:assistant|user|system)\s*:?\s*$"            # rôle de chat seul
    r"|^\s*(?:assistant|user|system)\s*:"                     # "assistant: ..."
    r"|</?r>|```"
    r"|\b(?:what\s+you\s+can|depends\s+on|as\s+an\s+ai|i\s*'?\s*m\s+(?:sorry|unable|not\s+able)"
    r"|i\s+am\s+(?:sorry|unable)|i\s+can\s*'?\s*n?o?t\b|here\s+is|here\s*'\s*s|let\s+me\s+know|please\b)"
)
# Libellé d'un autre champ recopié dans la valeur ("Commune concernée : ...")
_LIBELLE_FUITE_RE = re.compile(
    r"(?i)\b(?:d[ée]partement|commune\s+concern[ée]e|date\s+de\s+signature|adresse\s+des\s+travaux"
    r"|longueur\s+g[ée]nie\s+civil|r[ée]f[ée]rence\s+bailleur)\s*:"
)
# Morceau de phrase d'arrêté, jamais une valeur de champ court
_PHRASE_RE = re.compile(
    r"(?i)\b(?:est\s+charg[ée]|sont\s+charg[ée]|doit\b|doivent\b|peuvent\b|pr[ée]sent\s+arr[êe]t"
    r"|pr[ée]sente\s+d[ée]cision|ci-apr[èe]s|consid[ée]r[ée]|par\s+d[ée]l[ée]gation|pour\s+le\s+pr[ée]sident"
    r"|co-?signataires?|instruction)\b"
)
_LONGUEUR_MAX = {
    "Nom Bailleur": 80, "Commune concernée": 150, "Référence bailleur": 60,
    "Partenaire cession": 80, "Date de signature": 40,
    "Date de debut d'autorisation": 40, "Date de fin d'autorisation": 40,
    "Durée de l'autorisation": 80, "Longueur génie civil": 80, "Nbr de chambres": 40,
    "Adresse des travaux": 300,
}
_COLONNES_LIBRES = {"Type", "Safix"}
# Texte libre : on ne contrôle que les artefacts LLM et le bloc de signature
_COLONNES_TEXTE_LONG = {"Modalités de renouvellement", "Modalités de résiliation"}
_BLOC_SIGNATURE_RE = re.compile(
    r"(?i)\b(?:pour\s+le\s+pr[ée]sident|par\s+d[ée]l[ée]gation|le\s+vice-?pr[ée]sident"
    r"|co-?signataires?|fait\s+(?:à|a)\s+\w+.{0,60}\ble\s+\d)"
)
# Ces champs doivent se retrouver mot pour mot dans le texte (hors accents/ponctuation)
_COLONNES_ANCREES = ["Nom Bailleur", "Commune concernée", "Référence bailleur"]
_MOTS_MAX_PAR_PARTIE = {"Nom Bailleur": 10, "Commune concernée": 6}

# mois en chiffres ou mot (même bruité par l'OCR : 'MA1', '0CT') ; validé ensuite
_MOIS_RE = r"(?:\d{1,2}|[0-9]?[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9]{1,9}\.?)"
_DATE_RE = rf"(\d{{1,2}}(?:\s?\d)?(?:er)?\s*[/.\-\s]\s*{_MOIS_RE}\s*[/.\-\s]\s*\d{{2,4}})"
_SIGNATURE_RES = [
    # "le" peut être collé à la date par l'OCR : "Fait à Bron, le4-février-2002"
    re.compile(rf"(?i)\bfait\s+(?:à|a)\b[^\n]{{0,150}}?\ble\s*[-–—]?\s*{_DATE_RE}"),
    re.compile(rf"(?i)\bfait\s+le\s*[-–—]?\s*{_DATE_RE}"),
    re.compile(rf"(?i)\bsign[ée]\s+le\s*[-–—]?\s*{_DATE_RE}"),
    # Formule de signature sans "Fait" : "Lyon, le 09/12/2020", "À Nantes, le 3 mai 2021"
    # (début de ligne, nom de ville court) — utilisée seulement si rien d'autre n'est trouvé.
    # La ligne doit contenir seulement "Ville, le <date>" (pas une phrase).
    re.compile(rf"(?im)^\s*(?:[àa]\s+)?"
               rf"(?!.*\b(?:monsieur|madame|maire|pr[ée]sident|pr[ée]fet|arr[êe]t|pr[ée]sent|d[ée]cision)\b)"
               rf"[A-ZÀ-Ý][A-Za-zÀ-ÿ'’\- ]{{1,40}},\s*le\s*{_DATE_RE}\s*[.,;]?\s*$"),
]


def _norm_mots(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^0-9a-z]+", " ", s).strip()


def _present_dans_texte(valeur: str, texte_norm: str) -> bool:
    parties = [p for p in re.split(r"\s*[;&]\s*", str(valeur)) if p.strip()]
    return bool(parties) and all(
        re.search(rf"(?<![0-9a-z]){re.escape(_norm_mots(p))}(?![0-9a-z])", texte_norm)
        for p in parties if _norm_mots(p)
    )


def _trouver_date_signature(texte: str) -> str:
    """Date écrite après 'Fait à ..., le', 'Fait le' ou 'Signé le' (la dernière du document)."""
    for rx in _SIGNATURE_RES:
        for m in reversed(list(rx.finditer(texte or ""))):
            brut = m.group(1).strip()
            if not _normaliser_date_fr(brut).lower().startswith("non trouv"):
                return brut
    return ""


def garde_fou_df(df: pd.DataFrame, texte: str, debug: bool = False) -> pd.DataFrame:
    """Remplace par 'Non trouvé' toute valeur qui :
    - contient un artefact de chat (assistant, phrase en anglais, balises) ;
    - recopie le libellé d'un autre champ ;
    - est un morceau de phrase d'arrêté dans un champ court ;
    - dépasse la longueur plausible du champ ;
    - (bailleur, commune, référence) n'existe pas dans le texte du document.
    Puis, si la date de signature manque, la cherche après « Fait à …, le ».
    """
    df = df.copy()
    texte_norm = _norm_mots(texte)

    def _rejeter(col, val, raison):
        if debug:
            print(f"[garde_fou] {col} rejeté ({raison}) : {str(val)[:80]!r}")
        return "Non trouvé"

    for col in df.columns:
        if col in _COLONNES_LIBRES:
            continue
        nouv = []
        for val in df[col]:
            if val is None or _is_missing_value(val):
                nouv.append(val)
                continue
            v = str(val).strip()
            if col in _COLONNES_TEXTE_LONG:
                if _ARTEFACT_LLM_RE.search(v):
                    val = _rejeter(col, v, "artefact LLM")
                elif _BLOC_SIGNATURE_RE.search(v):
                    val = _rejeter(col, v, "bloc de signature")
                nouv.append(val)
                continue
            if _ARTEFACT_LLM_RE.search(v):
                val = _rejeter(col, v, "artefact LLM")
            elif _LIBELLE_FUITE_RE.search(v):
                val = _rejeter(col, v, "libellé d'un autre champ")
            elif _PHRASE_RE.search(v):
                val = _rejeter(col, v, "phrase d'arrêté")
            elif len(v) > _LONGUEUR_MAX.get(col, 150):
                val = _rejeter(col, v, "trop long")
            elif col in _MOTS_MAX_PAR_PARTIE and any(
                    len(p.split()) > _MOTS_MAX_PAR_PARTIE[col] for p in re.split(r"\s*;\s*", v)):
                val = _rejeter(col, v, "trop de mots")
            elif col in _COLONNES_ANCREES and not _present_dans_texte(v, texte_norm):
                val = _rejeter(col, v, "absent du texte")
            nouv.append(val)
        df[col] = nouv

    if "Date de signature" in df.columns:
        if df["Date de signature"].apply(_is_missing_value).all():
            d = _trouver_date_signature(texte)
            if d:
                if debug:
                    print(f"[garde_fou] Date de signature trouvée dans le texte : {d!r}")
                df["Date de signature"] = d
    return df


# --- dépendances utilisées seulement à l'appel des fonctions (importées en fin de module : évite les imports circulaires) ---
from .normalisation import _is_missing_value, _normaliser_date_fr  # noqa: E402,F401
