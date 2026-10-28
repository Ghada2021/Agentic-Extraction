# -*- coding: utf-8 -*-
"""
llm_fallback.py — Client LLM avec bascule automatique Azure OpenAI -> Ollama.

Le client exposé imite l'interface OpenAI utilisée partout dans pmv.py :

    resp = client.chat.completions.create(model=..., messages=..., max_completion_tokens=...)
    resp.choices[0].message.content

=> AUCUNE fonction d'extraction n'a besoin d'être modifiée.

Logique :
  1. On tente Azure OpenAI.
  2. En cas d'erreur (timeout, 429, 5xx, réseau, auth...) ou de réponse vide,
     on rejoue la même requête sur Ollama (llama3.1:8b par défaut).
  3. Disjoncteur (circuit breaker) : après N échecs Azure consécutifs, Azure est
     court-circuité pendant `cooldown` secondes -> on va directement sur Ollama
     au lieu d'attendre un timeout à chaque appel.
  4. Si Azure n'est pas configuré, tout passe par Ollama.

Thread-safe : un seul client peut être partagé par tous les workers.
"""

import logging
import threading
import time
from types import SimpleNamespace
from typing import List, Dict, Optional

import httpx

from pmv_tracing import traced_completion, observation, _update

log = logging.getLogger("pmv.llm")


def _fake_openai_response(content: str, provider: str, model: str):
    """Objet ayant la même forme qu'une réponse OpenAI (resp.choices[0].message.content)."""
    msg = SimpleNamespace(role="assistant", content=content)
    choice = SimpleNamespace(index=0, message=msg, finish_reason="stop")
    return SimpleNamespace(choices=[choice], model=model, provider=provider)


