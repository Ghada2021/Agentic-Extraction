"""Colonnes « Nom Bailleur », « Commune concernée », « Date de signature » (prompt_general_com).
Code repris tel quel de pmv_api.py (aucune modification)."""
from ._base import *  # noqa: F401,F403


# ====================================================================
#                 DÉPARTEMENT / COMMUNE / SIGNATURE
# ====================================================================
FRENCH_DEPARTMENTS = [
    "Ain","Aisne","Allier","Alpes-de-Haute-Provence","Hautes-Alpes","Alpes-Maritimes","Val de loire","Jura","Métropole de Lille","Sud-est Toulousain","Nantes","BORDEAUX","le mans métropole","le mans","Alpes Martimes",
    "Ardèche","Ardennes","Ariège","Aube","Aude","Aveyron","Bouches-du-Rhône","Calvados","Seine & Oise","Grenoble-Alpes",
    "Cantal","Charente","Charente-Maritime","Cher","Corrèze","Corse-du-Sud","Haute-Corse",
    "Côte-d'Or","Côtes-d'Armor","Creuse","Dordogne","Doubs","Drôme","Eure","Eure-et-Loir",
    "Finistère","Gard","Haute-Garonne","Gers","Gironde","Hérault","Ille-et-Vilaine","Indre","deux serves",
    "Indre-et-Loire","Isère","Jura","Landes","Loir-et-Cher","Loire","Haute-Loire",
    "Loire-Atlantique","Loiret","Lot","Lot-et-Garonne","Lozère","Maine-et-Loire","Manche","Toulouse Métropole","Strasbourg","Bordeaux Métropole","MARSEILLE","MARSEILLE PROVENCE METROPOLE",
    "MARSEILLE MPM PROVENCE METROPOLE", "MPM PROVENCE METROPOLE","GRANDLYON","Nievre","Ville de Reims",
    "Marne","Haute-Marne","Mayenne","Meurthe-et-Moselle","Meuse","Morbihan","Moselle","GRANDLYON","grand dijon",
    "Nièvre","Nord","Oise","Orne","Pas-de-Calais","Puy-de-Dôme","Pyrénées-Atlantiques","ORLÉANS","Paris La Défense","Aix-en-Provence",
    "Hautes-Pyrénées","Pyrénées-Orientales","Bas-Rhin","Haut-Rhin","Rhône","Haute-Saône",
    "Saône-et-Loire","Sarthe","Savoie","Haute-Savoie","Paris","Seine-Maritime","Seine-et-Marne","Saint-Étienne","Narbonne","valde marne","Fontenay-aux-Roses",
    "Yvelines","Deux-Sèvres","Somme","Tarn","Tarn-et-Garonne","Var","Vaucluse","Vendée","yvelines",
    "Vienne","Haute-Vienne","Vosges","Yonne","Territoire de Belfort","Essonne","Hauts-de-Seine","Voies Navigables de France","Toulouse Métropole",
    "Seine-Saint-Denis","Val-de-Marne","Val-d'Oise","Guadeloupe","Martinique","Guyane","IZON","Communauté Urbaine de Lille",
    "La Réunion","Mayotte","Saint-Étienne","essone","Hérault","herault","Montpellier","NICE COTE D'AZUR","valence romans agglo","VNF","Montpellier Méditerranée Métropole","Grand Reims","Deux rives de la Seine","Grand Lyon","Grandlyon",
    "PERPIGNAN","BONNEUIL-SUR-MARNE","Grand port martime","Suresnes","Office National des forets","Albigeois","CLERMONT AUVERGNE METROPOLE","Métropole rouennormandie","clermont auvergne métropole",
]


