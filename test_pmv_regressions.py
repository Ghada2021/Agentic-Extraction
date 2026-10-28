"""
Tests de non-régression PMV — tous les cas réels rencontrés.

À lancer AVANT de garder une modification :
    python test_pmv_regressions.py                  -> teste pmv.py (version Paddle)
    python test_pmv_regressions.py pmv_api_azure    -> teste la version Azure
    (ou : PMV_MODULE=pmv_api_azure pytest test_pmv_regressions.py)
Les tests propres à l'OCR Paddle sont ignorés pour la version Azure.

Aucun appel OCR ni LLM réel : le modèle est simulé par une réponse fixe.
Si un test échoue, la dernière modification a cassé un cas qui marchait.
Ajoutez ici chaque nouveau cas corrigé (texte OCR réel + résultat attendu).
"""
import importlib
import os
import sys
import types
import unittest

import pandas as pd

_NOM_MODULE = (sys.argv[1] if __name__ == "__main__" and len(sys.argv) > 1
               else os.getenv("PMV_MODULE", "pmv"))
pmv = importlib.import_module(_NOM_MODULE)


def _besoin(*noms):
    """Ignore le test si la version testée n'a pas ces fonctions (ex. OCR Paddle)."""
    manquants = [n for n in noms if not hasattr(pmv, n)]
    if manquants:
        raise unittest.SkipTest(f"absent de {_NOM_MODULE} : {', '.join(manquants)}")


# --------------------------------------------------------------------------
# Outils
# --------------------------------------------------------------------------
def faux_client(reponse: str):
    """Client LLM simulé : renvoie toujours `reponse`."""
    msg = types.SimpleNamespace(content=reponse)
    resp = types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])
    return types.SimpleNamespace(chat=types.SimpleNamespace(
        completions=types.SimpleNamespace(create=lambda **kw: resp)))


def date_signature(texte: str) -> str:
    d = pmv._trouver_date_signature(texte)
    return pmv._normaliser_date_fr(d) if d else ""


# --------------------------------------------------------------------------
# 1. Clauses « Vu »
# --------------------------------------------------------------------------
ARRETE_RHONE = """es Routes Urbaines
23 rue de Solesmes  Permissionnaire
69500 BRON
Affaire suivie par :  N° TN01T031
LE PREFET DU RHONE ET DE LA REGION RHONE ALPES
Vu la pétition en date du 2/11/2001, par laquelle BOUYGUES TELECOM,.demeurant
Europe-51 avenue de l'Europe 78944 VELIZY Cedex, demande l'autorisation d'effectuer des
travaux souterrains sur le réseau télécom, sur une longueur de t38-ml, sur l'emprise de la
route=départementale=n=7-P-R-48±810-a=48±890, sur la commune de TASSFN-LA-DEM
LUNEs, ces travaux étant destinés à laconstruction=de-canalisation=souterraine=7.pvc=80
.avenue:de:la:Républiquex
Vu le Code de la Voirie Routière ;
Vu l'arrêté départemental n°2000-4048 en date du 25 août 2000 portant délégation de
signature ;
TN01T031 1
ARTICLE 1- AUTORISATION
* Le pétitionnaire est autorisé à exécuter les travaux visés ci-dessous.
Vu les plans joints, la tranchée fera 120 ml.
Vue en coupe : chambre L2T"""


def test_vu_supprimes_dans_le_preambule():
    out = pmv._supprimer_clauses_vu(ARRETE_RHONE)
    assert "Vu la pétition" not in out
    assert "Républiquex" not in out          # suite de la 1re clause Vu (6 lignes)
    assert "signature ;" not in out           # suite de clause sur 2 lignes
    assert "LE PREFET DU RHONE" in out        # en-tête gardé
    assert "TN01T031 1" in out                # pied de page gardé


def test_vu_jamais_touche_apres_article_1():
    out = pmv._supprimer_clauses_vu(ARRETE_RHONE)
    assert "ARTICLE 1- AUTORISATION" in out
    assert "Vu les plans joints, la tranchée fera 120 ml." in out
    assert "Vue en coupe : chambre L2T" in out


