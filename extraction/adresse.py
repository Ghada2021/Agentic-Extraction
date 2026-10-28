"""Colonne « Adresse des travaux ».
Code repris tel quel de pmv_api.py (aucune modification)."""
from ._base import *  # noqa: F401,F403


# ====================================================================
#                         ADRESSE DES TRAVAUX
# ====================================================================
# Une "voie" = ce qui fait qu'un texte est une adresse de travaux (et pas juste une commune).
_VOIE_KW = re.compile(
    r"(?i)("
    r"\b(rue|avenue|av|boulevard|bd|route|chemin|impasse|all[ée]e|voie|sentier|venelle|"
    r"passage|place|quai|cours|rond[- ]?point|lieu[- ]?dit|porte)\b"
    r"|\b(rd|rn|vc|cr|pk|pr)\s*\d+"
    r"|\b[an]\s*\d{1,3}\b"
    r"|autoroute"
    r")"
)


@trace_step('text')
def llm_extract_adresse_travaux(text: str, client, deployment, debug: bool = False) -> str:
    """Extraction de l'adresse / localisation des travaux via LLM."""

    def _noacc_lower(s: str) -> str:
        s = unicodedata.normalize("NFKD", s or "")
        s = "".join(ch for ch in s if not unicodedata.combining(ch))
        s = re.sub(r"\s+", " ", s).strip().lower()
        return s

    def _fragment_bruite(frag: str) -> bool:
        """Détecte un fragment d'adresse illisible issu du bruit OCR."""
        t = (frag or "").strip()
        if not t:
            return True
        if re.search(r"\.{2,}|…", t):                       # points de suite '...' / '…'
            return True
        # Token « poubelle » = au moins 2 alternances chiffre<->lettre (ex: '02ANAM1', 'C12TURENNE').
        # Un numéro de rue ('255bis'), un code voirie ('RN157') ou 'N°3' n'ont qu'1 alternance -> OK.
        for tok in re.findall(r"\S+", t):
            w = re.sub(r"[^0-9A-Za-zÀ-ÿ]", "", tok)
            if len(w) < 2:
                continue
            trans = sum(1 for a, b in zip(w, w[1:]) if a.isdigit() != b.isdigit())
            if trans >= 2:
                return True
        return False

    def _nettoyer_adresses(adresse_str: str) -> str:
        """Sépare, filtre le bruit OCR, jette les fragments sans voie (communes), déduplique."""
        if not adresse_str or adresse_str.lower().startswith("non trouv"):
            return "non trouvée"
        vus, out = set(), []
        for part in re.split(r"\s*;\s*", adresse_str):
            p = part.strip().strip(",;. ")
            if not p or _fragment_bruite(p):
                continue
            if not _VOIE_KW.search(p):          # un fragment sans voie (ex: 'INGRÉ') = commune, pas adresse
                continue
            cle = re.sub(r"[^a-z0-9]", "", _noacc_lower(p))
            if not cle or cle in vus:
                continue
            vus.add(cle)
            p = re.sub(r"\s*,\s*", ", ", re.sub(r"\s+", " ", p)).strip(", ")
            out.append(p)
        return " ; ".join(out) if out else "non trouvée"

    lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    numbered = "\n".join(f"{i+1:03d}: {l}" for i, l in enumerate(lines))

    system_msg = (
        "Assistant d'extraction ULTRA STRICT.\n"
        "- N'invente JAMAIS.\n"
        "- Copie les libellés EXACTEMENT tels qu'ils apparaissent dans le texte.\n"
        "- Si une valeur ne figure pas dans le texte, écris exactement: 'non trouvée'.\n"
        "- Réponds UNIQUEMENT avec un bloc <r> contenant 1 ligne, rien d'autre."
    )

    user_msg = f"""
Tu reçois un texte OCR avec des lignes numérotées.
Tu dois extraire EXACTEMENT cette ligne (et rien d'autre) :

<r>
Adresse des travaux : ...
</r>

RÈGLES CLAIRES

1) Tu cherches l'ADRESSE ou la LOCALISATION PHYSIQUE des travaux :
   - Rue, avenue, boulevard, route, chemin, place, impasse, allée, voie, sentier, venelle, passage...
   - Route départementale (RD), route nationale (RN), route communale (VC, CR)
   - Autoroute (A1, A6, etc.), point kilométrique (PK), point de repère (PR)
   - Passage à niveau (PN), Porte (ex: Porte de paris RD30)
   - Lieu-dit, parcelle cadastrale, Commune + rue
   - L'adresse DOIT contenir au moins une VOIE (rue, sentier, venelle, route, RN, RD, chemin...).
     Recopie TOUT le bloc, même s'il s'étend sur plusieurs lignes et enchaîne plusieurs voies
     séparées par « / ».

1bis) INTERDIT : ne rends JAMAIS un simple nom de COMMUNE / VILLE comme adresse
   (ex: « INGRÉ », « MARSEILLE » seuls). Ça, c'est la commune, PAS l'adresse des travaux.
   Si tu ne vois qu'un nom de ville sans aucune voie → "non trouvée".

1ter) GARDE les repères de PORTION, qui font partie de l'adresse :
   « entre le N°X et le N°Y », « entre le X et le Y », « au niveau du N », « du n°A au n°B »,
   « jusqu'à la rue ... », « au droit de ... ». Recopie-les tels quels.

2) INDICES : après "concernant", "situé", "localisation", "emplacement", "lieu des travaux",
   "adresse du chantier", "sur la voie", "au droit de", "travaux sur", "occupation du domaine public".

3) NE PAS EXTRAIRE :
   - Le PÉTITIONNAIRE / opérateur télécom (BOUYGUES TÉLÉCOM, ORANGE, FREE, SFR, ...) ni son siège
     ("demeurant", "sise", "siège", "domicilié", "SIRET", "RCS", "TSA")
   - L'adresse du DÉPARTEMENT / PRÉFECTURE / MAIRIE / CONSEIL DÉPARTEMENTAL
   - Ne pas inclure le type de réseau (souterrain, aérien) ni le type de travaux.

4) Si PLUSIEURS localisations DIFFÉRENTES, concatène avec " ; ". Extraire TOUTES les adresses d'un tableau.
   Cible en priorité les voies où portent RÉELLEMENT des travaux (génie civil / GC, fourreaux,
   chambres, tranchée, pose, câble). Ignore les voies simplement citées sans travaux.

5) COPIE L'ADRESSE COMPLÈTE (rue, route, RD, RN, PR, PK, commune, code postal, numéro).
   Supprime UNIQUEMENT les mots de NATURE des travaux (pose, création, câble, chambre, fourreau, tranchée...).

6) UNE SEULE forme par adresse. Le texte OCR contient souvent la MÊME rue deux fois :
   une version lisible et une version abîmée (« Rue.Frecaric...02ANAM1 », « Ri2..de…BiiRA.H »).
   Garde UNIQUEMENT la version lisible. NE RECOPIE JAMAIS les fragments avec des points de suite
   (« ... »), des lettres et chiffres mélangés dans un mot, ou des caractères parasites.
   Corrige les fautes OCR évidentes (accents, lettres isolées) pour rendre une adresse propre.

7) Si aucune adresse de travaux → "non trouvée"

TEXTE COMPLET (lignes numérotées) :
{numbered}
""".strip()

    try:
        response = traced_completion(client.chat.completions.create, 
            model=deployment,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            max_completion_tokens=4000,  # GPT-5 : inclut les tokens de réflexion (était 300)
        )
        decoded = (response.choices[0].message.content or "").strip()
    except Exception as e:
        print(f"[llm_extract_adresse_travaux] Azure OpenAI error: {e}")
        decoded = ""

    if debug:
        print("DEBUG LLM (adresse) >>>\n", decoded[:2000], "\n<<< END")

    mres = re.search(r"<r>(.*?)</r>", decoded, flags=re.I | re.S)
    if mres:
        block = mres.group(1).strip()
    else:
        mres2 = re.search(r"<r>(.*)", decoded, flags=re.I | re.S)
        block = mres2.group(1).strip() if mres2 else decoded.strip()

    adresse_llm = "non trouvée"

    mm = re.search(r"^\s*Adresse\s+des\s+travaux\s*:\s*(.+?)\s*$", block, flags=re.I | re.M)
    if mm:
        adresse_llm = mm.group(1).strip()
    elif block and not block.lower().startswith("non trouv"):
        clean = re.sub(r"\s+", " ", block).strip().rstrip(",. ")
        if len(clean) > 3:
            adresse_llm = clean

    if not adresse_llm or adresse_llm.lower().startswith("non trouv"):
        adresse_llm = "non trouvée"

    PETITIONNAIRE_CTX = re.compile(
        r"(?i)\b(petitionnaire|pétitionnaire|demeurant|domicili[ée]|"
        r"si[eè]ge\s+social|sise|siret|siren|rcs|tsa|"
        r"la\s+soci[ée]t[ée]|repr[ée]sent[ée]\s+par)\b"
    )

    ROAD_INDICATOR = re.compile(r"(?i)\b(RD|RN|VC|CR|PR|PK|D\d|N\d|A\d|autoroute)\b")

    TRAVAUX_CTX = re.compile(
        r"(?i)\b(travaux|chantier|occupation|autoris[ée]|voirie|domaine\s+public|"
        r"concern[ée]|situe|situ[ée]s?|localisation|emplacement)\b"
    )

    def _is_petitionnaire_address(adresse: str, text_raw: str) -> bool:
        if not adresse or adresse.lower().startswith("non trouv"):
            return False
        adresse_norm = _noacc_lower(adresse)[:60]
        text_norm = _noacc_lower(text_raw)
        positions = [m.start() for m in re.finditer(re.escape(adresse_norm), text_norm)]
        if not positions:
            return False
        for pos in positions:
            left = text_raw[max(0, pos - 200): pos]
            if TRAVAUX_CTX.search(left):
                return False
            if not PETITIONNAIRE_CTX.search(left):
                return False
        return True

    if adresse_llm != "non trouvée":
        if not ROAD_INDICATOR.search(adresse_llm):
            if _is_petitionnaire_address(adresse_llm, text):
                if debug:
                    print(f"[DEBUG] Rejeté pétitionnaire : {adresse_llm}")
                adresse_llm = "non trouvée"

    # Garde-fou : une adresse de travaux DOIT contenir une voie (rue, sentier, RN/RD...).
    # Un simple nom de commune (« INGRÉ ») n'est PAS une adresse -> non trouvée.
    if adresse_llm != "non trouvée":
        if not _VOIE_KW.search(adresse_llm):
            if debug:
                print(f"[DEBUG] Rejeté (pas de voie, sûrement une commune) : {adresse_llm}")
            adresse_llm = "non trouvée"

    # Nettoyage final : retire les doublons OCR bruités, déduplique.
    adresse_llm = _nettoyer_adresses(adresse_llm)

    return f"Adresse des travaux : {adresse_llm}"


def _parse_adresse_output(s: str) -> str:
    mm = re.search(r"(?i)Adresse\s+des\s+travaux\s*:\s*(.+)", s)
    if mm:
        val = mm.group(1).strip()
        return val.splitlines()[0].strip()
    return "non trouvée"


def adresse_to_df(output: str, none_for_missing: bool = False) -> pd.DataFrame:
    v = _parse_adresse_output(output)
    if none_for_missing and v.lower().startswith("non trouv"):
        v = None
    return pd.DataFrame({"Adresse des travaux": [v]})
