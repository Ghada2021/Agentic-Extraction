"""Post-traitements des colonnes : nombres, unités ml, dates, « Non trouvé », casse, fusion GC, nettoyage.
Code repris tel quel de pmv_api.py (aucune modification)."""
from ._base import *  # noqa: F401,F403


# ====================================================================
#                 NOMBRES EN LETTRES -> CHIFFRES
# ====================================================================
_SMALL_FR = {
    "zero": 0, "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4,
    "cinq": 5, "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10,
    "onze": 11, "douze": 12, "treize": 13, "quatorze": 14, "quinze": 15, "seize": 16,
    "vingt": 20, "vingts": 20, "trente": 30, "quarante": 40, "cinquante": 50,
    "soixante": 60, "quatrevingt": 80, "quatrevingts": 80,
}

_NUMBER_TOKENS = set(_SMALL_FR) | {"cent", "cents", "mille", "et", "quatre", "vingt", "vingts"}


def _fr_words_to_int(phrase: str):
    """Convertit une suite de mots-nombres français (sans accents, sans tirets, en minuscules) en entier."""
    phrase = (phrase or "").strip()
    if not phrase:
        return None
    phrase = re.sub(r"\bquatre\s+vingt", "quatrevingt", phrase)
    tokens = phrase.split()

    total, current, used = 0, 0, False
    for w in tokens:
        if w in _SMALL_FR:
            current += _SMALL_FR[w]
            used = True
        elif w in ("cent", "cents"):
            current = (current or 1) * 100
            used = True
        elif w == "mille":
            total += (current or 1) * 1000
            current = 0
            used = True
        else:
            return None
    if not used:
        return None
    return total + current


def _convertir_nombres_ecrits(s):
    """
    Remplace les nombres écrits en lettres par des chiffres, en gardant le reste
    (unités, ponctuation) intact. 'cinquante-six mètres linéaires' -> '56 mètres linéaires'.
    """
    if s is None:
        return s
    original = str(s)
    if not original.strip() or original.strip().lower().startswith("non trouv"):
        return original

    out, buf = [], []

    def flush():
        if buf:
            norm = _strip_accents(" ".join(buf).lower()).replace("-", " ")
            norm = " ".join(w for w in norm.split() if w != "et")
            n = _fr_words_to_int(norm)
            out.append(str(n) if n is not None else " ".join(buf))
            buf.clear()

    for raw in original.split():
        sub = _strip_accents(raw.lower()).replace("-", " ").split()
        sub = [x for x in sub if x]
        if sub and all(x in _NUMBER_TOKENS for x in sub):
            buf.append(raw)
        else:
            flush()
            out.append(raw)
    flush()
    return " ".join(out)


def _texte_nombres_en_chiffres(text: str) -> str:
    """Convertit les nombres écrits en lettres -> chiffres, ligne par ligne (garde la structure)."""
    return "\n".join(_convertir_nombres_ecrits(l) for l in (text or "").splitlines())


def normaliser_longueurs_df(df: pd.DataFrame, cols=None) -> pd.DataFrame:
    """Convertit les nombres en lettres -> chiffres dans les colonnes de longueur."""
    if cols is None:
        cols = ["Longueur génie civil", "Longueur par fourreau", "Longueur totale"]
    df = df.copy()
    for c in cols:
        if c in df.columns:
            df[c] = df[c].apply(_convertir_nombres_ecrits)
    return df


# ====================================================================
#                 NORMALISATION UNITÉ -> "N ml"
# ====================================================================
def _to_number(num_str: str):
    """Parse un nombre français ('1 234,5', '14,2546', '56') -> float."""
    s = (num_str or "").strip().replace(" ", "").replace("\xa0", "").replace(" ", "")
    if "," in s and "." in s:          # '1.234,5' -> point = millier, virgule = décimale
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:                      # '14,25' -> virgule décimale
        s = s.replace(",", ".")
    s = s.strip(".,")
    try:
        return float(s)
    except ValueError:
        return None