# --------------------------------------------------------------------------
# 2. En-tête à 2 colonnes (logo Clermont)
# --------------------------------------------------------------------------
def test_logo_clermont_contigu():
    _besoin("_separer_colonnes_entete_texte")
    t = """Permissionnaire : BOUYGUES TELECOM
Référence dossier du permissionnaire : Non renseigné
clermont
auvergne  INVESTISSEMENT
métropole
Le Président
PERMISSION DE VOIRIE N° 2021-0920"""
    lignes = pmv._separer_colonnes_entete_texte(t).splitlines()
    i = lignes.index("clermont")
    assert lignes[i:i + 3] == ["clermont", "auvergne", "métropole"]
    assert "INVESTISSEMENT" in lignes                 # rien n'est supprimé


def test_tableau_en_haut_de_page_jamais_modifie():
    _besoin("_separer_colonnes_entete_texte")
    # Régression 05/10 : le tableau était découpé ("Nbre de fourreaux" / "2" séparés).
    t = """DEPARTEMENT DE LA SEINE-SAINT-DENIS
OBJET DE L'AUTORISATION
AVENUE DU PRESIDENT-JOHN-KENNEDY  ROSNY-SOUS-BOIS
Nbre de fourreaux  Diamètre  Longueur
2  45 mm  120 ml"""
    assert pmv._separer_colonnes_entete_texte(t) == t


def test_entete_libelle_valeur_et_adresse_intacts():
    _besoin("_separer_colonnes_entete_texte")
    t = """es Routes Urbaines
23 rue de Solesmes  Permissionnaire
Affaire suivie par :  N° TN01T031
Vu le Code de la voirie"""
    assert pmv._separer_colonnes_entete_texte(t) == t


# --------------------------------------------------------------------------
# 3. Lignes de formulaire « Libellé (en ml)  171 »
# --------------------------------------------------------------------------
def test_lignes_formulaire():
    t = """Artère aérienne (en ml)
Artère souterraine (en ml)  171
Chambre (quantité)  3
Tranchée (largeur en m) 0,40
RD 30 (PR 12) 450"""
    out = pmv._normaliser_lignes_formulaire(t).splitlines()
    assert out == ["Artère aérienne (en ml)",
                   "Artère souterraine : 171 ml",
                   "Chambre : 3",
                   "Tranchée (largeur) : 0,40 m",
                   "RD 30 (PR 12) 450"]


# --------------------------------------------------------------------------
# 4. Fusion GC / longueur totale
# --------------------------------------------------------------------------
def test_fusion_gc():
    df = pd.DataFrame({"Longueur génie civil": ["120 ml", "Non trouvé", "Non trouvé"],
                       "Longueur totale": ["50 ml", "200 ml", "Non trouvé"]})
    out = pmv.fusionner_longueur_gc_totale(df)
    assert list(out["Longueur génie civil"]) == ["120 ml", "200 ml", "Non trouvé"]
    assert "Longueur totale" not in out.columns


# --------------------------------------------------------------------------
# 5. Nettoyage des champs texte
# --------------------------------------------------------------------------
def test_nettoyage_champs_texte():
    f = pmv._nettoyer_champ_texte
    assert f("Rue : Victor Hugo ?? §§, 59120 Loos") == "Rue Victor Hugo, 59120 Loos"
    assert f("Boulevard | des Belges (RD 30) ;; Rue X") == "Boulevard des Belges (RD 30) ; Rue X"
    assert f("IV-2022-2123-02") == "IV-2022-2123-02"
    assert f("DGAST/SEER/CD/OD") == "DGAST/SEER/CD/OD"
    assert f("Non trouvé") == "Non trouvé"


# --------------------------------------------------------------------------
# 6. Dates (OCR bruité)
# --------------------------------------------------------------------------
def test_normalisation_dates():
    f = pmv._normaliser_date_fr
    attendu = {
        "1 6 MAI 2006": "16/05/2006",
        "1 5 MA1 2000": "15/05/2000",
        "3 JU1N 2001": "03/06/2001",      # juin, pas juillet
        "2 3 0CT.2018": "23/10/2018",
        "3l DEC 2020": "31/12/2020",
        "15Aon 99": "15/08/1999",
        "4-février-2002": "04/02/2002",
        "09/12/2020": "09/12/2020",
    }
    for brut, res in attendu.items():
        assert f(brut) == res, (brut, f(brut))


