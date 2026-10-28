"""Colonne « Nbr de chambres ».
Code repris tel quel de pmv_api.py (aucune modification)."""
from ._base import *  # noqa: F401,F403


# ====================================================================
#                         CHAMBRES
#  (adaptée à l'API Azure : la version notebook utilisait tokenizer/model
#   local ; ici on passe par le même client que les autres fonctions.)
# ====================================================================
@trace_step('text')
def extract_chambres_from_text(text: str, client, deployment, debug: bool = False) -> str:
    lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    numbered = "\n".join(f"{i+1:03d}: {l}" for i, l in enumerate(lines))

    system_msg = (
    "Assistant d'extraction OCR ULTRA STRICT. Français uniquement.\n"
    "- N'invente JAMAIS de valeur.\n"
    "- Extrais uniquement des informations explicitement présentes dans le texte.\n"
    "- Les codes de type de chambre (L2T, L3T, K2C, K3C, etc.) ne sont JAMAIS des quantités.\n"
    "- Si aucune quantité de chambre fiable n'est identifiable, écris exactement : 'Non trouvé'.\n"
    "- Réponds UNIQUEMENT avec un bloc <r> contenant exactement 1 ligne, rien d'autre."
)

    user_msg = f"""
    Tu reçois un texte OCR avec des lignes numérotées.

    Tu dois extraire UNIQUEMENT :

    <r>
    Chambres : ...
    </r>

    ==================================================
    OBJECTIF
    ==================================================

    Extraire uniquement le NOMBRE DE CHAMBRES TÉLÉCOM mentionnées dans le document.

    Ne retourne jamais :
    - le type de chambre ;
    - une longueur ;
    - un diamètre ;
    - un nombre de fourreaux ;
    - un nombre d'alvéoles ;
    - une référence technique.

    ==================================================
    1) TABLEAUX — PRIORITÉ MAXIMALE
    ==================================================

    Si une information apparaît dans un tableau, elle est prioritaire sur le texte libre.

    Cherche notamment les colonnes ou cellules contenant :

    - Chambre
    - Chambres
    - Nbre de chambres
    - Nb de chambres
    - Nombre de chambres
    - Qté chambres
    - Quantité chambres
    - Chambre existante
    - Chambre à créer
    - Chambre à poser

    La valeur à extraire est UNIQUEMENT la quantité directement associée
    à cette ligne, colonne ou cellule.

    Exemple :

    Type | Quantité
    L2T  | 2

    → Chambres : 2

    Exemple :

    Chambres L2T | 3

    → Chambres : 3

    ATTENTION :

    Dans :

    L2T
    L3T
    K2C
    K3C

    le chiffre contenu dans le code ne représente JAMAIS le nombre de chambres.

    Exemple :

    Chambre L2T

    → ne retourne PAS 2.

    ==================================================
    2) TEXTE LIBRE
    ==================================================

    Extrais une quantité uniquement lorsqu'elle est clairement associée
    au mot « chambre » ou « chambres ».

    Exemples :

    « 2 chambres L2T »
    → Chambres : 2

    « création de 3 chambres »
    → Chambres : 3

    « pose de 4 chambres télécom »
    → Chambres : 4

    « une chambre L3T »
    → Chambres : 1

    « pose d'une chambre L2T »
    → Chambres : 1

    « création d'une chambre »
    → Chambres : 1

    Si le nombre est écrit en lettres, convertis-le en chiffre.

    Exemples :

    « deux chambres »
    → Chambres : 2

    « trois chambres L2T »
    → Chambres : 3

    ==================================================
    3) PLUSIEURS GROUPES
    ==================================================

    Si plusieurs quantités DISTINCTES de chambres sont explicitement indiquées,
    retourne-les dans leur ordre d'apparition, séparées par :

    & 

    Exemple :

    « 2 chambres L2T et 3 chambres L3T »

    → Chambres : 2 & 3

    Exemple :

    « création de 1 chambre L2T et pose de 2 chambres L3T »

    → Chambres : 1 & 2

    Ne calcule PAS le total.

    Exemple :

    « 2 chambres L2T et 3 chambres L3T »

    NE PAS retourner :
    5

    Retourner :
    2 & 3

    ==================================================
    4) CAS SANS QUANTITÉ EXPLICITE
    ==================================================

    Une formulation au SINGULIER qui indique clairement la création,
    la pose ou l'installation d'une chambre correspond à 1 chambre.

    Exemples :

    « pose de chambre L2T »
    → Chambres : 1

    « création de chambre télécom »
    → Chambres : 1

    « mise en place d'une chambre »
    → Chambres : 1

    En revanche, si le mot « chambre » est seulement cité comme référence,
    type, localisation ou équipement existant sans indication de quantité,
    de création ou de pose, ne déduis PAS automatiquement 1.

    Exemple :

    « raccordement vers chambre L2T existante »

    → ne pas déduire automatiquement 1.

    Exemple :

    « au droit de la chambre K2C »

    → ne pas déduire automatiquement 1.

    ==================================================
    5) ÉLÉMENTS À IGNORER
    ==================================================

    Ne jamais utiliser comme quantité de chambres les nombres associés à :

    - fourreaux ;
    - tubes ;
    - artères ;
    - gaines ;
    - canalisations ;
    - alvéoles ;
    - câbles ;
    - conduites ;
    - longueur en m, ml ou km ;
    - surface en m² ;
    - diamètre ;
    - DN ;
    - Ø ;
    - profondeur ;
    - largeur ;
    - hauteur ;
    - numéro de voie ;
    - numéro de ligne OCR ;
    - références techniques.

    Exemples :

    « 4 fourreaux Ø45 »
    → ne signifie PAS 4 chambres.

    « chambre L2T + 3 fourreaux »
    → 3 correspond aux fourreaux, PAS aux chambres.

    « chambre à 25 m »
    → 25 est une longueur, PAS une quantité de chambres.

    « L3T »
    → 3 est inclus dans le TYPE, PAS une quantité.

    ==================================================
    6) ÉVITER LES DOUBLONS
    ==================================================

    Si la même information est répétée plusieurs fois dans le document
    ou reprise dans un tableau et dans le texte, ne la compte pas plusieurs fois.

    Exemple :

    Tableau :
    « Chambres L2T : 2 »

    Puis texte :
    « réalisation de 2 chambres L2T »

    Si ces deux mentions décrivent clairement la même opération :

    → Chambres : 2

    et NON :

    → Chambres : 2 & 2

    ==================================================
    7) ABSENCE DE VALEUR
    ==================================================

    Si aucune quantité de chambre télécom n'est explicitement identifiable :

    <r>
    Chambres : Non trouvé
    </r>

    ==================================================
    FORMAT DE SORTIE
    ==================================================

    Retourne STRICTEMENT :

    <r>
    Chambres : [quantité(s) ou Non trouvé]
    </r>

    Aucun commentaire.
    Aucune explication.
    Aucun Markdown.
    Aucun texte avant <r>.
    Aucun texte après </r>.

    ==================================================
    TEXTE COMPLET — LIGNES NUMÉROTÉES
    ==================================================

    {numbered}
    """.strip()

    try:
        response = traced_completion(client.chat.completions.create, 
            model=deployment,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            max_completion_tokens=2000,  # GPT-5 : inclut les tokens de réflexion
        )
        decoded = (response.choices[0].message.content or "").strip()
    except Exception as e:
        print(f"[extract_chambres_from_text] Azure OpenAI error: {e}")
        decoded = ""

    if debug:
        print("DEBUG LLM (chambres) >>>\n", decoded[:500], "\n<<< END")

    mres = re.search(r"<r>(.*?)</r>", decoded, flags=re.I | re.S)
    if mres:
        block = mres.group(1).strip()
    else:
        mres2 = re.search(r"<r>(.*)", decoded, flags=re.I | re.S)
        block = mres2.group(1).strip() if mres2 else decoded.strip()

    result = "Non trouvé"
    for line in block.splitlines():
        line = line.strip()
        if "chambre" in line.lower() and ":" in line:
            result = line.split(":", 1)[1].strip()
            break

    if result == "Non trouvé":
        clean = re.sub(r"\s+", " ", block).strip()
        if clean and not clean.lower().startswith("non") and re.search(r"\d", clean):
            result = clean

    if not result or result.lower().startswith("non"):
        result = "Non trouvé"

    # Secours sans LLM : ligne de formulaire/tableau « Chambre(s) : 3 »
    # (après _normaliser_lignes_formulaire, « Chambre (quantité)  3 » devient « Chambre : 3 »).
    if result == "Non trouvé":
        for l in lines:
            mq = re.match(r"(?i)^\s*(?:nombre\s+de\s+|nb\s+de\s+|nbre\s+de\s+)?chambres?"
                          r"\s*(?:\((?:quantit[ée]|nombre|nbre|nb|qt[ée])\))?\s*:\s*(\d{1,3})\s*$", l)
            if mq and int(mq.group(1)) > 0:
                result = mq.group(1)
                break

    return f"Chambres : {result}"


def chambres_to_df(output: str, none_for_missing: bool = False) -> pd.DataFrame:
    mm = re.search(r"(?i)Chambres\s*:\s*(.+)", output)
    val = mm.group(1).strip() if mm else "Non trouvé"
    if none_for_missing and val.lower().startswith("non"):
        val = None
    return pd.DataFrame({"Nbr de chambres": [val]})
