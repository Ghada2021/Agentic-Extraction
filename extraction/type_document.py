"""Colonne « Type » : classification du document.
Code repris tel quel de pmv_api.py (aucune modification)."""
from ._base import *  # noqa: F401,F403


# ====================================================================
#                         TYPE PMV
# ====================================================================
@trace_step('texte_extrait')
def classify_pdf_llm(texte_extrait: str, client, deployment) -> str:
    """Classifie un PDF par le texte OCR via l'API Azure OpenAI."""

    pages = texte_extrait.split("\f")[:2]
    text_2pages = "\f".join(pages)[:3000]

    
    prompt = f"""Analyse ce texte extrait d'un PDF et réponds UNIQUEMENT par une seule catégorie, sans explication.

    Catégories :

    - PMV :
    permission de voirie, arrêté municipal/préfectoral, autorisation de voirie,
    autorisation d'occupation temporaire du domaine public.
    Le document contient souvent des articles numérotés :
    Article 1, Article 2, Article 3, etc.
    Mots-clés fréquents :
    "Permission de voirie", "PMV", "Autorisation de voirie", "Arrêté",
    "Arrêté municipal", "Arrêté préfectoral",
    "Autorisation d'occupation temporaire".

    - CERFA :
    formulaire administratif officiel CERFA.
    Peut contenir le mot "CERFA", "Formulaire CERFA" ou un numéro CERFA.

    - Document administratif et financier :
    facture, attestation d'assurance, transfert de domanialité,
    avoir, avenant, document financier ou administratif similaire.
    Mots-clés possibles :
    "Facture", "Attestation d'assurance", "Avoir", "Avenant",
    "HT", "TTC", "TVA", "RIB", "IBAN", "BIC".

    - Document technique :
    APD, plan, plans techniques, cartographie, schéma réseau,
    tracé télécom ou document technique similaire.
    Mots-clés possibles :
    "APD", "Plan", "Cartographie", "Plan de réseau",
    "Schéma", "Tracé", "Télécom".

    - Convention :
    convention d'occupation, convention cadre, convention collectivité,
    convention particulier, convention de servitude de passage.
    Le mot "Convention" apparaît généralement dans le titre ou en tête de page.
    Mots-clés fréquents :
    "Convention cadre",
    "Convention d'occupation",
    "Convention d'occupation du domaine public",
    "Convention de servitude",
    "Convention de servitude de passage".

    - BDC :
    bon de commande.
    Le document peut contenir "BDC" ou "Bon de commande"
    dans le titre, le nom du document ou en tête de page.
    Mots-clés fréquents :
    "BDC",
    "Bon de commande",
    "BON DE COMMANDE",
    "N° de commande",
    "Numéro de commande".

    - Autre :
    courrier, mail, lettre, compte-rendu, bordereau, annexe
    ou tout autre type de document ne correspondant pas aux catégories précédentes.

    RÈGLES DE CLASSIFICATION :

    1. Cherche d'abord le titre ou l'en-tête du document.
    2. Les mots-clés explicites du titre sont prioritaires.
    3. "Bon de commande" ou "BDC" → BDC.
    4. Tout titre contenant clairement "Convention" → Convention.
    5. "Permission de voirie", "Arrêté", "PMV", "Autorisation de voirie"
    → PMV si le contexte confirme qu'il s'agit du document principal.
    6. "CERFA" → CERFA.
    7. "APD", "Plan", "Cartographie" → Document technique.
    8. "Facture", "Attestation d'assurance", "Avoir", "Avenant"
    → Document administratif et financier.
    9. Une simple mention d'un mot-clé dans une référence ou dans le corps du texte
    ne suffit pas toujours : privilégie le TYPE DU DOCUMENT COURANT.
    10. En cas de doute → Autre.

    Réponds UNIQUEMENT par l'une des catégories suivantes :

    PMV
    CERFA
    Document administratif et financier
    Document technique
    Convention
    BDC
    Autre

    Texte du document :
    {text_2pages}

    Catégorie :"""



    resp = traced_completion(client.chat.completions.create, 
        model=deployment,
        messages=[{"role": "user", "content": prompt}],
        max_completion_tokens=4000,  # GPT-5 : inclut les tokens de réflexion (était 200)
    )
    raw = (resp.choices[0].message.content or "").strip()

    CATEGORIES = ["PMV", "CERFA", "Document financier", "Plan de travail telecom", "Convention", "Autre"]
    raw_clean = raw.strip().strip(".-•:").strip().lower()
    for cat in CATEGORIES:
        if cat.lower() == raw_clean:
            return cat
    matches = [cat for cat in CATEGORIES if cat.lower() in raw_clean]
    if len(matches) == 1:
        return matches[0]
    return "Autre"
