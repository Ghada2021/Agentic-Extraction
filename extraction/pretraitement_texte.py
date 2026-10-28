"""Pré-traitements du texte OCR : lignes de formulaire, suppression des clauses « Vu ».
Code repris tel quel de pmv_api.py (aucune modification)."""
from ._base import *  # noqa: F401,F403


# ====================================================================
#          LIGNES DE FORMULAIRE « Libellé (en ml)  171 »
# ====================================================================
# Dans les formulaires, l'unité est dans le libellé et la valeur vient après :
#   "Artère souterraine (en ml)  171"  -> "Artère souterraine : 171 ml"
#   "Chambre (quantité)  3"            -> "Chambre : 3"
#   "Cabine (emprise au sol en m²) 12" -> "Cabine : 12 m²"
# Les lignes sans valeur ("Artère aérienne (en ml)") ne changent pas.
_FORM_LIGNE_RE = re.compile(
    r"^(?P<label>[^()\n]*?[A-Za-zÀ-ÿ][^()\n]*?)\s*"
    r"\(\s*(?P<parenth>[^()]*?)\s*\)\s*[:\-–]?\s*"
    r"(?P<num>\d[\d\s.,]*?)\s*$"
)
_FORM_UNITE_RE = re.compile(r"(?i)(?:^|\b(?:en|au)\s+)(?P<unit>ml|m²|m2|m|km|mètres?|metres?)$")
_FORM_QTE_RE = re.compile(r"(?i)^(?:quantit[ée]|nombre|nbre|nb|qt[ée])$")


def _normaliser_lignes_formulaire(texte: str) -> str:
    out = []
    for ligne in (texte or "").splitlines():
        m = _FORM_LIGNE_RE.match(ligne.strip())
        if m:
            label = m.group("label").strip(" :-–")
            parenth = m.group("parenth").strip()
            num = re.sub(r"\s+", "", m.group("num")).rstrip(".,")
            mu = _FORM_UNITE_RE.search(parenth)
            if mu:
                unit = mu.group("unit").lower().replace("m2", "m²")
                reste = parenth[:mu.start()].strip(" ,;-")  # ex. "emprise au sol", "largeur"
                if reste:
                    label = f"{label} ({reste})"
                out.append(f"{label} : {num} {unit}")
                continue
            if _FORM_QTE_RE.match(parenth):
                out.append(f"{label} : {num}")
                continue
        out.append(ligne)
    return "\n".join(out)


# ====================================================================
#                 SUPPRESSION DES CLAUSES "VU"
# ====================================================================
# Début d'une clause "Vu" (visa juridique)
_VU_START_RE = re.compile(r"^\s*[-–—•·*]?\s*vu\b", re.I)
# Autre clause du préambule : termine la clause Vu en cours
_PREAMBULE_CLAUSE_RE = re.compile(
    r"^\s*[-–—•·*]?\s*(?:consid[ée]rant|sur\s+(?:la\s+)?proposition|apr[èe]s\s+avis)", re.I)
# Fin du préambule : "ARRÊTE" seul sur sa ligne, ou "ARTICLE 1 / 1er / PREMIER"
_FIN_PREAMBULE_RE = re.compile(
    r"^\s*(?:a\s*r\s*r\s*[êe]\s*t\s*e\s*:?\s*$"
    r"|article\s*(?:1\b|1er\b|premier\b|i\b))",
    re.I)
_VU_MAX_CONTINUATION = 4  # sécurité si le document n'a ni ARRÊTE ni ARTICLE


def _supprimer_clauses_vu(texte: str) -> str:
    """Retire les clauses 'Vu ...' UNIQUEMENT dans le préambule de l'arrêté.

    - Le préambule s'arrête à 'ARRÊTE' (seul sur sa ligne) ou 'ARTICLE 1 / PREMIER' :
      tout ce qui suit est conservé tel quel.
    - Une clause Vu = la ligne 'Vu ...' + ses lignes de suite, jusqu'au ';' ou '.' final,
      une ligne vide, un 'Considérant', un nouveau 'Vu' ou la fin du préambule.
    - Les lignes hors clause Vu (en-tête, pied de page, Considérant) sont gardées.
    - Sans ARRÊTE/ARTICLE dans le document : même règle, mais une clause Vu
      ne peut pas absorber plus de 4 lignes de suite (sécurité).
    """
    lignes = (texte or "").splitlines()
    borne = any(_FIN_PREAMBULE_RE.match(l.strip()) for l in lignes)
    max_cont = None if borne else _VU_MAX_CONTINUATION

    out, in_vu, termine, cont = [], False, True, 0
    dans_preambule = True
    for ligne in lignes:
        s = ligne.strip()

        if dans_preambule and _FIN_PREAMBULE_RE.match(s):
            dans_preambule, in_vu = False, False
        if not dans_preambule:
            out.append(ligne)          # corps de l'arrêté : jamais touché
            continue

        if _VU_START_RE.match(s):
            in_vu, termine, cont = True, s.endswith((";", ".")), 0
            continue
        if in_vu:
            if (not s or termine or _PREAMBULE_CLAUSE_RE.match(s)
                    or (max_cont is not None and cont >= max_cont)):
                in_vu = False
            else:
                cont += 1
                termine = s.endswith((";", "."))
                continue
        out.append(ligne)
    return "\n".join(out)