# ====================================================================
#                         OLLAMA (API native)
# ====================================================================
class OllamaChat:
    """
    Appel à Ollama via l'API native /api/chat (et non /v1) pour pouvoir fixer
    `num_ctx` : par défaut Ollama tronque silencieusement le contexte (2k-4k tokens),
    ce qui casserait les prompts qui envoient tout le texte OCR numéroté.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.1:8b",
        num_ctx: int = 16384,
        temperature: float = 0.0,
        timeout: float = 300.0,
        keep_alive: str = "30m",
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.num_ctx = num_ctx
        self.temperature = temperature
        self.keep_alive = keep_alive
        # httpx.Client est thread-safe et réutilise les connexions.
        self._http = httpx.Client(timeout=httpx.Timeout(timeout, connect=5.0))

    def is_available(self) -> bool:
        """Vérifie que le serveur Ollama répond ET que le modèle est téléchargé."""
        try:
            r = self._http.get(f"{self.base_url}/api/tags", timeout=3.0)
            r.raise_for_status()
            names = {m.get("name", "") for m in r.json().get("models", [])}
            ok = self.model in names or f"{self.model}:latest" in names
            if not ok:
                log.warning("Ollama répond mais le modèle '%s' est absent (ollama pull %s).",
                            self.model, self.model)
            return ok
        except Exception as e:
            log.warning("Ollama indisponible sur %s : %s", self.base_url, e)
            return False

    def chat(self, messages: List[Dict[str, str]], max_tokens: Optional[int] = None) -> str:
        options = {"temperature": self.temperature, "num_ctx": self.num_ctx}
        if max_tokens:
            options["num_predict"] = int(max_tokens)
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "keep_alive": self.keep_alive,
            "options": options,
        }
        r = self._http.post(f"{self.base_url}/api/chat", json=payload)
        r.raise_for_status()
        return ((r.json().get("message") or {}).get("content") or "").strip()


# ====================================================================
#                   CLIENT AVEC BASCULE AUTOMATIQUE
# ====================================================================
class _Completions:
    def __init__(self, parent: "FallbackLLMClient"):
        self._parent = parent

    def create(self, model=None, messages=None, max_completion_tokens=None,
               max_tokens=None, **kwargs):
        # `model` est ignoré : chaque fournisseur utilise son propre modèle.
        return self._parent._create(messages or [], max_completion_tokens or max_tokens, **kwargs)


class FallbackLLMClient:
    def __init__(
        self,
        azure_client=None,
        azure_deployment: Optional[str] = None,
        ollama: Optional[OllamaChat] = None,
        fallback_on_empty: bool = True,
        max_failures: int = 3,
        cooldown: float = 120.0,
    ):
        self.azure = azure_client
        self.azure_deployment = azure_deployment
        self.ollama = ollama
        self.fallback_on_empty = fallback_on_empty
        self.max_failures = max_failures
        self.cooldown = cooldown

        self.chat = SimpleNamespace(completions=_Completions(self))

        self._lock = threading.Lock()
        self._fail_count = 0
        self._azure_blocked_until = 0.0
        self._local = threading.local()
        self.stats = {"azure": 0, "ollama": 0, "azure_errors": 0, "azure_empty": 0}

    # ---------- disjoncteur ----------
    def _azure_allowed(self) -> bool:
        if self.azure is None:
            return False
        with self._lock:
            return time.monotonic() >= self._azure_blocked_until

    def _azure_ok(self):
        with self._lock:
            self._fail_count = 0

    def _azure_failed(self, err: Exception):
        with self._lock:
            self.stats["azure_errors"] += 1
            self._fail_count += 1
            if self._fail_count >= self.max_failures:
                self._azure_blocked_until = time.monotonic() + self.cooldown
                self._fail_count = 0
                log.warning("Azure KO %d fois de suite -> Ollama seul pendant %.0fs",
                            self.max_failures, self.cooldown)
        log.warning("Azure OpenAI erreur (%s: %s) -> bascule Ollama",
                    type(err).__name__, str(err)[:200])

    # ---------- compteurs par thread (= par PDF) ----------
    def reset_thread_usage(self):
        self._local.usage = {"azure": 0, "ollama": 0}

    def thread_usage(self) -> Dict[str, int]:
        return dict(getattr(self._local, "usage", {"azure": 0, "ollama": 0}))

    def _bump(self, provider: str):
        with self._lock:
            self.stats[provider] += 1
        usage = getattr(self._local, "usage", None)
        if usage is None:
            self.reset_thread_usage()
            usage = self._local.usage
        usage[provider] += 1

    # ---------- appel ----------
    def _create(self, messages, max_tokens, **kwargs):
        last_err = None
        azure_resp = None

        if self._azure_allowed():
            try:
                params = dict(model=self.azure_deployment, messages=messages, **kwargs)
                if max_tokens:
                    params["max_completion_tokens"] = max_tokens
                azure_resp = traced_completion(self.azure.chat.completions.create, **params)
                self._azure_ok()
                content = (azure_resp.choices[0].message.content or "").strip()
                if content or not self.fallback_on_empty or self.ollama is None:
                    self._bump("azure")
                    return azure_resp
                with self._lock:
                    self.stats["azure_empty"] += 1
                log.info("Azure a renvoyé une réponse vide -> bascule Ollama")
            except Exception as e:
                last_err = e
                self._azure_failed(e)

        if self.ollama is not None:
            try:
                with observation("ollama.chat", as_type="generation", model=self.ollama.model,
                                 input=messages, metadata={"provider": "ollama"},
                                 model_parameters={"max_tokens": max_tokens}) as span:
                    content = self.ollama.chat(messages, max_tokens=max_tokens)
                    _update(span, output=content)
                self._bump("ollama")
                return _fake_openai_response(content, "ollama", self.ollama.model)
            except Exception as e:
                log.error("Ollama erreur : %s", e)
                if azure_resp is not None:      # Azure avait répondu (vide) : on le garde
                    self._bump("azure")
                    return azure_resp
                raise RuntimeError(f"Azure et Ollama indisponibles (Ollama: {e})") from (last_err or e)

        if last_err is not None:
            raise last_err
        raise RuntimeError("Aucun fournisseur LLM configuré (ni Azure ni Ollama).")