def test_date_signature_dans_le_texte():
    assert date_signature("Fait à Bordeaux, au siège de la Communauté urbaine, le  1 6 MAI 2006") == "16/05/2006"
    assert date_signature("notification, Fait à Lille, le 1 5 MA1 2000 Pour le Président") == "15/05/2000"
    assert date_signature("Fait à Bron, le4-février-2002\nLe Préfet, par délégation") == "04/02/2002"
    assert date_signature("Lyon, le 09/12/2020\nPour le Président de la Métropole de Lyon") == "09/12/2020"
    assert date_signature("À Nantes, le 3 mai 2021") == "03/05/2021"
    assert date_signature("Fait à Livry-Gargan, le - 4 DEC. 2017") == "04/12/2017"   # tampon relu


def test_date_signature_jamais_inventee():
    assert date_signature("Fait à Livry-Gargan, le - & [IEC. 2017") == ""
    assert date_signature("Le présent arrêté, le 12/12/2012 sera publié") == ""
    assert date_signature("Monsieur le Maire, le 3 mai 2020") == ""
    assert date_signature("Délivré pour la période du 01/02/2021") == ""


# --------------------------------------------------------------------------
# 7. Département / Commune / Date (LLM simulé)
# --------------------------------------------------------------------------
def test_reponse_llm_sur_une_ligne_lille():
    texte = "COMMUNAUTÉ URBAINE DE LILLE\nFait à Lille, le 1 5 MA1 2000 Pour le Président"
    rep = ("assistant\nDépartement : Communauté Urbaine de Lille\nCommune concernée : Lille\n"
           "Date de signature : non trouvée\n<r> Département : Communauté Urbaine de Lille "
           "Commune concernée : Lille Date de signature : 1 5 MA1 2000 </r>")
    out = pmv.prompt_general_com(texte, faux_client(rep), "gpt-5", pmv.FRENCH_DEPARTMENTS)
    assert "Département : Communauté Urbaine de Lille" in out
    assert "Commune concernée : Lille" in out
    assert "Date de signature : 15/05/2000" in out


def test_date_inventee_par_le_llm_rejetee():
    texte = "COMMUNAUTÉ URBAINE DE LILLE\nFait à Lille, le 1 5 MA1 2000"
    rep = "<r>\nDépartement : Communauté Urbaine de Lille\nCommune concernée : Lille\nDate de signature : 4 décembre 2017\n</r>"
    out = pmv.prompt_general_com(texte, faux_client(rep), "gpt-5", pmv.FRENCH_DEPARTMENTS)
    assert "4 décembre" not in out and "04/12/2017" not in out


# --------------------------------------------------------------------------
# 8. Garde-fou final
# --------------------------------------------------------------------------
TEXTE_BORDEAUX = """COMMUNAUTÉ URBAINE DE BORDEAUX
ARRÊTÉ N° 2006-123
Travaux rue Sainte-Catherine à BORDEAUX
Communauté urbaine est chargé de l’exécution du présent arrêté.
Fait à Bordeaux, au siège de la Communauté urbaine, le  1 6 MAI 2006
Pour le président, Par délégation, le vice-président Henri Houdebert"""


def test_garde_fou_rejette_les_phrases():
    df = pd.DataFrame([{
        "Nom Bailleur": "BORDEAUX Commune concernée : What you can do depends on how",
        "Commune concernée": "What you can do depends on how",
        "Date de signature": "Non trouvé",
        "Référence bailleur": "Communauté urbaine est chargé de l’exécution du présent arrêté.",
        "Durée de l'autorisation": "assistant",
        "Modalités de renouvellement": "Pour le président, Par délégation, le vice-président Henri Houdebert",
    }])
    out = pmv.garde_fou_df(df, TEXTE_BORDEAUX).iloc[0]
    for col in ["Nom Bailleur", "Commune concernée", "Référence bailleur",
                "Durée de l'autorisation", "Modalités de renouvellement"]:
        assert out[col] == "Non trouvé", (col, out[col])
    assert pmv._normaliser_date_fr(out["Date de signature"]) == "16/05/2006"


def test_garde_fou_garde_les_bonnes_valeurs():
    bon = {"Nom Bailleur": "COMMUNAUTÉ URBAINE DE BORDEAUX", "Commune concernée": "BORDEAUX",
           "Référence bailleur": "2006-123", "Adresse des travaux": "rue Sainte-Catherine à BORDEAUX",
           "Longueur génie civil": "120 ml", "Nbr de chambres": "2 & 3",
           "Modalités de renouvellement": "La permission est renouvelable sur demande adressée deux mois avant son échéance."}
    out = pmv.garde_fou_df(pd.DataFrame([bon]), TEXTE_BORDEAUX).iloc[0].to_dict()
    for k, v in bon.items():
        assert out[k] == v, (k, out[k])