def _fmt_number(x: float) -> str:
    """Formate un nombre : entier sans décimale, sinon virgule française."""
    if x == int(x):
        return str(int(x))
    return ("%.4f" % x).rstrip("0").rstrip(".").replace(".", ",")


def _ml_simple(val):
    """Uniformise UNE valeur de longueur en 'N ml' (sans gérer les '&')."""
    if val is None:
        return val
    s = str(val).strip()
    if not s or s.lower().startswith("non trouv"):
        return s

    low = _strip_accents(s.lower())
    m = re.search(r"\d[\d   .,]*\d|\d", low)
    if not m:
        return s

    num = _to_number(m.group(0))
    if num is None:
        return s

    if re.search(r"\bkm\b", low):       # km -> mètres
        num *= 1000

    return f"{_fmt_number(num)} ml"


def _normaliser_unite_ml(val):
    """
    Uniformise une valeur de longueur en 'N ml', y compris les valeurs MULTIPLES séparées par '&'.
    '56ml'->'56 ml' ; '1,2 km'->'1200 ml' ; '1080 & 220 & 230 mètres'->'1080 ml & 220 ml & 230 ml'.
    Garde 'Non trouvé' et les valeurs sans nombre intactes.
    """
    if val is None:
        return val
    s = str(val).strip()
    if not s or s.lower().startswith("non trouv"):
        return s
    if "&" in s:
        parts = [_ml_simple(p).strip() for p in s.split("&")]
        parts = [p for p in parts if p]
        return " & ".join(parts) if parts else s
    return _ml_simple(s)


def normaliser_unite_ml_df(df: pd.DataFrame, cols=None) -> pd.DataFrame:
    """Force le format 'N ml' sur les colonnes de longueur demandées."""
    if cols is None:
        cols = ["Longueur génie civil", "Longueur totale", "Longueur par fourreau"]
    df = df.copy()
    for c in cols:
        if c in df.columns:
            df[c] = df[c].apply(_normaliser_unite_ml)
    return df


# ====================================================================
#                 NORMALISATION DES DATES -> JJ/MM/AAAA
# ====================================================================
_MOIS_FR_NUM = {
    "janvier": "01", "janv": "01", "jan": "01",
    "fevrier": "02", "fevr": "02", "fev": "02",
    "mars": "03", "mar": "03",
    "avril": "04", "avr": "04",
    "mai": "05",
    "juin": "06",
    "juillet": "07", "juil": "07", "jul": "07",
    "aout": "08", "aou": "08",
    "septembre": "09", "sept": "09", "sep": "09",
    "octobre": "10", "oct": "10",
    "novembre": "11", "nov": "11",
    "decembre": "12", "dec": "12",
}


def _mois_vers_num(mot: str):
    m = re.sub(r"[^a-z]", "", (mot or "").lower())
    if m in _MOIS_FR_NUM:
        return _MOIS_FR_NUM[m]
    for cle, num in _MOIS_FR_NUM.items():
        if len(cle) >= 3 and m.startswith(cle):
            return num
    return None


def _annee4(y: str) -> str:
    """Année sur 2 chiffres -> 4 chiffres (pivot 68, comme %y : 00-68 -> 20xx, 69-99 -> 19xx).
    Les dates de fin d'autorisation peuvent aller loin dans le futur ('15/12/36' -> 2036)."""
    y = re.sub(r"\D", "", y or "")
    if len(y) == 4:
        return y
    if len(y) == 2:
        n = int(y)
        return str(2000 + n) if n <= 68 else str(1900 + n)
    return y


# Alias mois tolérants au bruit OCR (après correction chiffre->lettre).
_MOIS_OCR_ALIAS = {
    "jan": "01", "janv": "01",
    "fev": "02", "fevr": "02",
    "mar": "03", "mars": "03",
    "avr": "04", "avri": "04",
    "mai": "05",
    "jui": "06", "juin": "06",
    "jul": "07", "juil": "07", "juill": "07",
    "aou": "08", "aout": "08", "aon": "08", "aor": "08", "aoi": "08",
    "sep": "09", "sept": "09",
    "oct": "10",
    "nov": "11",
    "dec": "12",
}


