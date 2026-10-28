"""Imports et configuration communs à tous les modules (repris tels quels de pmv_api.py)."""


"""PMV — version AUTONOME, OCR Azure AI Document Intelligence (voir section « OCR AZURE »).
N'utilise ni Paddle ni pdf2image/poppler, et n'importe pas pmv.py.
Identique à pmv.py pour tout le reste : prompts, règles, garde-fous."""
import io
import os
import re
import json
import time
import logging
import threading
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Callable, Optional

import numpy as np
import pandas as pd
from openai import OpenAI
from dotenv import load_dotenv

# OCR settings below must see .env before module-level defaults are evaluated.
load_dotenv()

from llm_fallback import FallbackLLMClient, OllamaChat
from pmv_tracing import trace_step, traced_completion, observation, _update

log = logging.getLogger("pmv")



__all__ = ["Callable", "Dict", "FallbackLLMClient", "List", "OllamaChat", "OpenAI", "Optional", "ThreadPoolExecutor", "_update", "as_completed", "io", "json", "load_dotenv", "log", "logging", "np", "observation", "os", "pd", "re", "threading", "time", "trace_step", "traced_completion", "unicodedata"]