# --------------------------------------------------------------------------
# 9. GC et chambres sur un formulaire (Clermont)
# --------------------------------------------------------------------------
FORMULAIRE_CLERMONT = pmv._normaliser_lignes_formulaire("""Nature des ouvrages implantés :  réalisation de conduite multiple
Artère aérienne (en ml)
Artère souterraine (en ml)  171
Cabine (emprise au sol en m²)
Chambre (quantité)  3
Support (quantité)""")


def test_gc_formulaire():
    for rep in ["", "Longueur génie civil : 171 ml"]:
        out = pmv.extract_longueur_gc(FORMULAIRE_CLERMONT, faux_client(rep), "gpt-5")
        assert out == "Longueur génie civil : 171 ml", (rep, out)


def test_chambres_formulaire():
    for rep in ["", "<r>\nChambres : 3\n</r>"]:
        out = pmv.extract_chambres_from_text(FORMULAIRE_CLERMONT, faux_client(rep), "gpt-5")
        assert out == "Chambres : 3", (rep, out)


def test_largeur_jamais_prise_pour_gc():
    t = pmv._normaliser_lignes_formulaire("Tranchée (largeur en m) 0,40\nProfondeur de tranchée (en m) 0,80")
    assert "non trouv" in pmv.extract_longueur_gc(t, faux_client(""), "gpt-5").lower()