def _mois_ocr_vers_num(word: str):
    """Mois en lettres, éventuellement bruité par l'OCR ('0CT', 'Aon', 'déc.'), -> '01'..'12'."""
    if not word:
        return None
    base = word.lower().replace("0", "o").replace("5", "s").replace("8", "b")
    # '1' OCR = 'i' ('MA1' -> mai, 'JU1N' -> juin) ou 'l' ('3l', 'ju1llet') : on essaie 'i' d'abord.
    if "1" in base:
        for variante in (base.replace("1", "i"), base.replace("1", "l")):
            num = _mois_ocr_vers_num(variante)
            if num:
                return num
        return None
    w = re.sub(r"[^a-z]", "", base)
    if not w:
        return None
    if w in {"lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"}:
        return None
    num = _mois_vers_num(w)           # table complète d'abord
    if num:
        return num
    if w in _MOIS_OCR_ALIAS:
        return _MOIS_OCR_ALIAS[w]
    for cle, v in _MOIS_OCR_ALIAS.items():
        if w.startswith(cle) or cle.startswith(w):
            return v
    return None


def _digits_ocr(tok: str) -> str:
    """Extrait les chiffres d'un token en corrigeant les lettres OCR courantes (l->1, o->0, s->5, b->8)."""
    fixed = tok.translate(str.maketrans("loisb", "10158"))
    return re.sub(r"\D", "", fixed)


def _parse_tokens_date(tokens):
    """
    À partir des tokens alphanumériques d'une date, repère mois (en lettres, même bruité),
    jour (chiffres avant, y compris collés ou OCR) et année. Renvoie 'JJ/MM/AAAA' ou 'MM/AAAA'.
    """
    # Weekdays are neither months ('mardi' must not match 'mar') nor day digits
    # ('lundi' would otherwise contribute OCR-corrected l/i -> 1).
    weekdays = {"lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"}
    tokens = [token for token in tokens if token.lower() not in weekdays]
    month_idx = month_num = day_glued = None
    for i, tok in enumerate(tokens):
        mg = re.match(r"^(\d{1,2})([a-z][a-z0-9]*)$", tok)   # jour collé au mois : '15aon', '9jan'
        if mg:
            cand = _mois_ocr_vers_num(mg.group(2))
            if cand:
                month_idx, month_num, day_glued = i, cand, mg.group(1)
                break
        if re.search(r"[a-z]", tok):                          # token-mois entier : 'jan', '0ct', 'octobre'
            cand = _mois_ocr_vers_num(tok)
            if cand:
                month_idx, month_num = i, cand
                break
    if month_idx is None:
        return None

    if day_glued is not None:
        day = day_glued
    else:
        day = "".join(_digits_ocr(t) for t in tokens[:month_idx])
    day = day[-2:] if len(day) > 2 else day

    year = None
    for t in tokens[month_idx + 1:]:
        d = _digits_ocr(t)
        if len(d) >= 2:
            year = d
    if year is None:
        return None

    if not day:
        return f"{month_num}/{_annee4(year)}"
    return f"{int(day):02d}/{month_num}/{_annee4(year)}"


def _valider_date(s: str) -> str:
    """Vérifie qu'une date est un vrai JJ/MM/AAAA (ou MM/AAAA) valide, sinon 'non trouvée'."""
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", s or "")
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= d <= 31 and 1 <= mo <= 12 and 1900 <= y <= 2100:
            return s
        return "non trouvée"
    m = re.match(r"^(\d{2})/(\d{4})$", s or "")     # MM/AAAA (date partielle sans jour)
    if m:
        mo, y = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12 and 1900 <= y <= 2100:
            return s
        return "non trouvée"
    return "non trouvée"


