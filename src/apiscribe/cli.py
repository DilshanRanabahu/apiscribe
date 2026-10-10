"""Command-line interface."""

from pathlib import Path

import typer

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
) -> None:
    """Generate openapi.yaml from a HAR recording."""
    typer.echo("Not implemented yet.", err=True)
    raise typer.Exit(code=1)
