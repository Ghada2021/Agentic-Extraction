"""OCR : Azure AI Document Intelligence (prebuilt-layout) -> texte page par page.
Code repris tel quel de pmv_api.py (aucune modification)."""
from ._base import *  # noqa: F401,F403


# ====================================================================
#            OCR AZURE AI DOCUMENT INTELLIGENCE (prebuilt-layout)
# ====================================================================
# Variables d'environnement (.env) :
#   AZURE_DI_ENDPOINT  = https://iadocumenthandwritten.cognitiveservices.azure.com/
#   AZURE_DI_KEY       = <clé de la ressource>            (obligatoire)
#   AZURE_DI_MODEL     = prebuilt-layout                  (tableaux + manuscrit + tampons)
#   AZURE_DI_TIMEOUT   = 180                              (secondes max par PDF)
#
# Le texte rendu garde les conventions du reste du pipeline :
#   - une ligne de texte par ligne ;
#   - un tableau = une ligne par rangée, cellules séparées par 2 espaces
#     ("Artère souterraine (en ml)  171", "2  Ø60  46,50  93,00") ;
#   - pages séparées par une ligne vide.
AZURE_DI_ENDPOINT = os.getenv("AZURE_DI_ENDPOINT",
                              "https://iadocumenthandwritten.cognitiveservices.azure.com/").strip()
AZURE_DI_KEY = os.getenv("AZURE_DI_KEY", "").strip()
AZURE_DI_MODEL = os.getenv("AZURE_DI_MODEL", "prebuilt-layout").strip()
AZURE_DI_TIMEOUT = float(os.getenv("AZURE_DI_TIMEOUT", "180"))

# v4.0 (Document Intelligence), puis ancienne API (Form Recognizer) si la ressource ne la connaît pas.
_AZURE_DI_ROUTES = [
    ("documentintelligence", "2024-11-30"),
    ("formrecognizer", "2023-07-31"),
]


def _azure_di_analyze(pdf_bytes: bytes) -> dict:
    """Envoie le PDF à Azure Document Intelligence et renvoie `analyzeResult`."""
    import httpx

    if not AZURE_DI_KEY:
        raise RuntimeError("AZURE_DI_KEY manquante dans le .env")
    base = AZURE_DI_ENDPOINT.rstrip("/")
    headers = {"Ocp-Apim-Subscription-Key": AZURE_DI_KEY, "Content-Type": "application/pdf"}
    derniere_erreur = None
    with httpx.Client(timeout=60.0) as http:
        for chemin, version in _AZURE_DI_ROUTES:
            url = f"{base}/{chemin}/documentModels/{AZURE_DI_MODEL}:analyze?api-version={version}"
            r = http.post(url, headers=headers, content=pdf_bytes)
            if r.status_code == 404:                       # version d'API non disponible
                derniere_erreur = f"404 sur {chemin} {version}"
                continue
            if r.status_code != 202:
                raise RuntimeError(f"Azure DI {r.status_code} : {r.text[:300]}")
            op_url = r.headers["Operation-Location"]
            debut = time.monotonic()
            while True:
                attente = float(r.headers.get("Retry-After", "1") or 1)
                time.sleep(min(max(attente, 0.5), 5))
                r = http.get(op_url, headers={"Ocp-Apim-Subscription-Key": AZURE_DI_KEY})
                if r.status_code == 429:                   # quota : on patiente et on réessaie
                    continue
                r.raise_for_status()
                corps = r.json()
                statut = corps.get("status")
                if statut == "succeeded":
                    return corps.get("analyzeResult") or {}
                if statut == "failed":
                    raise RuntimeError(f"Azure DI échec : {json.dumps(corps.get('error'))[:300]}")
                if time.monotonic() - debut > AZURE_DI_TIMEOUT:
                    raise TimeoutError(f"Azure DI : pas de résultat après {AZURE_DI_TIMEOUT:.0f} s")
    raise RuntimeError(f"Azure DI : aucune route d'API disponible ({derniere_erreur})")


def _azure_nettoyer(t: str) -> str:
    """Retire les marques de cases à cocher non cochées ; garde les cochées en [X]."""
    t = (t or "").replace(":unselected:", "").replace(":selected:", "[X]")
    return re.sub(r"[ \t]{2,}", " ", t).strip()


def _azure_page_de(element) -> int:
    regions = element.get("boundingRegions") or []
    return regions[0].get("pageNumber", 1) if regions else 1