def _normaliser_date_fr(val):
    """
    Uniformise une date en JJ/MM/AAAA, tolérant au bruit OCR des scans.
    '14 août 2030'->'14/08/2030' ; '2 3 0CT.2018'->'23/10/2018' ; '9 0CT 2018'->'09/10/2018' ;
    '9-JAN-2009'->'09/01/2009' ; '3l DEC 2020'->'31/12/2020' ; '15Aon 99'->'15/08/1999' ;
    '22.7 .99'->'22/07/1999' ; 'le 3.11.99'->'03/11/1999'.
    Si la date ne peut PAS être ramenée à un JJ/MM/AAAA valide (ex: '3. {. 99', '29 ai 209',
    '15Aon99'), renvoie 'non trouvée' plutôt qu'une valeur aberrante. 'Non trouvé' reste intact.
    """
    if val is None:
        return val
    s = str(val).strip()
    if not s or s.lower().startswith("non trouv"):
        return s

    low = _strip_accents(s.lower())
    low = re.sub(r"^\s*le\s+", "", low).strip()

    # 0) ISO : AAAA-MM-JJ
    m = re.search(r"\b(\d{4})[.\-/ ](\d{1,2})[.\-/ ](\d{1,2})\b", low)
    if m:
        y, mo, d = m.groups()
        return _valider_date(f"{int(d):02d}/{int(mo):02d}/{y}")

    # A) date avec mois en lettres (même bruité) — via tokens
    tokens = re.findall(r"[a-z0-9]+", re.sub(r"[.\-/]", " ", low))
    res = _parse_tokens_date(tokens)
    if res:
        return _valider_date(res)

    # B) jour / mois / année entièrement numérique (séparateurs bruités : '. ', '  ')
    m = re.search(
        r"(\d{1,2})\s*[.\-/ ]+\s*(\d{1,2})\s*[.\-/ ]+\s*(\d{2,4})\b",
        low,
    )
    if m:
        d, mo, y = m.groups()
        return _valider_date(f"{int(d):02d}/{int(mo):02d}/{_annee4(y)}")

    # Rien d'exploitable -> on préfère 'non trouvée' à une valeur aberrante.
    return "non trouvée"


def normaliser_dates_df(df: pd.DataFrame, cols=None) -> pd.DataFrame:
    """Force le format JJ/MM/AAAA sur les colonnes de dates."""
    if cols is None:
        cols = ["Date de signature",
                "Date de debut d'autorisation",
                "Date de fin d'autorisation"]
    df = df.copy()
    for c in cols:
        if c in df.columns:
            df[c] = df[c].apply(_normaliser_date_fr)
    return df


# ====================================================================
#                 NORMALISATION "NON TROUVÉ"
# ====================================================================
_MISSING_EXACT = {
    "", "-", "--", "---", "n/a", "na", "n.a", "n.a.", "nan", "none", "null",
    "neant", "aucun", "aucune", "vide", "inconnu", "inconnue", "nc", "n.c",
    "n.c.", "introuvable", "?", "/",
}

_MISSING_PREFIXES = (
    "non trouv", "non dispo", "non renseign", "non communiqu", "non precis",
    "non identifi", "non mentionn", "non applicable", "not found", "not available",
)


def _is_missing_value(val) -> bool:
    if val is None:
        return True
    try:
        if pd.isna(val):
            return True
    except (TypeError, ValueError):
        pass
    s = _strip_accents(str(val)).lower().strip()
    s = re.sub(r"\s+", " ", s).strip(" .:;-_")
    if s in _MISSING_EXACT:
        return True
    return any(s.startswith(p) for p in _MISSING_PREFIXES)


def normaliser_non_trouve_df(df: pd.DataFrame, valeur: str = "Non trouvé") -> pd.DataFrame:
    """Remplace toutes les variantes de 'non trouvé' par une seule valeur, sur toutes les colonnes."""
    df = df.copy()
    for c in df.columns:
        df[c] = df[c].apply(lambda v: valeur if _is_missing_value(v) else v)
    return df


# ====================================================================
#                 HARMONISATION DE LA CASSE (Titre)
# ====================================================================
_PARTICULES = {"de", "du", "des", "la", "le", "les", "d", "l", "et",
               "a", "au", "aux", "en", "sur", "sous", "lez", "les"}
_ACRONYMES = {"rd", "rn", "vc", "cr", "pr", "pk", "gc", "vnf", "cd",
              "epci", "sdis", "zac", "zi", "za", "bp"}


