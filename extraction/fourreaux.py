"""Colonnes « Nombre de fourreaux », « Longueur par fourreau », « Longueur totale ».
Code repris tel quel de pmv_api.py (aucune modification)."""
from ._base import *  # noqa: F401,F403


# ====================================================================
#                         FOURREAUX
# ====================================================================
def _clean_fourreaux_value(v: str) -> str:
    if not isinstance(v, str):
        return v
    v = v.strip()
    v = re.sub(r"(?i)^nombre\s+de\s+fourreaux\s*:\s*", "", v)
    v = re.sub(r"(?i)^longueur\s+par\s+fourreau\s*:\s*", "", v)
    v = re.sub(r"(?i)^longueur\s+totale\s*:\s*", "", v)
    return v.strip()


@trace_step('text')
def llm_extract_fourreaux(text: str, client, deployment, debug: bool = False) -> str:
    """Extraction fourreaux (nombre, longueur par fourreau, longueur totale) via LLM."""
    # Nombres en lettres -> chiffres AVANT le LLM : facilite l'alignement des groupes multiples.
    text = _texte_nombres_en_chiffres(text)
    lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    numbered = "\n".join(f"{i+1:03d}: {l}" for i, l in enumerate(lines))

    
    
    system_msg = (
        "Tu es un extracteur OCR ULTRA STRICT spécialisé dans les tableaux et documents télécom.\n"
        "- Analyse la STRUCTURE logique du texte avant d'extraire une valeur.\n"
        "- Les tableaux OCR peuvent perdre leurs colonnes, retours à la ligne et alignements : "
        "reconstruis les relations entre EN-TÊTES, LIBELLÉS, UNITÉS et VALEURS.\n"
        "- N'invente jamais une valeur.\n"
        "- Ne te base jamais uniquement sur la proximité de deux nombres.\n"
        "- Réponds UNIQUEMENT avec le bloc <r> demandé."
    )

    user_msg = f"""
    Tu reçois un texte OCR pouvant contenir du texte libre et des tableaux dont
    la mise en page a été partiellement perdue.

    Tu dois extraire uniquement :

    <r>
    Nombre de fourreaux : ...
    Longueur par fourreau : ...
    Longueur totale : ...
    </r>

    ==================================================
    PRINCIPE GÉNÉRAL
    ==================================================

    Ne cherche PAS des formats fixes.

    Comprends le rôle de chaque information à partir de :

    1. l'intitulé de la section ;
    2. les en-têtes de colonnes ;
    3. les libellés ;
    4. les unités ;
    5. la relation entre les valeurs d'une même ligne ou d'un même groupe ;
    6. les mots indiquant une valeur unitaire ou totale.

    Les tableaux OCR peuvent être linéarisés et perdre leur alignement visuel.
    Tu dois reconstruire la structure logique du tableau.

    ==================================================
    1. NOMBRE DE FOURREAUX
    ==================================================

    Extrais une QUANTITÉ lorsqu'elle est associée à un concept comme :

    - fourreau / fourreaux
    - gaine / gaines
    - tube / tubes
    - alvéole / alvéoles
    - artère / artères (souterraines) lorsqu'elles sont comptées
      (« 2 artères souterraines ») : une artère = un fourreau
    - nombre / nb / nbre / quantité

    Dans les tableaux télécom, une colonne « Alvéoles » peut représenter
    le nombre de fourreaux.

    Ne confonds jamais cette quantité avec :

    - un diamètre ;
    - un type de fourreau ;
    - une longueur ;
    - une surface ;
    - un numéro de chambre ;
    - un code technique.

    ==================================================
    2. LONGUEUR PAR FOURREAU
    ==================================================

    Extrais une LONGUEUR UNITAIRE uniquement lorsque la structure du texte ou du tableau
    montre que cette longueur correspond à UN fourreau / une gaine / un tube.

    Indices possibles :

    - « par fourreau »
    - « chaque fourreau »
    - « chacun / chacune »
    - une colonne de longueur située sur la même ligne logique qu'un nombre de fourreaux,
    avec une autre colonne « total », « sous-total » ou équivalent ;
    - une structure de tableau montrant clairement :
    quantité + longueur unitaire + total.

    IMPORTANT :

    Le mot « fourreau » à proximité d'une longueur ne suffit pas toujours à dire
    qu'il s'agit d'une longueur unitaire.

    Une longueur ne doit être classée « Longueur par fourreau » que si son rôle
    UNITAIRE est clairement établi par la structure ou le libellé.

    CAS FRÉQUENT — UNE LONGUEUR PAR GROUPE DE FOURREAUX :

    Quand chaque groupe de fourreaux a SA longueur, cette longueur est la longueur
    parcourue par les fourreaux du groupe : c'est une « Longueur par fourreau »,
    JAMAIS une « Longueur totale ».

    Exemples :

    « 3 fourreaux sur 124 ml et 2 fourreaux sur 76 ml »
    → Nombre de fourreaux : 3 & 2
    → Longueur par fourreau : 124 ml & 76 ml
    → Longueur totale : Non trouvé

    « pose de 124 ml de 3 fourreaux Ø45 et 76 ml de 2 fourreaux Ø45 »
    → Nombre de fourreaux : 3 & 2
    → Longueur par fourreau : 124 ml & 76 ml
    → Longueur totale : Non trouvé

    « 2 artères souterraines de 10 ml chacune »
    → Nombre de fourreaux : 2
    → Longueur par fourreau : 10 ml
    → Longueur totale : 20 ml   (« chacune » rend le calcul explicite)

    « 2 fourreaux Ø60 sur une longueur de 46,50 ml »
    → Nombre de fourreaux : 2
    → Longueur par fourreau : 46,50 ml
    → Longueur totale : Non trouvé (sauf si un total est écrit ailleurs)

    ==================================================
    3. LONGUEUR TOTALE
    ==================================================

    Extrais une LONGUEUR GLOBALE lorsqu'elle correspond au total du linéaire
    des fourreaux / gaines / tubes / câbles concernés.

    Indices forts :

    - total
    - sous-total
    - linéaire total
    - longueur totale
    - total linéaire
    - longueur des fourreaux
    - longueur fourreaux
    - longueur fourreaux ou câbles
    - somme globale explicitement présentée dans le tableau

    Un total explicite est toujours prioritaire sur une déduction ou un calcul.

    « Longueur totale » = UNE valeur globale ÉCRITE comme total dans le document
    (total, sous-total, linéaire total, longueur totale…).
    Plusieurs longueurs de groupes (« 124 ml & 76 ml ») ne sont JAMAIS une longueur
    totale : elles vont dans « Longueur par fourreau ».

    ==================================================
    4. TABLEAUX OCR
    ==================================================

    Lorsqu'un tableau est présent :

    - identifie d'abord le TITRE ou la SECTION ;
    - identifie ensuite les EN-TÊTES de colonnes ;
    - rattache chaque valeur au bon en-tête ;
    - ne suppose jamais qu'un nombre appartient à la colonne la plus proche dans le texte OCR ;
    - utilise la cohérence globale du tableau.

    Par exemple, une structure logique peut être :

    Quantité | Type | Longueur | Sous-total

    Dans ce cas :

    - Quantité → Nombre de fourreaux
    - Type → à ignorer
    - Longueur → peut être une longueur unitaire
    - Sous-total → longueur totale

    Mais cette interprétation doit venir des en-têtes et de la structure réelle,
    pas d'un ordre fixe mémorisé.

    ==================================================
    5. DIFFÉRENCE GC / FOURREAUX
    ==================================================

    Ne confonds jamais :

    - Longueur de Génie Civil / GC / tranchée
    avec
    - Longueur de fourreaux.

    Une section comme :

    « Génie Civil »
    « Longueur »
    « Alvéoles »

    peut signifier :

    - Longueur = longueur GC
    - Alvéoles = nombre de fourreaux

    Dans ce cas, la longueur GC ne doit PAS être copiée automatiquement
    dans « Longueur par fourreau » ni dans « Longueur totale ».

    La présence d'un nombre de fourreaux à côté d'une longueur GC ne signifie
    pas que cette longueur s'applique à chaque fourreau.

    ==================================================
    6. NE PAS CALCULER SAUF RELATION EXPLICITE
    ==================================================

    Ne calcule rien par défaut.

    Ne multiplie jamais :

    longueur GC × nombre de fourreaux.

    Ne calcule une longueur totale à partir d'une quantité et d'une longueur unitaire
    que si la relation est explicitement établie par :

    - « chacun / chacune »
    - « par fourreau »
    - ou une structure de tableau claire :
    quantité + longueur unitaire + total attendu.

    Si un total explicite existe, utilise toujours le total écrit.

    ==================================================
    7. VALEURS À IGNORER
    ==================================================

    Ne jamais confondre avec :

    - diamètre ;
    - DN ;
    - Ø ;
    - mm ;
    - type PEHD / PVC ;
    - référence technique ;
    - chambres L2T / L3T / K2C / K3C ;
    - surface m² ;
    - volume m³ ;
    - profondeur ;
    - hauteur ;
    - largeur ;
    - distance de sécurité ;
    - PR / PK ;
    - longueur de voie ;
    - longueur de tranchée ;
    - longueur GC non explicitement liée aux fourreaux.

    ==================================================
    8. UNITÉS
    ==================================================

    Pour les longueurs :

    - conserver m ou ml selon le texte ;
    - si un total est donné en km, convertir en mètres ;
    - ne jamais utiliser mm comme longueur de fourreau lorsque mm désigne un diamètre.

    ==================================================
    9. PLUSIEURS GROUPES
    ==================================================

    Si plusieurs groupes indépendants de fourreaux existent :

    - conserve leur ordre d'apparition ;
    - sépare les valeurs par " & ".

    Ne mélange pas deux groupes différents.

    ==================================================
    10. CONTRÔLE FINAL
    ==================================================

    Avant de répondre, vérifie pour chaque valeur :

    Nombre de fourreaux :
    → est-ce bien une quantité ?

    Longueur par fourreau :
    → est-ce bien une longueur UNITAIRE ?

    Longueur totale :
    → est-ce bien une longueur GLOBALE ?

    Si le rôle d'une valeur n'est pas suffisamment clair :
    → Non trouvé

    ==================================================
    FORMAT STRICT
    ==================================================

    <r>
    Nombre de fourreaux : [valeur ou Non trouvé]
    Longueur par fourreau : [valeur ou Non trouvé]
    Longueur totale : [valeur ou Non trouvé]
    </r>

    Aucun commentaire.
    Aucune explication.
    Aucun Markdown.
    Aucun texte avant ou après.

    ==================================================
    TEXTE OCR
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
            max_completion_tokens=4000,  # GPT-5 : inclut les tokens de réflexion (était 300)
        )
        decoded = (response.choices[0].message.content or "").strip()
    except Exception as e:
        print(f"[llm_extract_fourreaux] Azure OpenAI error: {e}")
        decoded = ""

    if debug:
        print("DEBUG LLM (fourreaux) >>>\n", decoded[:2000], "\n<<< END")

    mres = re.search(r"<r>(.*?)</r>", decoded, flags=re.I | re.S)
    if mres:
        block = mres.group(1).strip()
    else:
        mres2 = re.search(r"<r>(.*)", decoded, flags=re.I | re.S)
        block = mres2.group(1).strip() if mres2 else decoded.strip()

    nb_final = "Non trouvé"
    lpf_final = "Non trouvé"
    lt_final = "Non trouvé"

    lines_block = [ln.strip() for ln in block.splitlines() if ln.strip()]

    parsed_by_header = False
    for line in lines_block:
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        key = key.strip().lower()
        val = val.strip()
        if not val or val.lower().startswith("non"):
            parsed_by_header = True
            continue
        if re.search(r"(?:nombre|nbre|nb)", key):
            nb_final = val
            parsed_by_header = True
        elif "par fourreau" in key:
            lpf_final = val
            parsed_by_header = True
        elif "totale" in key:
            lt_final = val
            parsed_by_header = True

    if not parsed_by_header and len(lines_block) >= 3:
        nb_final = lines_block[0]
        lpf_final = lines_block[1]
        lt_final = lines_block[2]

    if nb_final != "Non trouvé":
        if re.search(r"(?i)\b(ml|m|mètres?|metres?)\b", nb_final):
            if lt_final == "Non trouvé":
                lt_final = nb_final
            nb_final = "non trouvé"

    # « 3 fourreaux sur 124 ml et 2 fourreaux sur 76 ml » : 124 et 76 sont la longueur
    # de CHAQUE groupe de fourreaux (longueur par fourreau), pas un total.
    # Si le modèle les a mises en "Longueur totale", on les replace en "Longueur par fourreau".
    _L = r"(\d[\d\s]*(?:[.,]\d+)?)\s*(?:ml|m|mètres?|metres?)\b"
    sur = re.findall(rf"(?i)\b\d+\s*fourreaux?\b[^.\n;]{{0,40}}?\bsur\s+(?:une\s+longueur\s+de\s+)?{_L}", text or "") \
        or re.findall(rf"(?i){_L}\s*(?:de|pour)\s+\d+\s*fourreaux?\b", text or "")
    if sur and lt_final != "Non trouvé" and lpf_final == "Non trouvé":
        def _nums(v):
            return [re.sub(r"\s+", "", n).replace(",", ".") for n in re.findall(r"\d[\d\s]*(?:[.,]\d+)?", v)]
        if _nums(lt_final) == [re.sub(r"\s+", "", n).replace(",", ".") for n in sur]:
            lpf_final, lt_final = lt_final, "Non trouvé"

    # « 2 artères souterraines de 10 ml chacune » / « 3 fourreaux de 50 ml chacun » :
    # si le modèle n'a rien donné, la phrase suffit (quantité + longueur unitaire explicite).
    if nb_final in ("Non trouvé", "non trouvé") and lpf_final == "Non trouvé" and lt_final == "Non trouvé":
        mc = re.search(
            r"(?i)\b(\d+)\s+(?:fourreaux?|gaines?|tubes?|art[èe]res?)(?:\s+souterraines?)?"
            r"[^.\n;]{0,30}?\bde\s+(\d+(?:[.,]\d+)?)\s*(ml|m|mètres?|metres?)\b\s*chacun(?:e)?s?\b",
            text or "")
        if mc:
            n, l_txt = int(mc.group(1)), mc.group(2)
            total = n * float(l_txt.replace(",", "."))
            nb_final = str(n)
            lpf_final = f"{l_txt} ml"
            lt_final = f"{total:g} ml".replace(".", ",")

    return (
        f"Nombre de fourreaux : {nb_final}\n"
        f"Longueur par fourreau : {lpf_final}\n"
        f"Longueur totale : {lt_final}"
    )


def _is_non_trouve(value) -> bool:
    if value is None:
        return True
    text = str(value).strip().lower()
    return (
        text == ""
        or text in {
            "non trouvé", "non trouvée", "non trouve", "non trouvee",
            "non spécifié", "non specifie", "n/a", "na", "none", "null", "-"
        }
        or text.startswith("non trouv")
        or text.startswith("non spécifi")
    )


def _parse_fourreaux_output(result: str) -> dict:
    fields = {
        "Nombre de fourreaux": "non trouvé",
        "Longueur par fourreau": "non trouvé",
        "Longueur totale": "non trouvé",
    }

    if not result:
        return fields

    text = result.replace("<r>", "").replace("</r>", "").strip()

    for line in text.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key in fields:
            fields[key] = _clean_fourreaux_value(value) if value else "Non trouvé"

    return fields


def fourreaux_to_df(output: str, none_for_missing: bool = False) -> pd.DataFrame:
    d = _parse_fourreaux_output(output)
    if none_for_missing:
        d = {k: (None if _is_non_trouve(v) else v) for k, v in d.items()}
    return pd.DataFrame([d])


# --- dépendances utilisées seulement à l'appel des fonctions (importées en fin de module : évite les imports circulaires) ---
from .normalisation import _texte_nombres_en_chiffres  # noqa: E402,F401