# --------------------------------------------------------------------------
# 10. Tableaux à bordures (Rosny-sous-Bois) — relecture ciblée
# --------------------------------------------------------------------------
def _page_avec_tableau():
    """Page synthétique 1654x2339 (A4 à 200 DPI) avec un tableau à bordures."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (1654, 2339), "white")
    d = ImageDraw.Draw(img)
    x0, x1 = 400, 1200
    ys = [800, 840, 880, 920, 960, 1000, 1040, 1080]
    for y in ys:
        d.line([(x0, y), (x1, y)], fill="black", width=2)
    for x in (x0, x1):
        d.line([(x, ys[0]), (x, ys[-1])], fill="black", width=2)
    return img


def _B(t, x0, y0, x1, y1):
    return {"text": t, "topLeftCoord": [x0, y0], "bottomRightCoord": [x1, y1], "confidence": 0.95}


TEXTE_ROSNY = """OBJET DEL'AUTORISATION
AVENUE DU PRESIDENT-JOHN-KENNEDY EX-RN 302 à ROSNY-SOUS-BOIS
Nbre de fourreaux
2
ARTICLE 2. - PRESCRIPTIONS TECHNIQUES
2"""

PREMIERE_LECTURE = {"bounds": {
    "0": _B("AVENUE DU PRESIDENT-JOHN-KENNEDY EX-RN 302 à ROSNY-SOUS-BOIS", 300, 740, 1300, 770),
    "1": _B("Nbre de fourreaux", 410, 845, 600, 875),
    "2": _B("2", 500, 885, 515, 915),
    "3": _B("ARTICLE 2. - PRESCRIPTIONS TECHNIQUES", 100, 1150, 800, 1180)}}


class _MoteurTableau:
    """Relecture du tableau : renvoie toutes les cellules (coordonnées du recadrage)."""
    def __init__(self, cellules):
        self.cellules = cellules

    def ocr(self, _png):
        return {"text": "", "bounds": {str(i): c for i, c in enumerate(self.cellules)}}


CELLULES_ROSNY = [  # (texte, x, rangée)
    ("Linéaire de fourreaux (en ml)", 600, 0),
    ("Nbre de fourreaux", 20, 1), ("Type de fourreaux", 500, 1), ("ml", 1100, 1), ("Sous-total 1", 1500, 1),
    ("2", 200, 2), ("Ø60", 700, 2), ("46,50", 1100, 2), ("93,00", 1500, 2),
    ("Chambres", 800, 3),
    ("Nbre de chambres", 300, 4), ("Type de chambre", 1300, 4),
    ("1", 500, 5), ("L3T", 1400, 5),
    ("Total linéaire de fourreaux (km)", 200, 6), ("0,093", 1500, 6)]


def test_tableau_relu_cellule_par_cellule():
    _besoin("_relire_tableaux")
    cellules = [_B(t, x, 30 + r * 80, x + 150, 70 + r * 80) for t, x, r in CELLULES_ROSNY]
    out, n = pmv._relire_tableaux(TEXTE_ROSNY, PREMIERE_LECTURE, _page_avec_tableau(), _MoteurTableau(cellules))
    assert n == 1
    lignes = out.splitlines()
    i = lignes.index("Nbre de fourreaux  Type de fourreaux  ml  Sous-total 1")
    assert lignes[i - 1] == "Linéaire de fourreaux (en ml)"
    assert lignes[i + 1] == "2  Ø60  46,50  93,00"
    assert "Nbre de chambres  Type de chambre" in lignes
    assert "1  L3T" in lignes
    assert "Total linéaire de fourreaux (km)  0,093" in lignes
    assert lignes[1].startswith("AVENUE DU PRESIDENT")          # avant le tableau : intact
    assert lignes[-2] == "ARTICLE 2. - PRESCRIPTIONS TECHNIQUES"  # après : intact
    assert lignes[-1] == "2"                                      # un "2" isolé ailleurs n'est pas retiré


def test_tableau_relecture_sans_gain_ne_change_rien():
    _besoin("_relire_tableaux")
    cellules = [_B("Nbre de fourreaux", 20, 110, 170, 150), _B("2", 200, 190, 215, 230)]
    out, n = pmv._relire_tableaux(TEXTE_ROSNY, PREMIERE_LECTURE, _page_avec_tableau(), _MoteurTableau(cellules))
    assert n == 0 and out == TEXTE_ROSNY


def test_page_sans_tableau_jamais_relue():
    _besoin("_detecter_tableaux")
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (1654, 2339), "white")
    ImageDraw.Draw(img).line([(100, 500), (1500, 500)], fill="black", width=2)   # simple trait
    assert pmv._detecter_tableaux(img) == []


# --------------------------------------------------------------------------
# 11. Fourreaux « 3 fourreaux sur 124 ml et 2 fourreaux sur 76 ml » (D95 Rte de Pitre)
# --------------------------------------------------------------------------
def _ligne_finale_fourreaux(texte, reponse):
    out = pmv.llm_extract_fourreaux(texte, faux_client(reponse), "gpt-5")
    df = pd.concat([pd.DataFrame({"Longueur génie civil": ["Non trouvé"]}), pmv.fourreaux_to_df(out)], axis=1)
    df = pmv.normaliser_unite_ml_df(df)
    return pmv.fusionner_longueur_gc_totale(df).iloc[0]


def test_longueur_par_groupe_va_dans_longueur_par_fourreau():
    texte = "Pose de 3 fourreaux sur 124 ml et 2 fourreaux sur 76 ml rue de Pitre."
    rep = "<r>\nNombre de fourreaux : 3 & 2\nLongueur par fourreau : Non trouvé\nLongueur totale : 124 ml & 76 ml\n</r>"
    row = _ligne_finale_fourreaux(texte, rep)
    assert row["Longueur par fourreau"] == "124 ml & 76 ml"
    assert pmv._is_missing_value(row["Longueur génie civil"])        # plus recopié dans GC
    assert row["Nombre de fourreaux"] == "3 & 2"


def test_longueur_par_groupe_autres_formulations():
    rep = "<r>\nNombre de fourreaux : 3 & 2\nLongueur par fourreau : Non trouvé\nLongueur totale : 124 ml & 76 ml\n</r>"
    for texte in ["Pose de 124 ml de 3 fourreaux Ø45 et 76 ml de 2 fourreaux Ø45.",
                  "3 fourreaux sur 124 ml et 2 fourreaux sur 76 ml.\nRedevance : Total 152,40 euros"]:
        row = _ligne_finale_fourreaux(texte, rep)
        assert row["Longueur par fourreau"] == "124 ml & 76 ml", texte
        assert pmv._is_missing_value(row["Longueur génie civil"]), texte


def test_vrai_total_toujours_recopie_dans_gc():
    texte = "Pose de 3 fourreaux. Longueur totale des fourreaux : 200 ml."
    rep = "<r>\nNombre de fourreaux : 3\nLongueur par fourreau : Non trouvé\nLongueur totale : 200 ml\n</r>"
    row = _ligne_finale_fourreaux(texte, rep)
    assert row["Longueur génie civil"] == "200 ml"


# --------------------------------------------------------------------------
# 12. Référence bailleur (Seine-Saint-Denis : « ARRÊTÉ Nº PV2017-612 »)
# --------------------------------------------------------------------------
TEXTE_SSD = """seine saint Denis LE DÉPARTEMENT
PÔLE AMÉNAGEMENT ET DÉVELOPPEMENT DURABLES
ORIGINAL
ARRÊTÉ Nº PV2017-612
Vu le Code de la voirie routière ;"""


def test_reference_bailleur_ssd():
    for rep in ["PV2017-612", "N° PV2017-612", "Nº PV2017-612"]:
        ref = pmv.extract_ref_bailleur_llm(TEXTE_SSD, faux_client(rep), "gpt-5")
        assert ref == "PV2017-612", (rep, ref)
        df = pmv.garde_fou_df(pmv.ref_bailleur_to_df(ref), TEXTE_SSD)
        assert df["Référence bailleur"][0] == "PV2017-612"


def test_reference_inventee_rejetee():
    assert pmv.extract_ref_bailleur_llm(TEXTE_SSD, faux_client("PV2018-999"), "gpt-5") == "Non trouvé"


# --------------------------------------------------------------------------
# 13. Paddle : relecture des seules zones d'encre non lues
# --------------------------------------------------------------------------
def _page_mots(lignes):
    """Page A4 200 DPI ; chaque ligne = suite de petits pavés noirs (comme des lettres)."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (1654, 2339), "white")
    d = ImageDraw.Draw(img)
    boites = []
    for (x, y, n) in lignes:
        for k in range(n):
            d.rectangle([x + k * 14, y, x + k * 14 + 9, y + 18], fill="black")
        boites.append((x, y, x + n * 14, y + 18))
    d.line([(100, 1500), (1500, 1500)], fill="black", width=2)      # un trait seul
    return img, boites


