"""Generate TECHNICAL_WHITE_PAPER.pdf from the markdown source.

Single-purpose build script. Renders the white paper with a polished
layout suitable for a senior-engineer audience: title page, section
hierarchy, fenced code blocks in monospace, justified body text, and
page numbers.
"""
import re
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak,
    ListFlowable, ListItem, Preformatted, KeepTogether,
)

ROOT = Path(__file__).parent
SRC = ROOT / "TECHNICAL_WHITE_PAPER.md"
DST = ROOT / "TECHNICAL_WHITE_PAPER.pdf"

NAVY = colors.HexColor("#0b3d91")
SLATE = colors.HexColor("#1f4e79")
DIM = colors.HexColor("#555555")
CODE_BG = colors.HexColor("#f4f4f4")
CODE_BORDER = colors.HexColor("#cccccc")


def _styles():
    s = getSampleStyleSheet()
    return {
        "cover_title": ParagraphStyle(
            "cover_title", parent=s["Title"], fontName="Helvetica-Bold",
            fontSize=24, leading=30, alignment=1, spaceAfter=16, textColor=NAVY,
        ),
        "cover_sub": ParagraphStyle(
            "cover_sub", parent=s["Normal"], fontName="Helvetica",
            fontSize=13, leading=18, alignment=1, textColor=DIM, spaceAfter=4,
        ),
        "h1": ParagraphStyle(
            "h1", parent=s["Heading1"], fontName="Helvetica-Bold",
            fontSize=15, leading=20, spaceBefore=18, spaceAfter=8,
            textColor=NAVY, keepWithNext=1,
        ),
        "h2": ParagraphStyle(
            "h2", parent=s["Heading2"], fontName="Helvetica-Bold",
            fontSize=12.5, leading=17, spaceBefore=12, spaceAfter=6,
            textColor=SLATE, keepWithNext=1,
        ),
        "body": ParagraphStyle(
            "body", parent=s["BodyText"], fontName="Helvetica",
            fontSize=10.5, leading=15, alignment=TA_JUSTIFY, spaceAfter=6,
        ),
        "bullet": ParagraphStyle(
            "bullet", parent=s["BodyText"], fontName="Helvetica",
            fontSize=10.5, leading=15, alignment=TA_LEFT, spaceAfter=2,
        ),
        "meta": ParagraphStyle(
            "meta", parent=s["Normal"], fontName="Helvetica",
            fontSize=10.5, leading=14, textColor=DIM, spaceAfter=2,
        ),
        "italic_close": ParagraphStyle(
            "italic_close", parent=s["BodyText"], fontName="Helvetica-Oblique",
            fontSize=10, leading=14, textColor=DIM, alignment=1, spaceBefore=18,
        ),
        # Kept for compatibility but not used — the rewritten markdown has
        # no fenced code blocks (single-font policy).
        "code": ParagraphStyle(
            "code", parent=s["BodyText"], fontName="Helvetica",
            fontSize=10, leading=14, leftIndent=8, rightIndent=8,
            spaceBefore=4, spaceAfter=8, backColor=CODE_BG,
            borderColor=CODE_BORDER, borderWidth=0.4, borderPadding=6,
        ),
    }


def _inline(text: str) -> str:
    """Convert minimal markdown inline syntax to reportlab tags.

    Single-font policy: identifiers and code-like terms stay in the body
    font, rendered as bold via the **token** markdown syntax. No Courier.
    """
    # Escape XML special chars first
    out = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # bold **x**
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
    # italic *x*
    out = re.sub(r"(?<!\*)\*([^*\n]+?)\*(?!\*)", r"<i>\1</i>", out)
    # inline backticks → render as bold (same font, no Courier)
    out = re.sub(r"`([^`]+)`", r"<b>\1</b>", out)
    return out


def _page_footer(canvas, doc):
    """Page number footer on every page except the cover."""
    canvas.saveState()
    if doc.page > 1:
        canvas.setFont("Helvetica", 9)
        canvas.setFillColor(DIM)
        canvas.drawCentredString(A4[0] / 2, 1.2 * cm, f"— {doc.page} —")
        canvas.setFont("Helvetica-Oblique", 8)
        canvas.drawString(
            2.2 * cm, 1.2 * cm,
            "School LLM — Technical White Paper"
        )
        canvas.drawRightString(
            A4[0] - 2.2 * cm, 1.2 * cm,
            "Gangadhar Reddy"
        )
    canvas.restoreState()


