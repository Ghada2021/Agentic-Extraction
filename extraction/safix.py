"""Colonne « Safix » (6 chiffres du nom de fichier).
Code repris tel quel de pmv_api.py (aucune modification)."""
from ._base import *  # noqa: F401,F403


# ====================================================================
#                 SAFIX (6 CHIFFRES DANS LE NOM DU PDF)
# ====================================================================
# Exactement 6 chiffres consécutifs (une suite de 7+ chiffres est ignorée).
RE_SIX_DIGITS = re.compile(r'(?<!\d)(\d{6})(?!\d)')


def extraire_safix(nom_fichier) -> str:
    """Renvoie les 6 chiffres consécutifs du nom du PDF, sinon 'Non trouvé'."""
    base = os.path.splitext(os.path.basename(str(nom_fichier or "")))[0]
    m = RE_SIX_DIGITS.search(base)
    return m.group(1) if m else "Non trouvé"
