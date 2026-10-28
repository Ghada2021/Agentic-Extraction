"""Optional Langfuse instrumentation. Disabled unless explicitly configured."""
import inspect
import logging
import os
from contextlib import contextmanager
from functools import lru_cache, wraps

log = logging.getLogger("pmv.tracing")


@lru_cache(maxsize=1)
def _client():
    from dotenv import load_dotenv
    load_dotenv()
    if os.getenv("PMV_LANGFUSE_ENABLED", "0").lower() not in ("1", "true", "yes"):
        return None
    try:
        if not all(os.getenv(k) for k in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL")):
            raise ValueError("Set LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY and LANGFUSE_BASE_URL")
        from langfuse import get_client
        return get_client()
    except Exception as exc:
        log.warning("Langfuse tracing unavailable: %s", type(exc).__name__)
        return None


def _update(span, **kwargs):
    if span is not None:
        try:
            span.update(**kwargs)
        except Exception:
            log.warning("Langfuse update failed", exc_info=False)


@contextmanager
def observation(name, **kwargs):
    client = _client()
    context = span = None
    if client is not None:
        try:
            context = client.start_as_current_observation(name=name, **kwargs)
            span = context.__enter__()
        except Exception:
            context = None
            log.warning("Langfuse observation failed", exc_info=False)
    try:
        yield span
    except BaseException as exc:
        _update(span, level="ERROR", status_message=str(exc))
        raise
    finally:
        if context is not None:
            try:
                context.__exit__(None, None, None)
            except Exception:
                log.warning("Langfuse observation close failed", exc_info=False)


def _serializable(value):
    if hasattr(value, "to_json"):
        import json
        return json.loads(value.to_json(orient="records", force_ascii=False))
    if isinstance(value, (tuple, list)):
        return [_serializable(item) for item in value]
    return value


def trace_step(*input_names):
    """Capture only named inputs; never serialize clients or credentials."""
    def decorate(func):
        signature = inspect.signature(func)
        @wraps(func)
        def wrapped(*args, **kwargs):
            if _client() is None:
                return func(*args, **kwargs)
            bound = signature.bind(*args, **kwargs).arguments
            inputs = {k: os.path.basename(os.fspath(v)) if k == "pdf_path" else v
                      for k, v in bound.items() if k in input_names}
            with observation(func.__name__, input=inputs) as span:
                result = func(*args, **kwargs)
                try:
                    _update(span, output=_serializable(result))
                except Exception:
                    log.warning("Langfuse output serialization failed", exc_info=False)
                return result
        return wrapped
    return decorate


def traced_completion(create, **kwargs):
    """Trace actual prompts and raw responses, including failed provider attempts."""
    with observation("chat.completions", as_type="generation",
                     model=kwargs.get("model"), input=kwargs.get("messages"),
                     model_parameters={k: v for k, v in kwargs.items()
                                       if k in ("temperature", "max_tokens", "max_completion_tokens")}) as span:
        result = create(**kwargs)
        try:
            usage = getattr(result, "usage", None)
            details = {k: v for k, v in {
                "input": getattr(usage, "prompt_tokens", None),
                "output": getattr(usage, "completion_tokens", None),
            }.items() if v is not None}
            _update(span, output=result.choices[0].message.content,
                    model=getattr(result, "model", None) or kwargs.get("model"),
                    usage_details=details,
                    metadata={"provider": getattr(result, "provider", "azure"),
                              "empty_response": not bool(result.choices[0].message.content)})
        except Exception:
            log.warning("Langfuse response serialization failed", exc_info=False)
        return result
