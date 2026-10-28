"""Colonne « Partenaire cession ».
Code repris tel quel de pmv_api.py (aucune modification)."""
from ._base import *  # noqa: F401,F403


# ====================================================================
#                         PARTENAIRE CESSION
# ====================================================================
@trace_step('texte_extrait')
def extract_partenaire_cession_df(texte_extrait: str) -> pd.DataFrame:
    """
    Détecte Nexloop / Cityfast / SDFast (tolérant casse/espaces) et renvoie
    un DataFrame 1 ligne: {"Partenaire cession": "..."} ou "Non trouvé".
    """
    def _norm(s: str) -> str:
        s = unicodedata.normalize("NFKD", s or "")
        s = "".join(ch for ch in s if not unicodedata.combining(ch))
        s = re.sub(r"\s+", " ", s).strip().upper()
        return s

    U = _norm(texte_extrait)

    pat = re.compile(r"\b(NEX\s*LOOP|CITY\s*FAST|SD\s*FAST|SDFAST)\b", re.I)

    mapping = {
        "NEXLOOP": "Nexloop",
        "CITYFAST": "Cityfast",
        "SDFAST": "SDFast",
    }

    found = []
    for m in pat.finditer(U):
        key = re.sub(r"\s+", "", m.group(1)).upper()
        canon = mapping.get(key)
        if canon and canon not in found:
            found.append(canon)

    value = " & ".join(found) if found else "Non trouvé"
    return pd.DataFrame({"Partenaire cession": [value]})
