"""process_pdf (ordre des extractions) et traitement parallèle.
Code repris tel quel de pmv_api.py (aucune modification)."""
from ._base import *  # noqa: F401,F403


# ====================================================================
#                         ORCHESTRATEUR
# ====================================================================
@trace_step('pdf_path')
def process_pdf(pdf_path, client, deployment,
                french_departments=None, st_model=None,
                poppler_path=None, debug=False, ocr_threads=None,
                nom_fichier=None):
    """
    OCR d'un PDF puis extraction de tous les champs.
    Renvoie (texte_ocr, DataFrame 1 ligne combinant tous les champs).
    nom_fichier : nom d'origine du PDF (upload Streamlit = fichier temporaire) ;
    par défaut, le nom de pdf_path.
    """
    if french_departments is None:
        french_departments = FRENCH_DEPARTMENTS

    txt = extract_text_from_pdf(pdf_path, poppler_path=poppler_path, ocr_threads=ocr_threads)

    # Règle : aucune information ne doit provenir d'une clause "Vu".
    txt_sans_vu = _supprimer_clauses_vu(txt)
    # Formulaires : « Artère souterraine (en ml)  171 » -> « Artère souterraine : 171 ml ».
    txt_sans_vu = _normaliser_lignes_formulaire(txt_sans_vu)

    cat = classify_pdf_llm(txt_sans_vu, client, deployment)

    df_part = extract_partenaire_cession_df(txt_sans_vu)

    gen = prompt_general_com(text=txt_sans_vu, client=client, deployment=deployment,
                             french_departments=french_departments, st_model=st_model, debug=debug)
    df_gen = result_to_df1(gen)

    ref = extract_ref_bailleur_llm(txt_sans_vu, client, deployment)
    df_ref = ref_bailleur_to_df(ref)

    dts = llm_extract_dates(section=None, client=client, deployment=deployment, full_text=txt_sans_vu, debug=debug)
    df_dates = dates_to_df(dts)

    dur = llm_extract_duree(section=None, client=client, deployment=deployment, full_text=txt_sans_vu, debug=debug)
    df_duree = duree_to_df2(dur)

    mod = prompt_modalites_renouvellement_resiliation(section=None, client=client, deployment=deployment, full_text=txt_sans_vu, debug=debug)
    df_mod = modalites_to_df(mod)

    adr = llm_extract_adresse_travaux(text=txt_sans_vu, client=client, deployment=deployment, debug=debug)
    df_adr = adresse_to_df(adr)

    gc_out = extract_longueur_gc(txt_sans_vu, client, deployment, debug=debug)
    df_gc = longueur_gc_to_df(gc_out)

    four = llm_extract_fourreaux(txt_sans_vu, client, deployment, debug=debug)
    df_four = fourreaux_to_df(four)

    chb = extract_chambres_from_text(txt_sans_vu, client, deployment, debug=debug)
    df_chb = chambres_to_df(chb)

    final_df = pd.concat(
        [df_gen, df_ref, df_part, df_dates, df_duree, df_mod,
         df_adr, df_gc, df_four, df_chb],
        axis=1
    )
    final_df.insert(0, "Type", cat)
    final_df.insert(1, "Safix", extraire_safix(nom_fichier or pdf_path))

    # Garde-fou : pas de phrase, d'artefact LLM ni de valeur absente du texte.
    final_df = garde_fou_df(final_df, txt_sans_vu, debug=debug)

    # Nombres en lettres -> chiffres dans les colonnes de longueur.
    final_df = normaliser_longueurs_df(final_df)

    # Uniformise l'unité : "N ml" (GC, longueur par fourreau, longueur totale).
    final_df = normaliser_unite_ml_df(final_df)

    # Fusion : une seule colonne "Longueur génie civil" (GC prioritaire,
    # fallback sur "Longueur totale"), puis suppression de "Longueur totale".
    final_df = fusionner_longueur_gc_totale(final_df)

    # Dates -> JJ/MM/AAAA.
    final_df = normaliser_dates_df(final_df)

    # Nettoie les caractères parasites (: ? § = | ...) des champs textuels.
    final_df = nettoyer_champs_texte_df(final_df)

    # Harmonise la casse (Titre) sur bailleur / commune / adresse.
    final_df = normaliser_casse_df(final_df)

    # Uniformise toutes les variantes de "non trouvé" -> "Non trouvé".
    final_df = normaliser_non_trouve_df(final_df)

    return txt, final_df


