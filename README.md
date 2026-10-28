# PMV — version modulaire (OCR Azure)

Même code, mêmes prompts, mêmes colonnes que `pmv_api.py` d'origine :
seule l'organisation change (un fichier par colonne) pour faciliter le débogage.

## Lancer

    streamlit run app.py                 (interface)
    python pmv_api.py dossier_pdfs/      (ligne de commande -> resultats_pmv.xlsx)
    python test_pmv_regressions.py pmv_api   (tests de non-régression)

## À copier dans ce dossier (non fournis)

- `.env` (voir `.env.exemple`)
- `llm_fallback.py`, `pmv_tracing.py` (vos modules existants)
- `gc_cases.json` (exemples du prompt GC, s'il existe dans votre projet)

## Où est quoi

| Fichier | Contenu |
|---|---|
| `pmv_api.py` | Regroupe tous les modules ; `import pmv_api as pmv` marche comme avant. CLI. |
| `app.py` | Interface Streamlit (inchangée). |
| `extraction/_base.py` | Imports communs, `load_dotenv()`, logger. |
| `extraction/ocr_azure.py` | OCR Azure Document Intelligence -> texte par page, tableaux en lignes. |
| `extraction/llm.py` | Connexion Azure OpenAI / repli Ollama. |
| `extraction/pretraitement_texte.py` | Suppression des clauses « Vu », lignes de formulaire « (en ml) 171 ». |
| `extraction/type_document.py` | Colonne **Type**. |
| `extraction/safix.py` | Colonne **Safix**. |
| `extraction/departement_commune_signature.py` | **Nom Bailleur**, **Commune concernée**, **Date de signature** (`prompt_general_com`, liste `FRENCH_DEPARTMENTS`). |
| `extraction/reference_bailleur.py` | **Référence bailleur**. |
| `extraction/partenaire.py` | **Partenaire cession**. |
| `extraction/dates_autorisation.py` | **Date de début / fin d'autorisation**. |
| `extraction/duree.py` | **Durée de l'autorisation**. |
| `extraction/modalites.py` | **Modalités de renouvellement / résiliation**. |
| `extraction/adresse.py` | **Adresse des travaux**. |
| `extraction/longueur_gc.py` | **Longueur génie civil**. |
| `extraction/fourreaux.py` | **Nombre de fourreaux**, **Longueur par fourreau**, **Longueur totale**. |
| `extraction/chambres.py` | **Nbr de chambres**. |
| `extraction/normalisation.py` | Post-traitements : nombres en lettres, « N ml », dates JJ/MM/AAAA, « Non trouvé », casse, fusion GC/total, nettoyage. |
| `extraction/garde_fou.py` | Garde-fou final (phrases, artefacts LLM, valeurs absentes du texte) + date de signature de secours. |
| `extraction/orchestrateur.py` | `process_pdf` : ordre des extractions et des post-traitements ; traitement parallèle. |

## Déboguer une colonne

Chaque module s'importe seul, par exemple pour les fourreaux :

    from extraction.fourreaux import llm_extract_fourreaux, fourreaux_to_df
    from extraction.llm import init_azure_openai
    client, deployment = init_azure_openai()
    print(llm_extract_fourreaux(texte_ocr, client, deployment, debug=True))

Les fonctions utilisées par plusieurs modules restent dans le module de leur section
d'origine (ex. `_strip_accents` dans `duree.py`, `_normaliser_date_fr` dans
`normalisation.py`) ; elles sont importées là où elles servent.