@trace_step('text')
def prompt_general_com(
    text: str,
    client,
    deployment,
    french_departments: List[str],
    st_model=None,
    debug: bool = False
) -> str:
    """
    Extraction stricte de : Département / Commune concernée / Date de signature.
    """

    def _noacc_lower(s: str) -> str:
        s = unicodedata.normalize("NFKD", s or "")
        s = "".join(ch for ch in s if not unicodedata.combining(ch))
        s = re.sub(r"\s+", " ", s).strip().lower()
        return s

    def _norm_for_span(s: str) -> str:
        s = unicodedata.normalize("NFKD", s or "")
        s = "".join(ch for ch in s if not unicodedata.combining(ch))
        s = re.sub(r"[^0-9a-zA-Z]+", " ", s)
        s = re.sub(r"\s+", " ", s).strip().lower()
        return s

    def _flex_norm(s: str) -> str:
        return re.sub(r"[-''`\s]+", " ", _noacc_lower(s)).strip()

    def _first_occurrence_phrase(text_raw: str, phrase: str) -> int:
        H = _norm_for_span(text_raw)
        P = _norm_for_span(phrase)
        if not H or not P:
            return 10**12
        m = re.search(rf"(?<!\w){re.escape(P)}(?!\w)", H)
        return m.start() if m else 10**12

    def _phrase_present(text_raw: str, phrase: str) -> bool:
        return _first_occurrence_phrase(text_raw, phrase) < 10**12

    official_names = [str(x).strip() for x in french_departments if str(x).strip()]
    official_norm_map = {_noacc_lower(n): n for n in official_names}

    official_set_norm = {_noacc_lower(n) for n in official_names}
    specials = []
    for x in french_departments:
        xs = str(x).strip()
        if not xs:
            continue
        if _noacc_lower(xs) not in official_set_norm:
            specials.append(xs)

    all_known = {}
    for n in official_names:
        all_known[_noacc_lower(n)] = n
    for n in specials:
        all_known.setdefault(_noacc_lower(n), n)

    def _strip_time(date_raw: str) -> str:
        if not date_raw or date_raw.lower().startswith("non trouv"):
            return "non trouvée"
        # Délègue au normaliseur robuste (gère le jour coupé par l'OCR '1 7'->17,
        # 'Le', mois abrégés/bruités, JJ/MM/AAAA). Voir _normaliser_date_fr plus bas.
        return _normaliser_date_fr(date_raw)

    GENERIC_SOLO = {
        "metropole", "métropole",
        "communaute", "communauté",
        "conseil",
        "departement", "département",
        "le departement", "le département",
        "la metropole", "la communauté", "la communaute", "le conseil",
        "prefecture", "préfecture",
    }

    COMMUNE_LIKE_RE = re.compile(r"(?i)^(?:ville\s+de|mairie\s+de|commune\s+de)\b")

    EPCI_LIKE_RE = re.compile(
        r"(?i)(m[ée]tropole|communaut[ée]|agglom[ée]ration|urbaine|intercommunal)"
    )

    ADMIN_PREFIX_RE = re.compile(
        r"(?i)^(?:le\s+)?"
        r"(?:d[ée]partement|conseil\s+d[ée]partemental|conseil\s+g[ée]n[ée]ral|pr[ée]fecture)"
        r"(?:\s+(?:de|du|des|de\s+la|de\s+l['']\s*))?\s*"
    )

    DEPT_HEADER_RE = re.compile(
        r"(?i)d[ée]partement\s+(?:de\s+la\s+|de\s+l['']\s*|de\s+|du\s+|des\s+)"
    )

    ADDRESS_CTX = re.compile(
        r"(?i)\b("
        r"petitionnaire|pétitionnaire|demeurant|adresse|siege|siège|cedex|bp|"
        r"rue|avenue|boulevard|bd|route|chemin|impasse|"
        r"siret|siren|tva|rcs|societe|société"
        r")\b"
    )
    POSTAL_OR_75 = re.compile(r"(?i)\b(75\d{3}|75)\b")

    CONTEXT = re.compile(
        r"(?i)\b(d[ée]partement|conseil\s+d[ée]partemental|conseil\s+g[ée]n[ée]ral|pr[ée]fecture|dept\.?|cd|ddept)\b"
    )

    def _is_in_address_context(H_raw: str, name: str, win: int = 90) -> bool:
        m = re.search(
            rf"(?:(?<=^)|(?<=\W)){re.escape(name)}(?:(?=\W)|$)",
            H_raw,
            flags=re.I
        )
        if not m:
            return False
        s, e = m.start(), m.end()
        local = H_raw[max(0, s - win): min(len(H_raw), e + win)]

        if CONTEXT.search(local):
            return False

        if ADDRESS_CTX.search(local):
            return True

        if name.lower() == "paris" and (POSTAL_OR_75.search(local) or re.search(r"(?i)\bcedex\b", local)):
            return True

        return False

    def _find_first_special_in_header(text_raw: str) -> str:
        header = "\n".join([l.strip() for l in (text_raw or "").splitlines()[:20] if l.strip()])
        specials_sorted = sorted(specials, key=lambda x: _first_occurrence_phrase(header, x))
        for name in specials_sorted:
            if _phrase_present(header, name):
                return name
        return "non trouvée"

    def _flex_match_all_known(candidate: str) -> str:
        fc = _flex_norm(candidate)
        if not fc:
            return "non trouvée"

        for key, val in all_known.items():
            if _flex_norm(key) == fc:
                return val

        # Correspondance en MOT ENTIER uniquement ('ain' ne doit pas matcher 'sainte',
        # 'cher' ne doit pas matcher 'recherche'). Parmi les noms trouvés, on garde
        # le PREMIER dans le texte (puis le plus long), pas le premier de la liste.
        best = None
        for key, val in all_known.items():
            fk = _flex_norm(key)
            if not fk:
                continue
            m = re.search(rf"(?<!\w){re.escape(fk)}(?!\w)", fc)
            if m and (best is None or (m.start(), -len(fk)) < best[0]):
                best = ((m.start(), -len(fk)), val)
        if best:
            return best[1]

        for key, val in all_known.items():
            fk = _flex_norm(key)
            if re.search(rf"(?<!\w){re.escape(fc)}(?!\w)", fk):
                return val

        return "non trouvée"

    lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    head40 = "\n".join(lines[:40])
    numbered = "\n".join(f"{i+1:03d}: {l}" for i, l in enumerate(lines))

    system_msg = (
    "Tu es un assistant d'extraction OCR ULTRA STRICT.\n"
    "\n"
    "RÈGLES ABSOLUES :\n"
    "- N'invente JAMAIS une information.\n"
    "- N'utilise JAMAIS tes connaissances externes pour compléter le texte OCR.\n"
    "- Une valeur retournée doit obligatoirement être présente dans le texte fourni, "
    "sauf lorsqu'une règle demande explicitement de supprimer un préfixe.\n"
    "- Copie les valeurs EXACTEMENT telles qu'elles apparaissent dans le texte OCR.\n"
    "- Ne corrige ni l'orthographe, ni les accents, ni la casse, ni les erreurs OCR.\n"
    "- Tu peux uniquement reconstituer une valeur coupée sur plusieurs lignes OCR consécutives.\n"
    "- Les numéros de lignes OCR ne font jamais partie des valeurs extraites.\n"
    "- Si une valeur n'est pas explicitement identifiable, écris exactement : 'non trouvée'.\n"
    "- En cas de doute ou d'ambiguïté, préfère toujours 'non trouvée'.\n"
    "- Réponds UNIQUEMENT avec un bloc <r> contenant exactement 3 lignes.\n"
    "- Aucun commentaire, aucune justification, aucun texte avant ou après le bloc <r>."
    )

    user_msg = f"""
    Tu reçois un texte OCR avec des lignes numérotées.

    Tu dois extraire EXACTEMENT ces 3 informations, dans cet ordre :

    <r>
    Département : ...
    Commune concernée : ...
    Date de signature : ...
    </r>

    ==================================================
    1) DÉPARTEMENT / BAILLEUR
    ==================================================

    OBJECTIF :

    Le champ « Département » correspond à l'ENTITÉ ADMINISTRATIVE,
    INTERCOMMUNALE ou GESTIONNAIRE DE VOIRIE qui émet le document.

    Cherche cette entité principalement dans le LOGO ou l'EN-TÊTE,
    donc dans les premières lignes du document.

    Elle peut être :

    - un département officiel ;
    - une métropole ;
    - une eurométropole ;
    - une communauté urbaine ;
    - une communauté d'agglomération ;
    - une communauté de communes ;
    - une intercommunalité ;
    - un syndicat ;
    - un gestionnaire de voirie ;
    - VNF ;
    - ou une autre collectivité explicitement identifiée comme émettrice.

    Exemples de formes possibles :

    - Jura
    - Grand Lyon
    - Nantes Métropole
    - Métropole Rouen Normandie
    - Métropole européenne de Lille
    - Eurométropole de Strasbourg
    - Interco Normandie Sud Eure
    - Communauté de communes ...
    - MARSEILLE MPM PROVENCE METROPOLE
    - VNF

    RÈGLES :

    A. NOM COMPLET

    Copie le nom COMPLET de l'entité.
    « Le Département », « Département », « La Métropole » ou « Le Conseil » seuls
    sont des libellés génériques, jamais un nom d'entité suffisant.
    Reconstitue le nom propre du logo lorsqu'il est réparti sur plusieurs lignes.

    Ne réduis jamais une métropole, communauté, interco ou autre collectivité
    à un département officiel.

    Exemples :

    « Grand Lyon »
    → Département : Grand Lyon

    « Métropole Rouen Normandie »
    → Département : Métropole Rouen Normandie

    Ne retourne PAS seulement :
    « Lyon »
    ou
    « Rouen Normandie ».

    --------------------------------------------------

    B. NOM COUPÉ SUR PLUSIEURS LIGNES OCR

    Le nom peut être réparti sur plusieurs lignes OCR consécutives.

    Tu dois alors reconstituer le nom complet.

    Exemple :

    Métropole européenne
    de Lille

    → Département : Métropole européenne de Lille

    Ne combine cependant que des lignes appartenant clairement au même nom.

    --------------------------------------------------

    C. PRÉFIXES ADMINISTRATIFS À SUPPRIMER

    Supprime uniquement les préfixes suivants lorsqu'ils introduisent directement
    le nom de l'entité :

    - DEPARTEMENT DE
    - DÉPARTEMENT DE
    - CONSEIL DEPARTEMENTAL DE
    - CONSEIL DÉPARTEMENTAL DE
    - PREFECTURE DE
    - PRÉFECTURE DE

    Après suppression du préfixe, conserve EXACTEMENT le texte restant.

    Exemple :

    « DEPARTEMENT DE LA VENDEE »

    → Département : LA VENDEE

    Ne corrige pas automatiquement en « Vendée ».

    --------------------------------------------------

    D. MOTS À CONSERVER

    Les mots suivants peuvent faire partie intégrante du nom et ne doivent
    JAMAIS être supprimés :

    - Métropole
    - Eurométropole
    - Communauté
    - Interco
    - Syndicat
    - Grand

    --------------------------------------------------

    E. DIRECTIONS INTERNES À NE PAS CONFONDRE

    Les expressions comme :

    - Agence Routière Nord
    - Agence Routière Sud
    - Agence Routière Est
    - Agence Routière Ouest
    - Pôle Nord
    - Pôle Sud
    - Pôle Est
    - Pôle Ouest
    - Antenne Nord
    - Antenne Sud
    - Antenne Est
    - Antenne Ouest

    peuvent représenter des directions géographiques internes.

    « Nord », « Sud », « Est » ou « Ouest » ne doivent donc pas être
    considérés seuls comme le nom du département ou du bailleur.

    Cherche l'entité administrative principale dans l'en-tête.

    --------------------------------------------------

    F. PLUSIEURS CANDIDATS

    Si plusieurs entités administratives valides sont présentes :

    1. privilégie celle explicitement présentée comme émettrice du document ;
    2. sinon privilégie celle du logo / en-tête principal ;
    3. si plusieurs candidats restent équivalents, prends le PREMIER
    dans l'ordre du texte.

    Ne choisis pas une entreprise, une adresse, une commune ou une direction
    interne simplement parce qu'elle apparaît en premier.

    --------------------------------------------------

    G. CAS PARTICULIER : PARIS

    Ne retourne JAMAIS :

    Département : Paris

    si « Paris » apparaît uniquement :

    - dans une adresse ;
    - dans un code postal ;
    - comme lieu ;
    - comme commune.

    Retourne « Paris » uniquement si le texte établit explicitement
    que Paris est l'entité administrative ou le département émetteur.

    --------------------------------------------------

    H. ABSENCE DE VALEUR

    Si aucune entité fiable n'est identifiable :

    Département : non trouvée


    ==================================================
    2) COMMUNE CONCERNÉE
    ==================================================
    OBJECTIF :
    Extraire UNIQUEMENT le NOM DE LA COMMUNE / VILLE concernée par les travaux.

    La valeur retournée doit être un nom de commune ou de ville.
    Ne retourne JAMAIS une adresse complète, un nom de rue, un numéro de voie ou un code postal seul.

    RÈGLE D'EXCLUSION PRIORITAIRE :

    * Ignore uniquement les champs explicitement libellés :
    « Commune de gestion voirie »
    « Commune de gestion de voirie »
    « Commune de gestion de la voirie »
    « Commune gestion voirie »
    * Ne prends jamais directement la valeur de ces champs comme commune concernée.

    Exemple :
    « Commune de gestion voirie : 59120 Loos »
    → IGNORER cette occurrence.

    Si « Loos » apparaît ailleurs dans un contexte valide lié aux travaux, « Loos » peut être retenu.

    PRIORITÉ 1 — COMMUNE EXPLICITE

    Cherche d'abord les mentions telles que :

    * Commune concernée : ...
    * Commune : ...
    * Commune de ...
    * Commune des ...
    * Communes de ...
    * Communes des ...

    Retourne uniquement le nom de la commune / ville.

    Exemples :

    « Commune concernée : Loos »
    → Commune concernée : Loos

    « Commune : 59120 Loos »
    → Commune concernée : Loos

    « Commune de Villejuif »
    → Commune concernée : Villejuif

    PRIORITÉ 2 — VILLE / MAIRIE

    Si aucune mention valide de « Commune » n'est trouvée, cherche :

    * Ville de ...
    * Mairie de ...
    * Municipalité de ...

    Exemples :

    « Ville de Loos »
    → Commune concernée : Loos

    « Mairie de Chevilly-Larue »
    → Commune concernée : Chevilly-Larue

    PRIORITÉ 3 — VILLE IDENTIFIABLE DANS LE CONTEXTE DES TRAVAUX

    Si le mot « Commune » n'existe pas, tu peux utiliser le contexte des travaux pour identifier la ville.

    IMPORTANT :
    L'adresse ou la localisation sert uniquement à IDENTIFIER la ville.
    Ne retourne jamais l'adresse complète.

    Exemples :

    « Adresse des travaux : 12 rue Victor Hugo, 59120 Loos »
    → Commune concernée : Loos

    « Localisation des travaux : rue Georges Potié - Loos »
    → Commune concernée : Loos

    « Travaux rue de Paris à Villejuif »
    → Commune concernée : Villejuif

    « Chantier situé 25 avenue de la République, 94550 Chevilly-Larue »
    → Commune concernée : Chevilly-Larue

    NE RETOURNE JAMAIS :

    « 12 rue Victor Hugo, 59120 Loos »

    ou :

    « 59120 Loos »

    si le nom de la ville « Loos » peut être isolé clairement.

    Retourne uniquement :

    Commune concernée : Loos

    RÈGLES POUR RECONNAÎTRE UNE VILLE :

    * Le nom doit apparaître explicitement dans le texte OCR.
    * Tu peux retirer un code postal placé immédiatement avant le nom de la ville.
    * Tu peux retirer le numéro et le nom de rue.
    * Tu peux retirer les termes de localisation qui ne font pas partie du nom de la commune.
    * Ne corrige pas le nom de la ville avec tes connaissances externes.
    * Conserve le nom tel qu'il apparaît dans l'OCR.

    Exemple :

    « 59120 LOOS »
    → Commune concernée : LOOS

    « 94800 VILLEJUIF »
    → Commune concernée : VILLEJUIF

    « 12 rue X, 69009 Lyon 9éme »
    → Commune concernée : Lyon 9éme

    NE PAS UTILISER COMME COMMUNE :

    Une ville présente uniquement dans :

    * l'adresse de l'entreprise ;
    * l'adresse du demandeur ;
    * l'adresse du service émetteur ;
    * l'adresse postale du département ;
    * le lieu de signature ;
    * une référence administrative ;
    * une adresse sans lien avec les travaux.

    Exemple :

    « Société ABC - 10 rue X - 75008 Paris »

    → ne pas conclure :
    Commune concernée : Paris

    Exemple :

    « Fait à Lille, le 15 juin 2025 »

    → ne pas conclure :
    Commune concernée : Lille

    CAS IMPORTANT :

    « Commune de gestion voirie : 59120 Loos »
    « Adresse des travaux : 8 rue du Général Leclerc, Loos »

    → Commune concernée : Loos

    La première ligne est ignorée.
    La seconde fournit une preuve indépendante que Loos est la ville des travaux.

    En revanche :

    « Commune de gestion voirie : 59120 Loos »

    sans autre mention reliant Loos aux travaux

    → Commune concernée : non trouvée

    PLUSIEURS COMMUNES :

    Si plusieurs villes sont explicitement concernées par les travaux, retourne uniquement leurs noms séparés par « ; ».

    Exemple :

    « Travaux entre Loos et Haubourdin »

    → Commune concernée : Loos ; Haubourdin

    RÈGLE FINALE :

    La sortie « Commune concernée » doit contenir UNIQUEMENT :

    * un nom de commune / ville ;
    ou
    * plusieurs noms de communes / villes.

    Elle ne doit jamais contenir :

    * numéro de rue ;
    * nom de rue ;
    * adresse complète ;
    * code postal seul ;
    * département ;
    * entreprise ;
    * service administratif.

    Si aucune ville concernée par les travaux n'est suffisamment identifiable :
    → Commune concernée : non trouvée

    


    ==================================================
    3) DATE DE SIGNATURE
    ==================================================

    OBJECTIF :

    Extraire la DATE ASSOCIÉE À LA SIGNATURE ou à la FORMULE DE SIGNATURE
    du document.

    Ne prends PAS automatiquement la première date rencontrée.

    Cherche en priorité les formulations telles que :

    - Fait à ..., le ...
    - Fait le ...
    - Signé le ...
    - À ..., le ...
    - Le ... lorsqu'il se trouve clairement dans la zone de signature
    - une date située immédiatement à proximité du signataire,
    de la signature ou du cachet

    Exemples :

    « Fait à Nantes, le 15 juin 2025 »

    → Date de signature : 15 juin 2025

    « Signé le 03/04/2023 »

    → Date de signature : 03/04/2023

    --------------------------------------------------

    NE PAS CONFONDRE AVEC :

    - date de début des travaux ;
    - date de fin des travaux ;
    - période des travaux ;
    - date d'autorisation ;
    - date de demande ;
    - date de réception ;
    - date de dépôt ;
    - date de naissance ;
    - date d'effet ;
    - durée de validité ;
    - dates figurant uniquement dans les références administratives.

    --------------------------------------------------

    COPIE EXACTE :

    Copie uniquement la date, EXACTEMENT telle qu'elle apparaît dans le texte OCR.

    Ne :

    - reformate pas ;
    - convertis pas le mois en chiffres ;
    - corriges pas l'orthographe ;
    - corriges pas l'OCR ;
    - complètes pas une année ;
    - modifies pas les séparateurs.

    Exemples :

    « 15 juin 2025 »
    → Date de signature : 15 juin 2025

    « 03/04/2023 »
    → Date de signature : 03/04/2023

    « 15 juim 2025 »
    → Date de signature : 15 juim 2025

    Si plusieurs dates sont présentes, choisis celle dont le lien avec
    la signature est le PLUS EXPLICITE.

    Si aucune date de signature fiable n'est identifiable :

    Date de signature : non trouvée


    ==================================================
    CONTRAINTES GÉNÉRALES
    ==================================================

    - N'invente JAMAIS.
    - N'utilise aucune connaissance externe.
    - Ne complète jamais une information à partir d'un code postal.
    - Ne déduis jamais une ville à partir d'un département.
    - Ne déduis jamais un département à partir d'une ville.
    - Ne corrige pas automatiquement les erreurs OCR.
    - Toute valeur doit être justifiable par le texte fourni.
    - En cas de doute : « non trouvée ».
    - Les exclusions sont toujours prioritaires sur les règles générales.
    - Une information provenant d'un champ explicitement exclu ne doit jamais
    être réutilisée indirectement sans une autre source admissible explicite.
    - Ne JAMAIS écrire « Paris » comme Département si « Paris » apparaît
    uniquement dans une adresse, une commune ou un lieu.

    ==================================================
    FORMAT DE SORTIE OBLIGATOIRE
    ==================================================

    Retourne STRICTEMENT et UNIQUEMENT :

    <r>
    Département : [valeur ou non trouvée]
    Commune concernée : [valeur ou non trouvée]
    Date de signature : [valeur ou non trouvée]
    </r>

    Aucun Markdown.
    Aucun commentaire.
    Aucune explication.
    Aucune citation de ligne.
    Aucun texte avant <r>.
    Aucun texte après </r>.

    ==================================================
    EN-TÊTE
    ==================================================

    {head40}

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
            max_completion_tokens=4000,  # GPT-5 : inclut les tokens de réflexion
        )
        decoded = (response.choices[0].message.content or "").strip()
    except Exception as e:
        print(f"[prompt_general_com] Azure OpenAI error: {e}")
        decoded = ""
    if debug:
        print("DEBUG LLM >>>\n", decoded[:2000], "\n<<< END DEBUG")

    blocs_r = re.findall(r"<r>(.*?)</r>", decoded, flags=re.I | re.S)
    block = (blocs_r[-1] if blocs_r else decoded).strip()   # dernier bloc = réponse finale
    block = re.sub(r"(?m)^\s*\d{1,4}\s*:\s*", "", block)

    wanted = ["Département", "Commune concernée", "Date de signature"]
    values: Dict[str, str] = {k: "non trouvée" for k in wanted}

    labeled_found = 0
    _LIB = r"(?:D[ée]partement|Commune\s+concern[ée]e|Date\s+de\s+signature)"
    for k in wanted:
        lib_k = re.escape(k).replace("é", "[ée]").replace("\\ ", "\\s+")
        trouves = re.findall(rf"(?i){lib_k}\s*:\s*(.*?)(?=\s*{_LIB}\s*:|\n|$)", block)
        trouves = [t.strip() for t in trouves if t.strip()]
        if trouves:
            # le modèle peut écrire un brouillon puis sa réponse : on garde la dernière valeur
            values[k] = trouves[-1]
            labeled_found += 1

    # Réponse sans libellés (texte libre, message d'erreur…) : on ne devine pas
    # quelle ligne correspond à quel champ -> les 3 champs restent "non trouvée".

    dep_llm = values["Département"]
    com_llm = values["Commune concernée"]
    date_llm = values["Date de signature"]

    dep_final = "non trouvée"

    if dep_llm and not dep_llm.lower().startswith("non trouv"):
        dep_norm = _noacc_lower(dep_llm)

        if dep_norm not in GENERIC_SOLO and _phrase_present(text, dep_llm):
            if dep_norm in all_known:
                candidate = all_known[dep_norm]

                if candidate in official_names:
                    special_header = _find_first_special_in_header(text)
                    if special_header != "non trouvée":
                        dep_final = special_header
                    else:
                        dep_final = candidate
                else:
                    dep_final = candidate

            elif COMMUNE_LIKE_RE.search(dep_llm):
                dep_final = dep_llm

            elif EPCI_LIKE_RE.search(dep_llm):
                dep_final = dep_llm
            else:
                dep_final = dep_llm

    if dep_final == "non trouvée" and dep_llm and not dep_llm.lower().startswith("non trouv"):
        stripped = ADMIN_PREFIX_RE.sub("", dep_llm).strip()

        if stripped:
            stripped2 = re.sub(r"(?i)^l[ae]s?\s*", "", stripped).strip()

            result = _flex_match_all_known(stripped2)
            if result != "non trouvée":
                dep_final = result

            if dep_final == "non trouvée":
                result = _flex_match_all_known(stripped)
                if result != "non trouvée":
                    dep_final = result

            if dep_final == "non trouvée" and EPCI_LIKE_RE.search(stripped):
                if _phrase_present(text, stripped):
                    dep_final = stripped

    if dep_final == "non trouvée":
        m_hdr = DEPT_HEADER_RE.search(text or "")
        if m_hdr:
            after = (text or "")[m_hdr.end():m_hdr.end() + 80].strip()
            after_first = re.split(r"\n{2,}|[.;!]", after)[0].strip()
            after_clean = re.sub(r"\s+", " ", after_first).strip()

            if after_clean:
                result = _flex_match_all_known(after_clean)
                if result != "non trouvée":
                    dep_final = result

    if dep_final == "non trouvée":
        specials_sorted = sorted(specials, key=lambda x: (-len(x), x))

        for name in specials_sorted:
            if _phrase_present(text, name):
                dep_final = name
                break

    if dep_final == "non trouvée":
        AMBIGUOUS = {
            "Ain", "Aisne", "Nord", "Somme", "Lot", "Aube", "Orne", "Cher",
            "Jura", "Creuse", "Mayenne", "Loire", "Seine", "Gard", "Vienne",
            "Paris", "Var",
        }

        H_raw = text or ""

        best_name, best_pos = "non trouvée", 10**12
        for name in official_names:
            pos = _first_occurrence_phrase(H_raw, name)
            if pos >= 10**12:
                continue

            if _is_in_address_context(H_raw, name):
                continue

            if name in AMBIGUOUS:
                m_cs = re.search(
                    rf"(?:(?<=^)|(?<=\W)){re.escape(name)}(?:(?=\W)|$)",
                    H_raw,
                )
                m_caps = re.search(
                    rf"(?:(?<=^)|(?<=\W)){re.escape(name.upper())}(?:(?=\W)|$)",
                    H_raw,
                ) if not m_cs else None
                m_any = m_cs or m_caps
                if not m_any:
                    continue
                s, e = m_any.start(), m_any.end()
                win = H_raw[max(0, s - 60): min(len(H_raw), e + 60)]
                if not CONTEXT.search(win):
                    continue

            if pos < best_pos:
                best_name, best_pos = name, pos

        if best_name != "non trouvée":
            dep_final = best_name

    if dep_final == "non trouvée" and st_model is not None:
        from sklearn.metrics.pairwise import cosine_similarity

        ref_embeds = st_model.encode(french_departments)

        words_all = (text or "").split()
        candidates = set()
        for n in range(1, 6):
            for i in range(len(words_all) - n + 1):
                chunk = " ".join(words_all[i:i + n])
                if 3 < len(chunk) < 80:
                    candidates.add(chunk)

        candidates = list(candidates)
        if candidates:
            cand_embeds = st_model.encode(candidates, batch_size=128)
            sims = cosine_similarity(cand_embeds, ref_embeds)

            flat_indices = sims.flatten().argsort()[::-1]
            for idx in flat_indices:
                row, col = divmod(idx, len(french_departments))
                score = sims[row, col]
                if score < 0.85:
                    break
                dep_candidate = french_departments[col]
                if _phrase_present(text, dep_candidate):
                    dep_final = dep_candidate
                    break

    if dep_final == "non trouvée":
        com_norm = _noacc_lower(com_llm or "")
        french_norm = {_noacc_lower(x) for x in french_departments}

        if com_norm in french_norm:
            dep_final = com_llm

    if _noacc_lower(dep_final) in GENERIC_SOLO:
        dep_final = "non trouvée"

    # Logo « Moselle / L'Eurodépartement » : le nom complet de l'entité est
    # « Moselle L'Eurodépartement » (sur la même ligne ou sur la ligne suivante de l'en-tête).
    # Résultat : « Moselle - L'Eurodépartement » (texte recopié de l'en-tête).
    if dep_final != "non trouvée":
        _EURO = r"l?\s*['’]?\s*euro\s*-?\s*departement"
        _lignes_entete = [l.strip() for l in (text or "").splitlines() if l.strip()][:40]
        _dep_n = _noacc_lower(dep_final)
        _base_n = re.sub(rf"\s*[-–]?\s*{_EURO}\s*$", "", _dep_n).strip()
        for _k, _l in enumerate(_lignes_entete):
            _ln = _noacc_lower(_l)
            _suite_brut = _lignes_entete[_k + 1] if _k + 1 < len(_lignes_entete) else ""
            _suite = _noacc_lower(_suite_brut)
            if re.fullmatch(_EURO, _suite) and (
                    _ln == _base_n or (not _base_n and re.fullmatch(r"[a-z][a-z\- ]{2,29}", _ln))):
                dep_final = f"{_l} - {_suite_brut}"
                break
            if _base_n and re.fullmatch(rf"{re.escape(_base_n)}\s*[-–]?\s*{_EURO}", _ln):
                _m = re.match(r"(?i)^(.*?)\s*[-–]?\s*(l?\s*['’]?\s*euro\s*-?\s*d[ée]partement)\s*$", _l)
                dep_final = f"{_m.group(1)} - {_m.group(2)}" if _m else _l
                break

    # Nom complet écrit dans l'en-tête : « CONSEIL DÉPARTEMENTAL DE LA HAUTE-GARONNE »,
    # « Métropole de Grand Lyon »… Le modèle donne souvent le nom court (« LA HAUTE-GARONNE »,
    # « Grandlyon ») : on recopie la forme complète de l'en-tête qui contient ce nom.
    if dep_final != "non trouvée":
        dep_final = _nom_complet_entete(dep_final, text)

    com_final = com_llm if com_llm else "non trouvée"
    if re.fullmatch(r"\d{4,5}", com_final.strip()):
        com_final = "non trouvée"
    # La date doit être recopiée du texte : une date "corrigée" ou inventée est rejetée
    # (le garde-fou la cherchera ensuite lui-même après « Fait à …, le »).
    if date_llm and not date_llm.lower().startswith("non trouv") and not _phrase_present(text, date_llm):
        if debug:
            print(f"[prompt_general_com] date rejetée (absente du texte) : {date_llm!r}")
        date_llm = "non trouvée"
    date_final = _strip_time(date_llm)

    out_lines = [
        f"Département : {dep_final}",
        f"Commune concernée : {com_final}",
        f"Date de signature : {date_final}",
    ]
    return "\n".join(out_lines)


_ENTITE_PREFIXE_RE = re.compile(
    r"(?i)\b(?:conseil\s+d[ée]partementale?|conseil\s+g[ée]n[ée]ral|m[ée]tropole)"
    r"\s+(?:de\s+la|de\s+l['’]|du|des|de|d['’])\s*$")
_ENTITE_PREFIXE_DEBUT_RE = re.compile(
    r"(?i)^\s*(?:(?:le|la)\s+)?(?:conseil\s+d[ée]partementale?|conseil\s+g[ée]n[ée]ral|d[ée]partement|m[ée]tropole)"
    r"\s+(?:de\s+la|de\s+l['’]|du|des|de|d['’])\s*")


def _cle_entite(s):
    s = unicodedata.normalize("NFKD", str(s or "")).casefold()
    return "".join(c for c in s if c.isalnum() and not unicodedata.combining(c))


def _cles_proches(a, b):
    """Même nom, ou une seule lettre mal lue par l'OCR (noms de 8 lettres et plus)."""
    if a == b:
        return True
    return len(a) >= 8 and len(a) == len(b) and sum(x != y for x, y in zip(a, b)) == 1


