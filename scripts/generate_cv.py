#!/usr/bin/env python3
"""
Generate the static full CV PDF from cv_data.py using Jinja2 + WeasyPrint.

Usage:
    python scripts/generate_cv.py                     # → assets/Resume_DevOps_SRE.pdf
    python scripts/generate_cv.py --output my_cv.pdf   # → custom path
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

from config.cv_data import CV_DATA

ASSETS_DIR = Path(__file__).parent.parent / "assets"
TEMPLATE_NAME = "cv_full_template.html"
DEFAULT_OUTPUT = ASSETS_DIR / "Resume_DevOps_SRE.pdf"


def generate_cv(output_path: Path) -> None:
    """Render CV data into HTML and convert to PDF."""
    env = Environment(loader=FileSystemLoader(str(ASSETS_DIR)))
    template = env.get_template(TEMPLATE_NAME)

    html = template.render(
        name=CV_DATA["name"],
        title=CV_DATA["title"],
        email=CV_DATA["email"],
        phone=CV_DATA["phone"],
        location=CV_DATA["location"],
        languages=CV_DATA["languages"],
        summary=CV_DATA["summary"],
        skills=CV_DATA["skills"],
        experience=CV_DATA["experience"],
        education=CV_DATA["education"],
    )

    HTML(string=html).write_pdf(str(output_path))
    print(f"CV generated: {output_path}")
    print(f"  Size: {output_path.stat().st_size / 1024:.1f} KB")


def main():
    parser = argparse.ArgumentParser(description="Generate CV PDF from cv_data.py")
    parser.add_argument("--output", "-o", type=str, default=str(DEFAULT_OUTPUT),
                        help="Output PDF path")
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    generate_cv(output_path)


if __name__ == "__main__":
    main()