def _titre_propre(val):
    """
    Met une chaîne en casse « Titre » : 1re lettre de chaque mot en majuscule, reste en minuscule.
    'RUE JULES FERRY, 13002, MARSEILLE' -> 'Rue Jules Ferry, 13002, Marseille'.
    Garde codes de voirie (RD30) en maj, particules (de, la, en) en min, 'Non trouvé' intact.
    """
    if val is None:
        return val
    s = str(val).strip()
    if not s or s.lower().startswith("non trouv"):
        return s

    def _cap(tok, is_first):
        low = tok.lower()
        letters = re.sub(r"[^0-9a-zà-ÿ]", "", low)
        if not letters:
            return tok
        if re.match(r"^(rd|rn|vc|cr|pr|pk|a|d|n)\d+$", letters) or letters in _ACRONYMES:
            return tok.upper()
        if letters.isdigit():
            return tok
        if not is_first and letters in _PARTICULES:
            return low
        return low[:1].upper() + low[1:]

    parts = re.split(r"([ \-'’])", s)
    out, first = [], True
    for part in parts:
        if part in (" ", "-", "'", "’", ""):
            out.append(part)
            continue
        out.append(_cap(part, first))
        first = False
    return "".join(out)


def _premiere_lettre_maj(val: str) -> str:
    """'LE MANS MÉTROPOLE' / 'le mans métropole' -> 'Le mans métropole'."""
    s = str(val).strip()
    return s[:1].upper() + s[1:].lower()


def _normaliser_nom_bailleur(value):
    """Nom canonique + casse harmonisée : tout en minuscule sauf la 1re lettre."""
    nom = _normaliser_nom_bailleur_canonique(value)
    if _is_missing_value(nom):
        return "Non trouvé"
    return _premiere_lettre_maj(nom)


def _normaliser_nom_bailleur_canonique(value):
    """Canonical spelling for known entities; no fuzzy/semantic merging."""
    if _is_missing_value(value):
        return "Non trouvé"

    def key(text):
        text = unicodedata.normalize("NFKD", str(text)).casefold()
        return "".join(c for c in text if c.isalnum() and not unicodedata.combining(c))

    names = {}
    for name in FRENCH_DEPARTMENTS:
        names.setdefault(key(name), name)
    raw = str(value).strip()
    # « Conseil départemental de la Haute-Garonne » : nom complet conservé ; seul le nom
    # du département est remis à l'orthographe officielle (« HAUTE-BARONNE » lu par l'OCR).
    m_cd = re.match(
        r"(?i)^((?:(?:le|la)\s+)?(?:conseil\s+d[ée]partementale?|conseil\s+g[ée]n[ée]ral)"
        r"\s+(?:de\s+la|de\s+l['’]|du|des|de|d['’])\s*)(.+)$", raw)
    if m_cd:
        k_dep = key(m_cd.group(2))
        if k_dep in names:
            return m_cd.group(1).strip() + " " + names[k_dep]
        proches = [n for nk, n in names.items()
                   if len(nk) >= 8 and len(nk) == len(k_dep) and sum(x != y for x, y in zip(nk, k_dep)) == 1]
        if len(proches) == 1:
            return m_cd.group(1).strip() + " " + proches[0]
        return _titre_propre(raw)
    candidates = [raw]
    # Remove presentation prefixes only if the remaining name is known.
    stripped = re.sub(
        r"(?i)^(?:(?:le|la)\s+)?(?:d[ée]partement)"
        r"\s+(?:(?:de|du|des)\s+)?", "", raw)
    candidates.append(stripped)
    candidates.append(re.sub(r"(?i)^(?:la|le|les)\s+|^l['’]\s*", "", stripped))
    for candidate in candidates:
        if key(candidate) in names:
            return names[key(candidate)]
    return _titre_propre(raw)


