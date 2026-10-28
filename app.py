# -*- coding: utf-8 -*-
"""
app.py — Interface Streamlit pour l'extraction PMV.

Lancement (depuis un terminal, PAS un notebook) :
    streamlit run app.py
"""

import os
import tempfile
from io import BytesIO
from datetime import datetime

import pandas as pd
import streamlit as st

import pmv_api as pmv   # pmv_api.py = version Azure autonome (sinon : import pmv)


# ------------------------------------------------------------
# Config : chemin poppler (mets ici ton dossier ...\Library\bin)
# ------------------------------------------------------------
POPPLER_PATH = os.environ.get("POPPLER_PATH") or \
    r"C:\Users\ghada.mhadhbi_amaris\Videos\Passation\PMV\PMV_Livrable\PMV_Livrable\Release-24.08.0-0\poppler-24.08.0\Library\bin"


# ------------------------------------------------------------
# Ressources chargées UNE seule fois (cache Streamlit)
# ------------------------------------------------------------
@st.cache_resource(show_spinner="Chargement du moteur OCR…")
def _load_ocr_engine():
    # Seule la version Paddle a un moteur OCR local ; la version Azure n'en a pas.
    if hasattr(pmv, "get_ocr_engine"):
        return pmv.get_ocr_engine()
    return None


@st.cache_resource(show_spinner="Connexion à Azure OpenAI…")
def _load_azure_client():
    return pmv.init_azure_openai()


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def _save_upload_to_temp(uploaded_file) -> str:
    suffix = os.path.splitext(uploaded_file.name)[1] or ".pdf"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded_file.getbuffer())
        return tmp.name


def _fill_blanks(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    return df.fillna("Non trouvé")


def run_extraction(uploaded_files, client, deployment):
    _load_ocr_engine()

    all_rows, errors = [], []
    progress = st.progress(0.0)
    n = len(uploaded_files)

    for idx, uf in enumerate(uploaded_files, start=1):
        st.write(f"⏳ Traitement de **{uf.name}** ({idx}/{n})…")
        pdf_path = _save_upload_to_temp(uf)
        try:
            _, final_df = pmv.process_pdf(
                pdf_path, client=client, deployment=deployment,
                poppler_path=POPPLER_PATH, debug=False,
                nom_fichier=uf.name,
            )
            if isinstance(final_df, pd.DataFrame) and not final_df.empty:
                if "fichier" not in final_df.columns:
                    final_df.insert(0, "fichier", uf.name)
                all_rows.append(final_df)
            else:
                errors.append(uf.name)
        except Exception as e:
            errors.append(f"{uf.name} : {e}")
        finally:
            try:
                os.remove(pdf_path)
            except OSError:
                pass
            progress.progress(idx / n)

    cumul = pd.concat(all_rows, ignore_index=True) if all_rows else pd.DataFrame()
    cumul = _fill_blanks(cumul)

    msg = f"{n} PDF traité(s), {len(cumul)} ligne(s)"
    if errors:
        msg += f" — {len(errors)} erreur(s) : " + " ; ".join(errors)
    return msg, cumul


# ------------------------------------------------------------
# Style / palette : bleu · bleu ciel · orange
# ------------------------------------------------------------
st.set_page_config(page_title="Extraction PMV", page_icon="📄", layout="wide")

st.markdown(
    """
    <style>
      :root {
        --bleu: #1565C0;
        --bleu-fonce: #0D47A1;
        --ciel: #4FC3F7;
        --ciel-clair: #E3F2FD;
        --orange: #FB8C00;
        --orange-fonce: #EF6C00;
      }
      /* Fond général */
      .stApp { background: linear-gradient(180deg, #F5FBFF 0%, #EAF4FD 100%); }
      /* Bandeau titre */
      .pmv-header {
        background: linear-gradient(120deg, var(--bleu-fonce) 0%, var(--bleu) 45%, var(--ciel) 100%);
        border-radius: 16px;
        padding: 28px 32px;
        margin-bottom: 22px;
        box-shadow: 0 6px 20px rgba(13,71,161,0.25);
      }
      .pmv-header h1 { color: #FFFFFF; margin: 0; font-size: 2rem; font-weight: 800; letter-spacing: .3px; }
      .pmv-header p  { color: #E3F2FD; margin: 6px 0 0; font-size: 1rem; }
      .pmv-header .accent { color: var(--orange); font-weight: 800; }
      /* Carte upload */
      [data-testid="stFileUploader"] {
        background: #FFFFFF;
        border: 2px dashed var(--ciel);
        border-radius: 14px;
        padding: 12px 16px;
      }
      [data-testid="stFileUploader"] label { color: var(--bleu-fonce); font-weight: 700; }
      /* Bouton principal (Lancer) -> orange */
      .stButton > button {
        background: var(--orange);
        color: #FFFFFF;
        border: 0;
        border-radius: 10px;
        padding: 0.6rem 1.6rem;
        font-weight: 700;
        font-size: 1rem;
        box-shadow: 0 4px 12px rgba(251,140,0,0.35);
        transition: all .15s ease;
      }
      .stButton > button:hover { background: var(--orange-fonce); transform: translateY(-1px); }
      .stButton > button:active { transform: translateY(0); }
      /* Bouton de téléchargement -> bleu */
      .stDownloadButton > button {
        background: var(--bleu);
        color: #FFFFFF;
        border: 0;
        border-radius: 10px;
        padding: 0.6rem 1.4rem;
        font-weight: 700;
        box-shadow: 0 4px 12px rgba(21,101,192,0.3);
      }
      .stDownloadButton > button:hover { background: var(--bleu-fonce); }
      /* Barre de progression -> orange */
      .stProgress > div > div > div > div { background-color: var(--orange); }
      /* En-tête du tableau */
      .stDataFrame thead tr th { background: var(--ciel-clair); color: var(--bleu-fonce); font-weight: 700; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="pmv-header">
      <h1>📄 Extraction <span class="accent">PMV</span></h1>
      <p>Importez vos PDF scannés — extraction automatique des champs vers Excel</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# Vérif des identifiants Azure
client, deployment = _load_azure_client()
if client is None:
    st.error(
        "Identifiants Azure OpenAI incomplets. Vérifiez le fichier `.env` "
        "(AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT, "
        "AZURE_OPENAI_API_VERSION, AZURE_OPENAI_DEPLOYMENT)."
    )
    st.stop()

uploaded = st.file_uploader(
    "Déposez vos PDF ici",
    type=["pdf"],
    accept_multiple_files=True,
)

col_btn, _ = st.columns([1, 4])
with col_btn:
    lancer = st.button("Lancer l'extraction", type="primary")

if lancer:
    if not uploaded:
        st.warning("Aucun PDF importé.")
    else:
        with st.spinner("Extraction en cours…"):
            msg, cumul = run_extraction(uploaded, client, deployment)

        st.success(msg)

        if not cumul.empty:
            st.dataframe(cumul, width="stretch")

            buf = BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                cumul.to_excel(writer, index=False, sheet_name="Extraction")
            buf.seek(0)

            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            st.download_button(
                "⬇️ Télécharger l'Excel",
                data=buf,
                file_name=f"extraction_{ts}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        else:
            st.info("Aucune donnée extraite.")