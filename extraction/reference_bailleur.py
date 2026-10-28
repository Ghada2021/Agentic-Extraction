"""Colonne « Référence bailleur ».
Code repris tel quel de pmv_api.py (aucune modification)."""
from ._base import *  # noqa: F401,F403


# ====================================================================
#                         BAILLEUR (référence)
# ====================================================================
def _nettoyer_lignes_vu(texte: str) -> str:
    """Supprime les lignes 'Vu ...' des arrêtés français."""
    lignes = texte.splitlines()
    lignes_filtrees = []
    dans_bloc_vu = False

    for ligne in lignes:
        debut_vu = re.match(r"^\s*[-•·*]?\s*[Vv][Uu]\b", ligne)

        if debut_vu:
            dans_bloc_vu = True
            continue

        if dans_bloc_vu:
            ligne_strippee = ligne.strip()
            if ligne_strippee == "":
                dans_bloc_vu = False
                lignes_filtrees.append(ligne)
                continue
            if ligne.startswith((" ", "\t")) or re.match(r"^[a-zà-ÿ]", ligne_strippee):
                continue
            dans_bloc_vu = False

        lignes_filtrees.append(ligne)

    return "\n".join(lignes_filtrees)


@trace_step('texte_extrait')
def extract_ref_bailleur_llm(texte_extrait: str, client, deployment, first_page_only: bool = True) -> str:
    """Extrait la référence bailleur via LLM (1ère page, filtrage 'Vu', anti-hallucination)."""
    if first_page_only:
        if "\f" in texte_extrait:
            page = texte_extrait.split("\f", 1)[0]
        else:
            lignes = texte_extrait.splitlines()
            page = "\n".join(lignes[:60])
    else:
        page = texte_extrait[:6000]

    page_nettoyee = _nettoyer_lignes_vu(page)

    prompt = f"""
Tu es un extracteur ULTRA STRICT de référence administrative.

OBJECTIF :
Extraire UNIQUEMENT la référence administrative DU DOCUMENT COURANT :
numéro d'arrêté, numéro d'autorisation, numéro d'acte, référence bailleur,
référence chantier ou référence administrative équivalente.

RÈGLE ABSOLUE :
- La référence retournée doit apparaître TEXTUELLEMENT dans le texte fourni.
- N'invente JAMAIS.
- Ne reconstruis pas un code absent.
- Ne complète pas une référence partielle.
- Si aucune référence fiable n'est trouvée, réponds exactement :
Non trouvé

==================================================
1) OÙ CHERCHER EN PRIORITÉ
==================================================

Cherche d'abord dans :

1. l'en-tête du document ;
2. le titre ;
3. les premières lignes ;
4. les lignes contenant explicitement un libellé de référence.

Libellés prioritaires possibles :

- Arrêté n°
- Arrêté N°
- Arrêté municipal n°
- Arrêté municipal N°
- Autorisation n°
- Autorisation N°
- Référence
- Réf.
- Réf
- Réf bailleur
- Réf chantier
- Nos réf
- Notre réf
- Numéro de l'acte
- N° de l'acte
- N° arrêté
- N° autorisation

Un code précédé de « N° », placé sous le titre d'une permission de voirie et avant
une formule telle que « Le Président du Conseil ... », est une référence admissible
du document courant, même si le libellé « Référence » ou « Arrêté n° » est absent.
La formule désignant le président ne fait PAS partie du code, même si l'OCR la colle
sur la même ligne : arrête l'extraction avant cette formule.
Des chiffres ou lettres séparés par des espaces ne rendent pas une référence
partielle ou illisible. Recopie ces caractères et leurs espaces tels qu'ils apparaissent.
Ne corrige jamais un caractère OCR et ne déduis pas le code à partir d'une année.

Exemple de structure :
« Permission de voirie valant accord technique préalable
N°07 V 0 1 2 Le Président du Conseil ... »
→ 07 V 0 1 2
Cet exemple illustre uniquement la structure ; utilise les caractères du texte fourni.

==================================================
2) ZONES À IGNORER ABSOLUMENT
==================================================

Ignore complètement toute référence apparaissant uniquement dans :

- une ligne commençant par « Vu », « VU », « Vu le », « VU le » ;
- les visas juridiques ;
- les références à des lois ;
- les références à des codes ;
- les références à des décrets ;
- les références à des arrêtés antérieurs ;
- les délégations de signature ;
- les références réglementaires ;
- les références citées dans le corps du texte comme documents antérieurs ;
- les numéros de pages ;
- les dates ;
- les numéros d'articles ;
- les numéros de routes, RD, RN, PR, PK ;
- les numéros de dossiers techniques qui ne sont pas clairement la référence du document ;
- les numéros de téléphone ;
- les codes postaux ;
- les SIRET/SIREN ;
- les références de plans, câbles, chambres, fourreaux ou équipements techniques.

Une référence trouvée dans une zone « Vu » ne doit JAMAIS être retournée,
même si son format ressemble parfaitement à un numéro d'arrêté.

==================================================
3) RÈGLE DE SÉLECTION
==================================================

La référence cherchée doit être associée AU DOCUMENT COURANT.

Privilégie donc :

1. une référence explicitement liée à « Arrêté », « Autorisation », « Acte », « Référence » ;
2. une référence située dans le titre ou l'en-tête principal ;
3. une référence située avant les lignes « Vu » ;
4. une référence clairement présentée comme identifiant administratif du document.

Si plusieurs références sont candidates :
- choisis celle qui est la plus explicitement liée au document courant ;
- sinon choisis celle qui apparaît le plus haut dans le document ;
- ne choisis pas une référence citée comme document antérieur.

==================================================
4) FORMAT DE LA VALEUR À RETOURNER
==================================================

Retourne uniquement le CODE ou la RÉFÉRENCE,
sans le préfixe « N° », « n° », « Réf », « Référence », « Arrêté », « Autorisation ».

Exemples :

« Arrêté n° 2021-0081 »
→ 2021-0081

« Arrêté Municipal N°IV-2022-2123-02 »
→ IV-2022-2123-02

« Autorisation n° 19-AV-0541 »
→ 19-AV-0541

« Réf bailleur : PV 20 VI 004 »
→ PV 20 VI 004

« Nos réf : DGAST/SEER/CD/OD »
→ DGAST/SEER/CD/OD

« Numéro de l'acte : 2024/AR/142 »
→ 2024/AR/142

Si le texte contient :

« N° 2024-125 »

et que le contexte montre clairement qu'il s'agit de la référence du document :
→ 2024-125

==================================================
5) FORMATS POSSIBLES
==================================================

La référence peut contenir :

- chiffres ;
- lettres ;
- tirets ;
- slashs « / » ;
- espaces ;
- points ;
- combinaisons alphanumériques.

Exemples de formats possibles :

2021-0081
IV-2022-2123-02
19-AV-0541
PV 20 VI 004
DGAST/SEER/CD/OD
2024/AR/142

Ces exemples servent uniquement à reconnaître la structure.
Ne retourne jamais un exemple s'il n'est pas réellement présent dans le texte.

==================================================
6) NE PAS CONFONDRE AVEC DES CODES TECHNIQUES
==================================================

Ne retourne pas comme référence administrative :

- L2T
- L3T
- K2C
- K3C
- DN40
- Ø63
- RD61
- RN7
- PR12
- PK5
- références de câbles ;
- références de plans ;
- références de chambres ;
- références de fourreaux ;
- codes d'équipements.

Un code technique n'est admissible que s'il est explicitement présenté
comme « Référence », « Réf chantier », « Réf bailleur », « N° d'acte »,
« Arrêté n° » ou équivalent.

==================================================
7) CAS AMBIGUS
==================================================

Si tu vois plusieurs codes mais qu'aucun n'est clairement identifié
comme référence du document courant :

→ Non trouvé

Si un code apparaît uniquement après « Vu » :

→ Non trouvé

Si seul un numéro de page, une date ou une référence légale est présent :

→ Non trouvé

Si la référence est tronquée ou illisible :

→ Non trouvé

==================================================
8) SORTIE OBLIGATOIRE
==================================================

Réponds UNIQUEMENT avec :

[référence]

ou :

Non trouvé

Aucun commentaire.
Aucune explication.
Aucun préfixe.
Aucun Markdown.
Aucun texte avant.
Aucun texte après.

==================================================
TEXTE
==================================================

\"\"\"
{page_nettoyee}
\"\"\"


Référence :"""

    try:
        response = traced_completion(client.chat.completions.create, 
            model=deployment,
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=4000,  # GPT-5 : inclut les tokens de réflexion (était 30)
        )
        raw = (response.choices[0].message.content or "").strip()
    except Exception as e:
        print(f"[extract_ref_bailleur_llm] Azure OpenAI error: {e}")
        return "Non trouvé"

    raw = re.sub(r"^[Nn]\s*[°ºo]\s*", "", raw)
    raw = raw.strip().strip(".-•:\"'").strip()
    raw = raw.split("\n")[0].strip()

    if not raw or raw.count(" ") > 5 or len(raw) > 50:
        return "Non trouvé"
    if raw.lower() in ("non trouvé", "non trouve", "aucun", "aucune", "néant", "n/a"):
        return "Non trouvé"

    norm_page_complete = re.sub(r"\s+", "", page).lower()
    norm_page_nettoyee = re.sub(r"\s+", "", page_nettoyee).lower()
    norm_raw = re.sub(r"\s+", "", raw).lower()

    if norm_raw not in norm_page_complete:
        return "Non trouvé"

    if norm_raw not in norm_page_nettoyee:
        return "Non trouvé"

    return raw


def ref_bailleur_to_df(ref: str, none_for_missing: bool = False) -> pd.DataFrame:
    val = ref
    if none_for_missing and (not val or str(val).lower().startswith("non trouv")):
        val = None
    return pd.DataFrame({"Référence bailleur": [val]})
