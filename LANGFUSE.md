# PMV traceability

Install into the environment used to run PMV:

```powershell
.\venvpmv\Scripts\python.exe -m pip install -r requirements-langfuse.txt
```

Create a Langfuse project (cloud or self-hosted), then add these settings to your
local `.env` with the project's API keys and server URL:

```dotenv
PMV_LANGFUSE_ENABLED=1
LANGFUSE_PUBLIC_KEY=pk-lf-your-project-key
LANGFUSE_SECRET_KEY=sk-lf-your-project-secret
LANGFUSE_BASE_URL=https://cloud.langfuse.com
```

Use the URL for your actual region or self-hosted server. Restart the application
after changing configuration. Set `PMV_LANGFUSE_ENABLED=0` to disable tracing.
No document content is sent to Langfuse while disabled. When enabled, document
text, filenames, prompts, responses and extracted values are sent to that server.
Client objects and API keys are excluded from trace inputs.

Process a PDF as usual, then open **Tracing** in your Langfuse project and select
the `process_pdf` trace. Each PDF has its own trace, including parallel processing.

- `extract_text_from_pdf` / `pdf-source-pages`: page text, native text vs OCR,
  OCR confidence and rotation when applicable.
- Extraction steps (for example `llm_extract_dates`): source inputs and the
  step's result after its Python rules have run.
- `chat.completions`: exact prompts, raw model response, model, elapsed time,
  reported token usage and errors. With the fallback client, the outer generation
  represents the logical request; nested Azure/Ollama generations represent the
  actual attempts. Do not sum logical and provider token counts together.
- `process_pdf` output: OCR text and final normalized row, for comparison with
  intermediate results. Steps that return `Non trouvé` can still contain a failed
  generation; inspect their children when debugging.

The SDK exports asynchronously. Keep the application running long enough to export;
in a short-lived script call `get_client().flush()` before exit if tracing is enabled.
Missing SDK/configuration or telemetry failures leave extraction running and emit
a warning. Check application logs if traces are missing.

These traces show the evidence supplied to the model, not its hidden reasoning or
proof that a specific passage caused a value. Field-level citations would require
a further extraction-schema change. No automatic cost is promised for custom Azure
deployment names, and the existing Ollama adapter does not expose token usage.

SDK reference: https://langfuse.com/docs/observability/sdk/instrumentation
