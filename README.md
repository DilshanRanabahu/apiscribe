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
