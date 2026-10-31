"""`docs edl`: print reference docs installed with the package, from any directory."""

from importlib import resources

import typer

from motion_studio.cli._output import JsonOption, emit

app = typer.Typer(help="Print reference docs.", no_args_is_help=True)


@app.command()
def edl(as_json: JsonOption = False) -> None:
    """Print the EDL reference: talk segments and events, product scenes, and music."""
    doc = resources.files("motion_studio") / "reference" / "edl.md"
    text = doc.read_text(encoding="utf-8")
    emit(as_json, {"path": str(doc), "text": text}, [text.rstrip("\n")])
