"""Generate PROJECT_STATUS.pdf from PROJECT_STATUS.md using reportlab.

Single-purpose build script — not part of the application. Run once to
produce the PDF for HR submission. Avoids markdown tables by rendering
bullet lists and prose only.
"""
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, ListFlowable, ListItem
)

ROOT = Path(__file__).parent
SRC = ROOT / "PROJECT_STATUS.md"
DST = ROOT / "PROJECT_STATUS.pdf"


def _styles():
    s = getSampleStyleSheet()
    base_font = "Helvetica"
    return {
        "title": ParagraphStyle(
            "title", parent=s["Title"], fontName="Helvetica-Bold",
            fontSize=20, leading=24, spaceAfter=12, textColor=colors.HexColor("#0b3d91"),
        ),
        "meta": ParagraphStyle(
            "meta", parent=s["Normal"], fontName=base_font,
            fontSize=10, leading=14, textColor=colors.HexColor("#444444"), spaceAfter=2,
        ),
        "h1": ParagraphStyle(
            "h1", parent=s["Heading1"], fontName="Helvetica-Bold",
            fontSize=14, leading=18, spaceBefore=14, spaceAfter=8,
            textColor=colors.HexColor("#0b3d91"),
        ),
        "h2": ParagraphStyle(
            "h2", parent=s["Heading2"], fontName="Helvetica-Bold",
            fontSize=12, leading=16, spaceBefore=10, spaceAfter=6,
            textColor=colors.HexColor("#1f4e79"),
        ),
        "body": ParagraphStyle(
            "body", parent=s["BodyText"], fontName=base_font,
            fontSize=10.5, leading=15, alignment=TA_JUSTIFY, spaceAfter=6,
        ),
        "bullet": ParagraphStyle(
            "bullet", parent=s["BodyText"], fontName=base_font,
            fontSize=10.5, leading=15, alignment=TA_LEFT, spaceAfter=2,
        ),
        "italic": ParagraphStyle(
            "italic", parent=s["BodyText"], fontName="Helvetica-Oblique",
            fontSize=10, leading=14, textColor=colors.HexColor("#666666"),
            spaceBefore=12,
        ),
    }


def _inline(text: str) -> str:
    """Convert minimal markdown inline syntax to reportlab tags."""
    out = text
    # bold **x**
    import re
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
    # code `x` → monospace
    out = re.sub(r"`([^`]+)`", r'<font face="Courier" size="9.5">\1</font>', out)
    # escape ampersands (reportlab uses XML)
    out = out.replace("&", "&amp;").replace("&amp;lt;", "&lt;").replace("&amp;gt;", "&gt;")
    # restore bold/code tags broken by the escape
    out = (
        out.replace("&amp;lt;b&amp;gt;", "<b>")
           .replace("&amp;lt;/b&amp;gt;", "</b>")
    )
    return out


def build():
    styles = _styles()
    md = SRC.read_text(encoding="utf-8")
    story = []

    in_bullets = []
    title_done = False
    meta_lines = []

    def flush_bullets():
        if in_bullets:
            items = [
                ListItem(Paragraph(_inline(b), styles["bullet"]), leftIndent=10)
                for b in in_bullets
            ]
            story.append(ListFlowable(items, bulletType="bullet", leftIndent=14, bulletFontSize=9))
            story.append(Spacer(1, 4))
            in_bullets.clear()

    for raw in md.splitlines():
        line = raw.rstrip()
        if not line.strip():
            flush_bullets()
            continue

        if line.startswith("# "):
            flush_bullets()
            story.append(Paragraph(_inline(line[2:].strip()), styles["title"]))
            title_done = True
        elif line.startswith("## "):
            flush_bullets()
            story.append(Paragraph(_inline(line[3:].strip()), styles["h1"]))
        elif line.startswith("### "):
            flush_bullets()
            story.append(Paragraph(_inline(line[4:].strip()), styles["h2"]))
        elif line.startswith("- "):
            in_bullets.append(line[2:].strip())
        elif line.startswith("*") and line.endswith("*") and len(line) > 2 and "End of report" in line:
            flush_bullets()
            story.append(Paragraph(_inline(line.strip("*").strip()), styles["italic"]))
        elif line.startswith("**") and "**" in line[2:]:
            # Bold metadata line — Prepared by, Date, etc.
            flush_bullets()
            story.append(Paragraph(_inline(line), styles["meta"]))
        else:
            flush_bullets()
            story.append(Paragraph(_inline(line), styles["body"]))

    flush_bullets()

    doc = SimpleDocTemplate(
        str(DST), pagesize=A4,
        leftMargin=2.2 * cm, rightMargin=2.2 * cm,
        topMargin=2.0 * cm, bottomMargin=2.0 * cm,
        title="School LLM — Project Status Report",
        author="Gangadhar Reddy",
    )
    doc.build(story)
    print(f"Wrote {DST} ({DST.stat().st_size:,} bytes)")


if __name__ == "__main__":
    build()