def _bloc(t, b):
    return {"text": t, "topLeftCoord": [b[0], b[1]], "bottomRightCoord": [b[2], b[3]], "confidence": 0.98}


class _MoteurZones:
    def __init__(self, texte):
        self.texte, self.appels = texte, 0

    def ocr(self, _png):
        self.appels += 1
        return {"bounds": {"0": {"text": self.texte, "topLeftCoord": [0, 0],
                                 "bottomRightCoord": [500, 40], "confidence": 0.95}}}


def test_zone_ratee_relue_et_inseree_a_sa_place():
    _besoin("_relire_zones_manquees")
    img, b = _page_mots([(150, 200, 30), (150, 260, 40), (150, 320, 25), (150, 2000, 30)])
    res = {"bounds": {"0": _bloc("ARTICLE 1 - AUTORISATION", b[0]),
                      "1": _bloc("Le pétitionnaire est autorisé", b[1]),
                      "3": _bloc("ARTICLE 2 - PRESCRIPTIONS", b[3])}}      # la 3e ligne est ratée
    page = "ARTICLE 1 - AUTORISATION\nLe pétitionnaire est autorisé\nARTICLE 2 - PRESCRIPTIONS"
    moteur = _MoteurZones("Fait à Livry-Gargan, le 4 DEC. 2017")
    out, n = pmv._relire_zones_manquees(page, res, img, moteur)
    assert n == 1 and moteur.appels == 1
    assert out.splitlines() == ["ARTICLE 1 - AUTORISATION", "Le pétitionnaire est autorisé",
                                "Fait à Livry-Gargan, le 4 DEC. 2017", "ARTICLE 2 - PRESCRIPTIONS"]


def test_page_bien_lue_aucun_ocr_en_plus():
    _besoin("_relire_zones_manquees")
    img, b = _page_mots([(150, 200, 30), (150, 260, 40)])
    res = {"bounds": {"0": _bloc("ARTICLE 1", b[0]), "1": _bloc("Le pétitionnaire", b[1])}}
    moteur = _MoteurZones("NE DOIT PAS APPARAITRE")
    out, n = pmv._relire_zones_manquees("ARTICLE 1\nLe pétitionnaire", res, img, moteur)
    assert n == 0 and moteur.appels == 0 and out == "ARTICLE 1\nLe pétitionnaire"


