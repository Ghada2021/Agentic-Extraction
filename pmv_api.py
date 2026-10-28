"""PMV — point d'entrée unique (même résultat que l'ancien pmv_api.py).

Le code est réparti dans le dossier extraction/ (un fichier par colonne).
Ce fichier ré-expose toutes les fonctions : `import pmv_api as pmv` marche comme avant."""
from extraction._base import *  # noqa: F401,F403
from extraction.ocr_azure import (  # noqa: F401
    AZURE_DI_ENDPOINT,
    AZURE_DI_KEY,
    AZURE_DI_MODEL,
    AZURE_DI_TIMEOUT,
    _AZURE_DI_ROUTES,
    _azure_dans_spans,
    _azure_di_analyze,
    _azure_lignes_tableau,
    _azure_nettoyer,
    _azure_offset,
    _azure_page_de,
    _azure_pages_texte,
    extract_text_from_pdf,
)
from extraction.llm import (  # noqa: F401
    init_azure_openai,
    init_llm_client,
)
from extraction.type_document import (  # noqa: F401
    classify_pdf_llm,
)
from extraction.partenaire import (  # noqa: F401
    extract_partenaire_cession_df,
)
from extraction.departement_commune_signature import (  # noqa: F401
    FRENCH_DEPARTMENTS,
    _parse_prompt_general_com_output,
    prompt_general_com,
    result_to_df1,
)
from extraction.reference_bailleur import (  # noqa: F401
    _nettoyer_lignes_vu,
    extract_ref_bailleur_llm,
    ref_bailleur_to_df,
)
from extraction.duree import (  # noqa: F401
    _parse_duree_output,
    _strip_accents,
    duree_to_df2,
    extract_duree_sections_from_text,
    llm_extract_duree,
)
from extraction.dates_autorisation import (  # noqa: F401
    MOIS_NUM,
    MONTH_RE,
    RE_DAY_MONTH_YEAR,
    RE_MONTH_YEAR,
    RE_SLASH,
    _complete_year_if_missing,
    _dedup_month_word,
    _extract_end_date_multiline,
    _find_next_date_after_contextual,
    _fix_broken_dates,
    _fix_ocr_text,
    _hard_date_filter,
    _is_verbatim_in,
    _looks_like_date,
    _norm_for_match,
    _numbered,
    _parse_date_to_comparable,
    _parse_dates_output,
    _pick_last_valid_result_block,
    _remove_legal_reference_noise,
    _run_llm,
    _search_broken_fin,
    _to_str,
    dates_to_df,
    llm_extract_dates,
)
from extraction.modalites import (  # noqa: F401
    _parse_modalites_output,
    modalites_to_df,
    prompt_modalites_renouvellement_resiliation,
)
from extraction.adresse import (  # noqa: F401
    _VOIE_KW,
    _parse_adresse_output,
    adresse_to_df,
    llm_extract_adresse_travaux,
)
from extraction.longueur_gc import (  # noqa: F401
    AERIAL_CONTEXT_RE,
    CHAINAGE_RE,
    DEPTH_CONTEXT_RE,
    NUM_KM_RE,
    NUM_UNIT_RE,
    PARTIAL_CONTEXT_RE,
    PR_RD_CTX_RE,
    TECHNICAL_CONSTRAINT_RE,
    TYPICAL_DEPTH_VALUES,
    UNDERGROUND_CONTEXT_RE,
    _call_llm,
    _explicit_gc_evidence,
    _extract_chainage_numbers,
    _extract_value_from_line,
    _find_longueur_totale_km,
    _find_total_in_text,
    _find_underground_value_multiline,
    _find_value_after_header,
    _find_with_heuristics,
    _format_cases,
    _is_aerial_line,
    _is_depth_or_constraint_line,
    _is_depth_value,
    _is_partial_line,
    _is_underground_line,
    _km_to_m,
    _load_cases,
    _normalize_unit,
    _parse_llm_response,
    _value_exists_in_text,
    extract_longueur_gc,
    longueur_gc_to_df,
)
from extraction.chambres import (  # noqa: F401
    chambres_to_df,
    extract_chambres_from_text,
)
from extraction.fourreaux import (  # noqa: F401
    _clean_fourreaux_value,
    _is_non_trouve,
    _parse_fourreaux_output,
    fourreaux_to_df,
    llm_extract_fourreaux,
)
from extraction.normalisation import (  # noqa: F401
    _ACRONYMES,
    _CARACTERES_AUTORISES_RE,
    _MISSING_EXACT,
    _MISSING_PREFIXES,
    _MOIS_FR_NUM,
    _MOIS_OCR_ALIAS,
    _NUMBER_TOKENS,
    _PARTICULES,
    _SMALL_FR,
    _annee4,
    _convertir_nombres_ecrits,
    _digits_ocr,
    _fmt_number,
    _fr_words_to_int,
    _is_missing_value,
    _ml_simple,
    _mois_ocr_vers_num,
    _mois_vers_num,
    _nettoyer_champ_texte,
    _normaliser_date_fr,
    _normaliser_nom_bailleur,
    _normaliser_nom_bailleur_canonique,
    _normaliser_unite_ml,
    _parse_tokens_date,
    _premiere_lettre_maj,
    _texte_nombres_en_chiffres,
    _titre_propre,
    _to_number,
    _valider_date,
    fusionner_longueur_gc_totale,
    nettoyer_champs_texte_df,
    normaliser_casse_df,
    normaliser_dates_df,
    normaliser_longueurs_df,
    normaliser_non_trouve_df,
    normaliser_unite_ml_df,
)
from extraction.pretraitement_texte import (  # noqa: F401
    _FIN_PREAMBULE_RE,
    _FORM_LIGNE_RE,
    _FORM_QTE_RE,
    _FORM_UNITE_RE,
    _PREAMBULE_CLAUSE_RE,
    _VU_MAX_CONTINUATION,
    _VU_START_RE,
    _normaliser_lignes_formulaire,
    _supprimer_clauses_vu,
)
from extraction.safix import (  # noqa: F401
    RE_SIX_DIGITS,
    extraire_safix,
)
from extraction.garde_fou import (  # noqa: F401
    _ARTEFACT_LLM_RE,
    _BLOC_SIGNATURE_RE,
    _COLONNES_ANCREES,
    _COLONNES_LIBRES,
    _COLONNES_TEXTE_LONG,
    _DATE_RE,
    _LIBELLE_FUITE_RE,
    _LONGUEUR_MAX,
    _MOIS_RE,
    _MOTS_MAX_PAR_PARTIE,
    _PHRASE_RE,
    _SIGNATURE_RES,
    _norm_mots,
    _present_dans_texte,
    _trouver_date_signature,
    garde_fou_df,
)
from extraction.orchestrateur import (  # noqa: F401
    _llm_label,
    process_pdf,
    process_pdfs_parallel,
    results_to_dataframe,
)