# ====================================================================
#                 TRAITEMENT PARALLÈLE (N PDF À LA FOIS)
# ====================================================================
def process_pdfs_parallel(
    pdf_paths: List[str],
    client,
    deployment,
    max_workers: int = 3,
    french_departments=None,
    st_model=None,
    poppler_path=None,
    debug: bool = False,
    on_result: Optional[Callable[[dict, int, int], None]] = None,
) -> List[dict]:
    """
    Traite plusieurs PDF en parallèle (max_workers à la fois, 2 ou 3 recommandé).

    Un PDF en erreur ne bloque pas les autres. Renvoie une liste de dicts, dans
    l'ORDRE des fichiers d'entrée :
        {"pdf", "ok", "texte", "df", "erreur", "duree_s", "llm": {"azure": n, "ollama": n}}

    on_result(result, n_termines, n_total) est appelé dans le THREAD APPELANT à chaque
    PDF terminé -> on peut y mettre à jour une barre st.progress() sans risque.
    """
    pdf_paths = list(pdf_paths)
    total = len(pdf_paths)
    if total == 0:
        return []
    max_workers = max(1, min(max_workers, total))

    ocr_threads = None   # OCR fait par Azure : aucun moteur local à précharger

    def _worker(pdf_path: str) -> dict:
        t0 = time.perf_counter()
        if hasattr(client, "reset_thread_usage"):
            client.reset_thread_usage()
        res = {"pdf": pdf_path, "ok": False, "texte": "", "df": None, "erreur": None}
        try:
            txt, df = process_pdf(
                pdf_path, client, deployment,
                french_departments=french_departments, st_model=st_model,
                poppler_path=poppler_path, debug=debug, ocr_threads=ocr_threads,
            )
            res.update(ok=True, texte=txt, df=df)
        except Exception as e:
            log.exception("Échec sur %s", pdf_path)
            res["erreur"] = f"{type(e).__name__}: {e}"
        res["duree_s"] = round(time.perf_counter() - t0, 1)
        res["llm"] = client.thread_usage() if hasattr(client, "thread_usage") else {}
        return res

    results: List[Optional[dict]] = [None] * total
    done = 0
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="pmv") as pool:
        futures = {pool.submit(_worker, p): i for i, p in enumerate(pdf_paths)}
        for fut in as_completed(futures):
            i = futures[fut]
            results[i] = fut.result()
            done += 1
            if on_result is not None:
                on_result(results[i], done, total)
    return results


def results_to_dataframe(results: List[dict]) -> pd.DataFrame:
    """Concatène les résultats en un tableau (1 ligne par PDF, colonne 'Fichier' en tête).
    Les PDF en erreur apparaissent avec la colonne 'Erreur' remplie."""
    rows = []
    for r in results:
        name = os.path.basename(r["pdf"])
        if r["ok"] and r["df"] is not None:
            df = r["df"].copy()
            df.insert(0, "Fichier", name)
            df["LLM utilisé"] = _llm_label(r.get("llm") or {})
        else:
            df = pd.DataFrame({"Fichier": [name], "Erreur": [r["erreur"]]})
        rows.append(df)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def _llm_label(usage: dict) -> str:
    a, o = usage.get("azure", 0), usage.get("ollama", 0)
    if o == 0:
        return "Azure"
    if a == 0:
        return "Ollama"
    return f"Mixte (Azure {a} / Ollama {o})"


# --- dépendances utilisées seulement à l'appel des fonctions (importées en fin de module : évite les imports circulaires) ---
from .adresse import adresse_to_df, llm_extract_adresse_travaux  # noqa: E402,F401
from .chambres import chambres_to_df, extract_chambres_from_text  # noqa: E402,F401
from .dates_autorisation import dates_to_df, llm_extract_dates  # noqa: E402,F401
from .departement_commune_signature import FRENCH_DEPARTMENTS, prompt_general_com, result_to_df1  # noqa: E402,F401
from .duree import duree_to_df2, llm_extract_duree  # noqa: E402,F401
from .fourreaux import fourreaux_to_df, llm_extract_fourreaux  # noqa: E402,F401
from .garde_fou import garde_fou_df  # noqa: E402,F401
from .longueur_gc import extract_longueur_gc, longueur_gc_to_df  # noqa: E402,F401
from .modalites import modalites_to_df, prompt_modalites_renouvellement_resiliation  # noqa: E402,F401
from .normalisation import fusionner_longueur_gc_totale, nettoyer_champs_texte_df, normaliser_casse_df, normaliser_dates_df, normaliser_longueurs_df, normaliser_non_trouve_df, normaliser_unite_ml_df  # noqa: E402,F401
from .ocr_azure import extract_text_from_pdf  # noqa: E402,F401
from .partenaire import extract_partenaire_cession_df  # noqa: E402,F401
from .pretraitement_texte import _normaliser_lignes_formulaire, _supprimer_clauses_vu  # noqa: E402,F401
from .reference_bailleur import extract_ref_bailleur_llm, ref_bailleur_to_df  # noqa: E402,F401
from .safix import extraire_safix  # noqa: E402,F401
from .type_document import classify_pdf_llm  # noqa: E402,F401
