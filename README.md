# apiscribe

Generate an OpenAPI 3 spec (`openapi.yaml`) from a HAR file recorded in your browser's DevTools.

> **Only use apiscribe on APIs you own or have permission to document.**
> HAR files contain tokens, cookies and personal data. Never commit them (`*.har` is git-ignored).

## Install (development)

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux
pip install -e ".[dev]"
```

## Usage

```bash
apiscribe gen traffic.har --host api.example.com -o openapi.yaml
```

Options: `--title "My API"` sets `info.title` (default: `<host> API`).

## How to record a HAR file

1. Open DevTools (F12), go to the **Network** tab and tick **Preserve log**.
2. Use the website: click through every feature you want documented.
3. Right-click the request list and choose **Save all as HAR**.

More traffic gives better results: a field seen in every response is marked `required`, and a field that was ever `null` is marked `nullable`.

## What it does

| Step | Module | Example |
|---|---|---|
| Keep only JSON API calls to `--host` | `har.py` | drops images, HTML, CORS preflights |
| Mask secrets | `redact.py` | `Bearer eyJ...`, cookies, passwords, emails, signed URLs |
| Group URLs into endpoints | `paths.py` | `/orders/42`, `/orders/57` -> `/orders/{order_id}` |
| Infer and merge schemas | `schema.py` | required vs optional, nullable, nested, formats |
| Detect auth | `auth.py` | bearer (JWT), basic, API key header/query, session cookie |
| Write the spec | `openapi.py` | OpenAPI 3.0.3 YAML, deterministic output |

**Leak check:** before writing, apiscribe searches the generated YAML for every raw token,
cookie and password it saw. If any would appear, it refuses to write the file.
The output never contains example values, only structure.

## Limitations

- Slugs (`/products/red-shoe`) become a parameter only when at least 3 variants with similar
  responses were recorded; otherwise each stays a separate path.
- Only JSON bodies are documented (no form data, XML or file uploads).
- Always review the generated spec before publishing it.

## Project layout

```
src/apiscribe/
  cli.py       command-line interface (Typer)
  har.py       load HAR, keep only JSON API calls
  redact.py    mask tokens, cookies, passwords, emails
  paths.py     /orders/42 -> /orders/{order_id}
  schema.py    infer and merge JSON schemas
  auth.py      detect auth scheme
  openapi.py   assemble and write openapi.yaml
tests/         pytest suite, one file per module
```

## Tests

```bash
pytest
```