# ====================================================================
#                         CLI
# ====================================================================
if __name__ == "__main__":
    # Usage : python pmv.py dossier_pdf/ --workers 3 --out resultats.xlsx
    import argparse
    import glob

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(threadName)s] %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+", help="Fichiers PDF ou dossiers")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--out", default="resultats_pmv.xlsx")
    ap.add_argument("--poppler", default=None)
    args = ap.parse_args()

    paths = []
    for p in args.inputs:
        paths += sorted(glob.glob(os.path.join(p, "*.pdf"))) if os.path.isdir(p) else [p]

    client, deployment = init_llm_client()
    if client is None:
        raise SystemExit("Aucun LLM disponible : configurez Azure (.env) ou lancez Ollama.")

    t0 = time.perf_counter()
    res = process_pdfs_parallel(
        paths, client, deployment, max_workers=args.workers, poppler_path=args.poppler,
        on_result=lambda r, n, t: print(f"[{n}/{t}] {os.path.basename(r['pdf'])} "
                                        f"{'OK' if r['ok'] else 'ERREUR'} en {r['duree_s']}s "
                                        f"({_llm_label(r['llm'])})"),
    )
    results_to_dataframe(res).to_excel(args.out, index=False)
    print(f"Terminé : {len(paths)} PDF en {time.perf_counter() - t0:.0f}s -> {args.out}")
    if hasattr(client, "stats"):
        print("Appels LLM :", client.stats)
# __END__
