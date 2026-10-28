"""Connexion aux LLM (Azure OpenAI, repli Ollama).
Code repris tel quel de pmv_api.py (aucune modification)."""
from ._base import *  # noqa: F401,F403


# ====================================================================
#                         AZURE OPENAI
# ====================================================================
def init_azure_openai(timeout: float = 60.0, max_retries: int = 1):
    """Initialize Azure OpenAI client from .env and return it.

    timeout / max_retries courts : si Azure rame, on bascule vite sur Ollama
    au lieu d'attendre les 10 min / 2 retries par défaut du SDK.

    Reads AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_API_VERSION, AZURE_OPENAI_DEPLOYMENT from .env.
    Returns (client, deployment) or (None, None) if credentials incomplete.
    """
    load_dotenv()

    api_key    = os.getenv("AZURE_OPENAI_API_KEY", "").strip()
    endpoint   = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
    api_ver    = os.getenv("AZURE_OPENAI_API_VERSION", "").strip()
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "").strip()

    if not all([api_key, endpoint, api_ver, deployment]):
        return None, None

    os.environ["OPENAI_API_KEY"] = api_key

    if not endpoint.endswith("/openai/v1"):
        if not endpoint.endswith("/"):
            endpoint += "/"
        endpoint += "openai/v1"

    client = OpenAI(
        api_key=api_key,
        base_url=endpoint,
        default_headers={"api-version": api_ver},
        timeout=timeout,
        max_retries=max_retries,
    )
    return client, deployment


def init_llm_client():
    """
    Client LLM principal : Azure OpenAI + backup Ollama (llama3.1:8b).
    Remplace init_azure_openai() dans l'app — même signature de retour (client, deployment).

    Variables .env (toutes optionnelles) :
      LLM_FALLBACK_ENABLED=1            -> 0 pour désactiver le backup
      OLLAMA_BASE_URL=http://localhost:11434
      OLLAMA_MODEL=llama3.1:8b
      OLLAMA_NUM_CTX=16384              -> contexte (le texte OCR complet est envoyé)
      OLLAMA_TIMEOUT=300
      AZURE_TIMEOUT=60
      LLM_BREAKER_FAILURES=3            -> nb d'échecs Azure avant de le court-circuiter
      LLM_BREAKER_COOLDOWN=120          -> durée (s) pendant laquelle on reste sur Ollama
    Renvoie (None, None) si ni Azure ni Ollama ne sont utilisables.
    """
    load_dotenv()
    azure_client, deployment = init_azure_openai(timeout=float(os.getenv("AZURE_TIMEOUT", "60")))

    ollama = None
    if os.getenv("LLM_FALLBACK_ENABLED", "1").strip() not in ("0", "false", "False", "no"):
        ollama = OllamaChat(
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            model=os.getenv("OLLAMA_MODEL", "llama3.1:8b"),
            num_ctx=int(os.getenv("OLLAMA_NUM_CTX", "16384")),
            timeout=float(os.getenv("OLLAMA_TIMEOUT", "300")),
        )
        if not ollama.is_available():
            ollama = None

    if azure_client is None and ollama is None:
        return None, None
    if azure_client is None:
        log.warning("Azure OpenAI non configuré -> tout passe par Ollama (%s)", os.getenv("OLLAMA_MODEL", "llama3.1:8b"))
    if ollama is None:
        log.warning("Backup Ollama indisponible -> Azure seul")

    client = FallbackLLMClient(
        azure_client=azure_client,
        azure_deployment=deployment,
        ollama=ollama,
        max_failures=int(os.getenv("LLM_BREAKER_FAILURES", "3")),
        cooldown=float(os.getenv("LLM_BREAKER_COOLDOWN", "120")),
    )
    return client, (deployment or (ollama.model if ollama else None))