def build():
    styles = _styles()
    md = SRC.read_text(encoding="utf-8")
    story = []

    # ── Cover page ────────────────────────────────────────────────
    story.append(Spacer(1, 6 * cm))
    story.append(Paragraph("School LLM", styles["cover_title"]))
    story.append(Paragraph(
        "Technical White Paper on the AI / RAG Architecture",
        styles["cover_sub"],
    ))
    story.append(Spacer(1, 2 * cm))
    story.append(Paragraph("<b>Author</b>: Gangadhar Reddy", styles["cover_sub"]))
    story.append(Paragraph("<b>Date</b>: 26 May 2026", styles["cover_sub"]))
    story.append(Paragraph(
        "<b>Audience</b>: Senior GenAI / RAG reviewers", styles["cover_sub"],
    ))
    story.append(Spacer(1, 1 * cm))
    story.append(Paragraph(
        "A code-grounded narrative of the retrieval pipeline, "
        "vector-store design, prompt-engineering strategy, multi-provider "
        "LLM orchestration, and quality-assurance loop that I designed "
        "and implemented.",
        ParagraphStyle(
            "tagline", parent=styles["body"], fontSize=10.5,
            alignment=1, textColor=DIM, leftIndent=2 * cm, rightIndent=2 * cm,
        ),
    ))
    story.append(PageBreak())

    # ── Body ──────────────────────────────────────────────────────
    in_code = False
    code_buf = []
    in_bullets = []

    def flush_bullets():
        if in_bullets:
            items = [
                ListItem(Paragraph(_inline(b), styles["bullet"]), leftIndent=10)
                for b in in_bullets
            ]
            story.append(ListFlowable(
                items, bulletType="bullet", leftIndent=14, bulletFontSize=9,
            ))
            story.append(Spacer(1, 4))
            in_bullets.clear()

    def flush_code():
        if code_buf:
            code_text = "\n".join(code_buf)
            # Strip a trailing blank line if present.
            code_text = code_text.rstrip()
            story.append(Preformatted(code_text, styles["code"]))
            code_buf.clear()

    for raw in md.splitlines():
        line = raw

        # Fenced code block toggle
        if line.strip().startswith("```"):
            if in_code:
                flush_code()
                in_code = False
            else:
                flush_bullets()
                in_code = True
            continue

        if in_code:
            code_buf.append(line)
            continue

        stripped = line.strip()
        if not stripped:
            flush_bullets()
            continue

        # The very first H1 in the body is the document title — we already
        # rendered a cover, so skip it.
        if stripped.startswith("# "):
            continue

        if stripped.startswith("## "):
            flush_bullets()
            story.append(Paragraph(_inline(stripped[3:].strip()), styles["h1"]))
            continue

        if stripped.startswith("### "):
            flush_bullets()
            story.append(Paragraph(_inline(stripped[4:].strip()), styles["h2"]))
            continue

        if stripped.startswith("- "):
            in_bullets.append(stripped[2:].strip())
            continue

        if stripped.startswith("*") and stripped.endswith("*") and "Prepared by" in stripped:
            flush_bullets()
            story.append(Paragraph(
                _inline(stripped.strip("*").strip()),
                styles["italic_close"],
            ))
            continue

        if stripped.startswith("**") and stripped.count("**") >= 2 and len(stripped) < 200:
            flush_bullets()
            story.append(Paragraph(_inline(stripped), styles["meta"]))
            continue

        flush_bullets()
        story.append(Paragraph(_inline(stripped), styles["body"]))

    flush_bullets()
    flush_code()

    doc = SimpleDocTemplate(
        str(DST), pagesize=A4,
        leftMargin=2.2 * cm, rightMargin=2.2 * cm,
        topMargin=2.0 * cm, bottomMargin=2.2 * cm,
        title="School LLM — Technical White Paper",
        author="Gangadhar Reddy",
        subject="AI / RAG architecture brief",
    )
    doc.build(story, onFirstPage=_page_footer, onLaterPages=_page_footer)
    print(f"Wrote {DST} ({DST.stat().st_size:,} bytes)")


if __name__ == "__main__":
    build()
