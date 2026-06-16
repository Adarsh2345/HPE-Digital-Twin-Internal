from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from simulation.models import SimulationResult

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"


def render_html(result: SimulationResult) -> str:
    environment = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(("html", "xml")),
    )
    return environment.get_template("report.html").render(result=result)


def render_pdf(result: SimulationResult) -> bytes:
    from weasyprint import HTML
    return HTML(string=render_html(result), base_url=str(TEMPLATE_DIR)).write_pdf()