def _azure_offset(element) -> int:
    spans = element.get("spans") or []
    return min((sp.get("offset", 0) for sp in spans), default=0)


def _azure_dans_spans(offset: int, spans) -> bool:
    return any(sp["offset"] <= offset < sp["offset"] + sp["length"] for sp in spans)


def _azure_lignes_tableau(table) -> List[str]:
    """Une ligne par rangée ; cellules (non vides) de gauche à droite, séparées par 2 espaces."""
    rangees = {}
    for c in table.get("cells") or []:
        rangees.setdefault(c.get("rowIndex", 0), []).append(c)
    lignes = []
    for i in sorted(rangees):
        cellules = sorted(rangees[i], key=lambda c: c.get("columnIndex", 0))
        textes = [_azure_nettoyer(c.get("content", "")).replace("\n", " ") for c in cellules]
        ligne = "  ".join(t for t in textes if t)
        if ligne and (not lignes or ligne != lignes[-1]):   # cellules fusionnées répétées
            lignes.append(ligne)
    return lignes


def _azure_pages_texte(resultat: dict) -> List[str]:
    """Reconstruit le texte de chaque page dans l'ordre de lecture d'Azure."""
    contenu = resultat.get("content") or ""
    nb_pages = max([p.get("pageNumber", 1) for p in resultat.get("pages") or []] or [1])
    tables = resultat.get("tables") or []
    spans_tables = [sp for t in tables for sp in (t.get("spans") or [])]

    # éléments (offset, page, lignes) : paragraphes hors tableaux + tableaux entiers
    elements = []
    for par in resultat.get("paragraphs") or []:
        off = _azure_offset(par)
        if spans_tables and _azure_dans_spans(off, spans_tables):
            continue
        spans = par.get("spans") or []
        brut = "\n".join(contenu[sp["offset"]: sp["offset"] + sp["length"]] for sp in spans) \
            if contenu and spans else par.get("content", "")
        lignes = [_azure_nettoyer(l) for l in brut.splitlines()]
        lignes = [l for l in lignes if l]
        if lignes:
            elements.append((off, _azure_page_de(par), lignes))
    for t in tables:
        lignes = _azure_lignes_tableau(t)
        if lignes:
            elements.append((_azure_offset(t), _azure_page_de(t), lignes))

    if not elements and resultat.get("pages"):
        # pas de paragraphes (modèle prebuilt-read) : lignes brutes de chaque page
        sortie = [""] * nb_pages
        for p in resultat["pages"]:
            n = min(max(p.get("pageNumber", 1), 1), nb_pages)
            sortie[n - 1] = "\n".join(_azure_nettoyer(l.get("content", "")) for l in (p.get("lines") or []))
        return sortie

    pages = [[] for _ in range(nb_pages)]
    for off, page, lignes in sorted(elements, key=lambda e: e[0]):
        pages[min(max(page, 1), nb_pages) - 1].extend(lignes)
    return ["\n".join(p) for p in pages]


@trace_step('pdf_path')
def extract_text_from_pdf(pdf_path: str, poppler_path: str = None, dpi: Optional[int] = None,
                          ocr_threads: Optional[int] = None, return_info: bool = False):
    """OCR via Azure AI Document Intelligence (toutes les pages en un appel).
    Même signature et même format de sortie que la version Paddle (pmv.py).
    Version autonome : aucun OCR local. Si Azure échoue, l'erreur est remontée
    (process_pdf la signale pour ce fichier, les autres PDF continuent)."""
    debut = time.perf_counter()
    with open(pdf_path, "rb") as fh:
        resultat = _azure_di_analyze(fh.read())
    pages = _azure_pages_texte(resultat)
    duree = round(time.perf_counter() - debut, 3)
    tables_par_page = {}
    for t in resultat.get("tables") or []:
        p = _azure_page_de(t)
        tables_par_page[p] = tables_par_page.get(p, 0) + 1
    infos = [{"page": i + 1, "source": f"Azure DI {AZURE_DI_MODEL}",
              "tableaux": tables_par_page.get(i + 1, 0), "ocr_seconds": duree}
             for i in range(len(pages))]
    with observation("pdf-source-pages") as source_span:
        _update(source_span, output=[dict(info, text=page) for info, page in zip(infos, pages)])
    text = "\n\n".join(p.strip() for p in pages)
    return (text, infos) if return_info else text
