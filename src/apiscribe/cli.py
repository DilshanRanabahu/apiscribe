"""Command-line interface."""

from dataclasses import replace
from pathlib import Path
from typing import NoReturn, Optional

import typer

from apiscribe import auth, har, openapi, paths
from apiscribe.redact import Redactor, find_leaks

app = typer.Typer(
    help="Generate an OpenAPI 3 spec from a HAR file. "
    "Only use on APIs you own or are authorized to document.",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """apiscribe: HAR -> OpenAPI."""


@app.command()
def gen(
    har_file: Path = typer.Argument(..., exists=True, dir_okay=False, help="HAR file to read."),
    host: str = typer.Option(..., "--host", help="Only document requests to this host."),
    output: Path = typer.Option(Path("openapi.yaml"), "-o", "--output", help="Output YAML path."),
    title: Optional[str] = typer.Option(None, "--title", help="API title (default: '<host> API')."),
) -> None:
    """Generate openapi.yaml from a HAR recording."""
    try:
        data = har.load_har(har_file)
    except har.HarError as exc:
        _fail(str(exc))

    exchanges = har.extract_exchanges(data, host)
    if not exchanges:
        _fail(f"No JSON API calls to {host} found in {har_file}.")

    # Auth must look at raw headers, so it runs before redaction.
    exchanges = [replace(ex, security=auth.detect(ex)) for ex in exchanges]
    redactor = Redactor()
    exchanges = [redactor.redact(ex) for ex in exchanges]

    endpoints = paths.group_endpoints(exchanges)
    spec = openapi.build(endpoints, title=title or f"{host} API")
    text = openapi.to_yaml(spec)

    leaks = find_leaks(text, redactor.secrets)
    if leaks:
        _fail(f"{len(leaks)} sensitive value(s) would appear in the output. Nothing was written.")

    output.write_text(text, encoding="utf-8")
    total = len(data["log"]["entries"])
    typer.echo(
        f"{total} entries -> {len(exchanges)} JSON API calls -> {len(endpoints)} endpoints. Wrote {output}"
    )


def _fail(message: str) -> NoReturn:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(code=1)