def test_relecture_peu_sure_ignoree():
    _besoin("_relire_zones_manquees")
    img, b = _page_mots([(150, 200, 30), (150, 320, 25)])
    res = {"bounds": {"0": _bloc("ARTICLE 1", b[0])}}

    class _Flou(_MoteurZones):
        def ocr(self, _png):
            self.appels += 1
            return {"bounds": {"0": {"text": "X'qe.", "topLeftCoord": [0, 0],
                                     "bottomRightCoord": [50, 20], "confidence": 0.41}}}
    out, n = pmv._relire_zones_manquees("ARTICLE 1", res, img, _Flou(""))
    assert n == 0 and out == "ARTICLE 1"


# --------------------------------------------------------------------------
# 14. Repli Azure : quand une page Paddle est-elle jugée mauvaise ?
# --------------------------------------------------------------------------
PAGE_BIEN_LUE = ("ARTICLE 1 - AUTORISATION. Le pétitionnaire est autorisé à occuper le domaine "
                 "public routier départemental comme indiqué ci-dessous, avenue du Président "
                 "Kennedy à Rosny-sous-Bois, pour la pose de deux fourreaux.")


def test_page_bien_lue_reste_paddle():
    _besoin("_ocr_mauvaise_qualite")
    assert pmv._ocr_mauvaise_qualite(PAGE_BIEN_LUE, {"confiance": 0.95}) is None
    assert pmv._ocr_mauvaise_qualite(PAGE_BIEN_LUE, {"confiance": 0.95, "zones_relues": 2}) is None


def test_page_mal_lue_part_sur_azure():
    _besoin("_ocr_mauvaise_qualite")
    assert pmv._ocr_mauvaise_qualite(PAGE_BIEN_LUE, {"confiance": 0.70})              # confiance basse
    assert pmv._ocr_mauvaise_qualite(PAGE_BIEN_LUE, {"confiance": 0.95, "zones_relues": 3})
    assert pmv._ocr_mauvaise_qualite("e s  e  e ARIIII llll", {"confiance": 0.95})  # presque vide
    charabia = PAGE_BIEN_LUE + " " + " ".join(["xqz", "brr", "tkl", "zzv"] * 40)
    assert pmv._ocr_mauvaise_qualite(charabia, {"confiance": 0.95})               # trop de charabia


# --------------------------------------------------------------------------
# 15. « 2 artères souterraines de 10 ml chacune »
# --------------------------------------------------------------------------
TEXTE_ARTERES = """Article 2 - Nature des ouvrages
Les ouvrages représentent :
· 2 artères souterraines de 10 ml chacune,
· 2 chambres de télécommunications,
le tout sur chaussée."""


def test_arteres_chacune_modele_muet():
    rep = "<r>\nNombre de fourreaux : Non trouvé\nLongueur par fourreau : Non trouvé\nLongueur totale : Non trouvé\n</r>"
    out = pmv.llm_extract_fourreaux(TEXTE_ARTERES, faux_client(rep), "gpt-5")
    assert out.splitlines() == ["Nombre de fourreaux : 2", "Longueur par fourreau : 10 ml", "Longueur totale : 20 ml"], out


def test_arteres_reponse_du_modele_gardee():
    rep = "<r>\nNombre de fourreaux : 2\nLongueur par fourreau : 10 ml\nLongueur totale : Non trouvé\n</r>"
    out = pmv.llm_extract_fourreaux(TEXTE_ARTERES, faux_client(rep), "gpt-5")
    assert "Nombre de fourreaux : 2" in out and "Longueur par fourreau : 10 ml" in out


def test_deux_arteres_en_lettres():
    texte = "Les ouvrages représentent deux artères souterraines de 12,5 ml chacune."
    rep = "<r>\nNombre de fourreaux : Non trouvé\nLongueur par fourreau : Non trouvé\nLongueur totale : Non trouvé\n</r>"
    out = pmv.llm_extract_fourreaux(texte, faux_client(rep), "gpt-5")
    assert "Nombre de fourreaux : 2" in out and "Longueur totale : 25 ml" in out, out

# --------------------------------------------------------------------------
if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    echecs = ignores = 0
    for nom, f in tests:
        try:
            f()
            print(f"OK     {nom}")
        except unittest.SkipTest as e:
            ignores += 1
            print(f"IGNORÉ {nom} ({e})")
        except Exception as e:  # noqa: BLE001
            echecs += 1
            print(f"ÉCHEC  {nom} -> {type(e).__name__}: {e}")
    lances = len(tests) - ignores
    print(f"\n[{_NOM_MODULE}] {lances - echecs}/{lances} tests OK" + (f", {ignores} ignorés" if ignores else ""))
    raise SystemExit(1 if echecs else 0)