def normaliser_casse_df(df: pd.DataFrame, cols=None) -> pd.DataFrame:
    """Harmonise la casse (Titre) sur les colonnes texte demandées."""
    if cols is None:
        cols = ["Nom Bailleur", "Commune concernée", "Adresse des travaux"]
    df = df.copy()
    for c in cols:
        if c in df.columns:
            normalizer = _normaliser_nom_bailleur if c in ("Nom Bailleur", "Département") else _titre_propre
            df[c] = df[c].apply(normalizer)
    return df


# ====================================================================
#                 FUSION LONGUEUR GC / LONGUEUR TOTALE
# ====================================================================
def fusionner_longueur_gc_totale(
    df: pd.DataFrame,
    col_gc: str = "Longueur génie civil",
    col_totale: str = "Longueur totale",
    col_finale: str = "Longueur génie civil",
) -> pd.DataFrame:
    """Preserve explicit GC only; remove the separate duct-total column."""
    df = df.copy()

    def _is_valid(val):
        if pd.isna(val):
            return False
        s = str(val).strip().lower()
        return s not in ("", "non trouvé", "non trouvée", "non trouve", "non trouvee")

    if col_gc not in df.columns and col_totale not in df.columns:
        return df

    if col_gc not in df.columns:
        df[col_gc] = "Non trouvé"
    if col_totale not in df.columns:
        df[col_totale] = "Non trouvé"

    def _merge(row):
        # 1) GC bien rempli -> on ne touche pas
        if _is_valid(row[col_gc]):
            return row[col_gc]
        # 2) GC non trouvé mais longueur totale fourreaux remplie -> on la reprend
        if _is_valid(row[col_totale]):
            return row[col_totale]
        # 3) Les deux non trouvés -> on laisse tel quel
        return row[col_gc]

    df[col_finale] = df.apply(_merge, axis=1)

    if col_totale in df.columns and col_totale != col_finale:
        df = df.drop(columns=[col_totale])

    return df


# ====================================================================
#                 NETTOYAGE DES CHAMPS TEXTUELS
# ====================================================================
# Caractères autorisés : lettres (accents compris), chiffres, espace et
# ponctuation utile aux adresses / références : , ; . - / ' ’ & ° ( )
_CARACTERES_AUTORISES_RE = re.compile(r"[^0-9A-Za-zÀ-ÖØ-öø-ÿŒœ\s,;.\-/'’&°()]")


def _nettoyer_champ_texte(val):
    """Retire les caractères parasites OCR (: ? § = | * # ~ _ ± « » etc.)
    sans toucher aux lettres ni aux chiffres. 'Non trouvé' reste intact."""
    if val is None:
        return val
    s = str(val)
    if not s.strip() or _is_missing_value(s):
        return s
    s = _CARACTERES_AUTORISES_RE.sub(" ", s)            # parasites -> espace
    s = re.sub(r"\(\s*\)", " ", s)                       # parenthèses vides
    s = re.sub(r"([,;.\-/&])(\s*\1)+", r"\1", s)          # ',,' '..' '--' -> un seul
    parties = []
    for part in s.split(";"):                            # ' ; ' = séparateur multi-valeurs
        part = re.sub(r"\s+([,.])", r"\1", part)          # pas d'espace avant , .
        part = re.sub(r",(?=\S)", ", ", part)             # espace après ,
        part = re.sub(r"\s{2,}", " ", part)
        part = part.strip(" ,.-/&'’")                    # ponctuation en bord
        if part:
            parties.append(part)
    s = " ; ".join(parties)
    return s if s else "Non trouvé"


def nettoyer_champs_texte_df(df: pd.DataFrame, cols=None) -> pd.DataFrame:
    """Applique _nettoyer_champ_texte aux colonnes textuelles."""
    if cols is None:
        cols = ["Nom Bailleur", "Commune concernée", "Adresse des travaux",
                "Référence bailleur"]
    df = df.copy()
    for c in cols:
        if c in df.columns:
            df[c] = df[c].apply(_nettoyer_champ_texte)
    return df


# --- dépendances utilisées seulement à l'appel des fonctions (importées en fin de module : évite les imports circulaires) ---
from .departement_commune_signature import FRENCH_DEPARTMENTS  # noqa: E402,F401
from .duree import _strip_accents  # noqa: E402,F401