def _nom_complet_entete(dep, texte, nb_lignes=40):
    """« LA HAUTE-GARONNE » + en-tête « CONSEIL DÉPARTEMENTAL DE LA HAUTE-GARONNE »
    -> « CONSEIL DÉPARTEMENTAL DE LA HAUTE-GARONNE ». Le texte renvoyé est recopié de
    l'en-tête ; sans forme complète dans l'en-tête, la valeur ne change pas."""
    coeur = _ENTITE_PREFIXE_DEBUT_RE.sub("", str(dep))
    coeur = re.sub(r"(?i)^\s*(?:(?:la|le|les)\s+|l['’]\s*)", "", coeur).strip()
    cle = _cle_entite(coeur)
    if len(cle) < 3:
        return dep
    lignes = [l.strip() for l in (texte or "").splitlines() if l.strip()][:nb_lignes]
    for i, ligne in enumerate(lignes):
        jetons = list(re.finditer(r"\S+", ligne))
        for a in range(len(jetons)):
            for b in range(a, min(a + 6, len(jetons))):
                deb, fin = jetons[a].start(), jetons[b].end()
                morceau = ligne[deb:fin].rstrip(",;:.")
                if not _cles_proches(_cle_entite(morceau), cle):
                    continue
                gauche = ligne[:deb]
                m = _ENTITE_PREFIXE_RE.search(gauche)
                if m:
                    return re.sub(r"\s+", " ", gauche[m.start():] + morceau).strip()
                if not gauche.strip() and i > 0:          # préfixe sur la ligne précédente
                    m = _ENTITE_PREFIXE_RE.search(lignes[i - 1])
                    if m:
                        return re.sub(r"\s+", " ", f"{lignes[i - 1][m.start():]} {morceau}").strip()
    return dep


def _parse_prompt_general_com_output(s: str) -> dict:
    m = re.search(r"<r>(.*?)</r>", s, flags=re.I | re.S)
    body = (m.group(1) if m else s).strip()
    body = re.sub(r"(?m)^\s*\d{1,4}\s*:\s*", "", body)

    fields = {
        "Département": "non trouvée",
        "Commune concernée": "non trouvée",
        "Date de signature": "non trouvée",
    }
    for line in body.splitlines():
        k, sep, v = line.partition(":")
        k = k.strip()
        v = v.strip()
        if sep and k in fields:
            fields[k] = v or fields[k]
    return fields


def result_to_df1(output: str, none_for_missing=False) -> pd.DataFrame:
    d = _parse_prompt_general_com_output(output)
    if none_for_missing:
        d = {k: (None if v == "non trouvée" else v) for k, v in d.items()}
    cols = ["Nom Bailleur", "Commune concernée", "Date de signature"]
    return pd.DataFrame(
        [[d["Département"], d["Commune concernée"], d["Date de signature"]]],
        columns=cols,
    )


# --- dépendances utilisées seulement à l'appel des fonctions (importées en fin de module : évite les imports circulaires) ---
from .normalisation import _normaliser_date_fr  # noqa: E402,F401