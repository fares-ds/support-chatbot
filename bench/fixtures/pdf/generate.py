"""Build the synthetic PDF used to compare parsers (#16).

Run from the repository root:

    uv run --with reportlab --with arabic-reshaper \
        python bench/fixtures/pdf/generate.py
"""

from pathlib import Path

import arabic_reshaper
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Table, TableStyle

ROOT = Path(__file__).resolve().parent
FONT_PATH = ROOT / "fonts" / "NotoNaskhArabic-Regular.ttf"
OUTPUT = ROOT / "parser-sample.pdf"
PAGE_WIDTH, PAGE_HEIGHT = A4
LEFT = 20 * mm
RIGHT = PAGE_WIDTH - 20 * mm
ARABIC_FONT = "NotoNaskhArabic"


def draw_arabic(canvas: Canvas, text: str, y: float, size: int, *, bullet: bool = False) -> None:
    """Draw logical-order Arabic from the right, one shaped letter at a time.

    A single text run would store the letters in display order. Placing each letter keeps
    the text layer in reading order while the page still reads right to left.
    """
    edge = RIGHT
    if bullet:
        canvas.setFont("Helvetica", size)
        canvas.drawRightString(edge, y, "-")
        edge -= 6 * mm
    shaped = arabic_reshaper.reshape(text)
    canvas.setFont(ARABIC_FONT, size)
    x = edge
    for letter in shaped:
        width = canvas.stringWidth(letter, ARABIC_FONT, size)
        x -= width
        canvas.drawString(x, y, letter)


def draw_page_number(canvas: Canvas, number: int) -> None:
    canvas.setFillColor(colors.black)
    canvas.setFont("Helvetica", 10)
    canvas.drawCentredString(PAGE_WIDTH / 2, 12 * mm, f"Page {number}")


def draw_heading(canvas: Canvas, text: str, y: float) -> float:
    canvas.setFont("Helvetica-Bold", 16)
    canvas.drawString(LEFT, y, text)
    return y - 12 * mm


def draw_lines(
    canvas: Canvas, lines: list[str], y: float, font: str = "Helvetica", size: int = 12
) -> float:
    canvas.setFont(font, size)
    for line in lines:
        canvas.drawString(LEFT, y, line)
        y -= 7 * mm
    return y


def french_lists(canvas: Canvas) -> None:
    y = PAGE_HEIGHT - 25 * mm
    y = draw_heading(canvas, "Listes en français", y)
    y = draw_lines(
        canvas,
        [
            "Cette page contient un titre,",
            "une liste à puces et une liste numérotée.",
        ],
        y,
    )
    y -= 4 * mm
    y = draw_lines(
        canvas,
        [
            "- Le guichet ouvre à 9 h.",
            "- Un virement coûte 50 DA.",
            "- La carte arrive en trois jours.",
        ],
        y,
    )
    y -= 4 * mm
    draw_lines(
        canvas,
        [
            "1. Ouvrir le compte.",
            "2. Choisir le montant.",
            "3. Confirmer le virement.",
        ],
        y,
    )
    draw_page_number(canvas, 1)


def table_page(canvas: Canvas) -> None:
    y = PAGE_HEIGHT - 25 * mm
    y = draw_heading(canvas, "Tableau avec en-tête", y)
    draw_lines(canvas, ["Le tableau ci-dessous a une ligne d'en-tête et trois lignes."], y)
    rows = [
        ["Service", "Frais", "Délai"],
        ["Virement", "50 DA", "Immédiat"],
        ["Carte", "500 DA", "3 jours"],
        ["Recharge", "0 DA", "Immédiat"],
    ]
    table = Table(rows, colWidths=[55 * mm, 40 * mm, 40 * mm])
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 11),
                ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.9, 0.9, 0.9)),
                ("GRID", (0, 0), (-1, -1), 0.6, colors.black),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    _, height = table.wrapOn(canvas, RIGHT - LEFT, 120 * mm)
    table.drawOn(canvas, LEFT, y - 18 * mm - height)
    draw_page_number(canvas, 2)


def two_columns(canvas: Canvas) -> None:
    y = PAGE_HEIGHT - 25 * mm
    draw_heading(canvas, "Deux colonnes", y)
    gutter = 12 * mm
    column_width = (RIGHT - LEFT - gutter) / 2
    top = y - 8 * mm
    left_lines = [
        "Colonne gauche",
        "Le client demande une",
        "carte depuis l'agence.",
        "Le conseiller vérifie",
        "la pièce d'identité.",
        "La demande part le",
        "jour même.",
    ]
    right_lines = [
        "Colonne droite",
        "Le plafond du virement",
        "est de 100 000 DA.",
        "Au-delà, l'agence doit",
        "valider l'opération.",
        "Le reçu indique le",
        "numéro de référence.",
    ]
    for index, line in enumerate(left_lines):
        font = "Helvetica-Bold" if index == 0 else "Helvetica"
        canvas.setFont(font, 12)
        canvas.drawString(LEFT, top - index * 7 * mm, line)
    for index, line in enumerate(right_lines):
        font = "Helvetica-Bold" if index == 0 else "Helvetica"
        canvas.setFont(font, 12)
        canvas.drawString(LEFT + column_width + gutter, top - index * 7 * mm, line)
    draw_page_number(canvas, 3)


def arabic_page(canvas: Canvas) -> None:
    y = PAGE_HEIGHT - 25 * mm
    draw_arabic(canvas, "صفحة عربية: عنوان وقائمة وفقرة", y, 18)
    y -= 14 * mm
    lines = [
        "ساعات العمل من التاسعة إلى الخامسة.",
        "التحويل يكلف خمسين دينارا.",
        "البطاقة تصل خلال ثلاثة أيام.",
        "يمكن للزبون طلب بطاقة جديدة من الوكالة. يصل الرد في نفس اليوم،",
        "والبطاقة خلال ثلاثة أيام عمل.",
    ]
    for index, line in enumerate(lines):
        draw_arabic(canvas, line, y, 13, bullet=index < 3)
        y -= 9 * mm
    draw_page_number(canvas, 4)


def main() -> None:
    if not FONT_PATH.is_file():
        raise SystemExit(f"Missing font: {FONT_PATH}")
    pdfmetrics.registerFont(TTFont(ARABIC_FONT, str(FONT_PATH)))
    canvas = Canvas(str(OUTPUT), pagesize=A4)
    canvas.setTitle("Parser sample")
    for draw in (french_lists, table_page, two_columns, arabic_page):
        draw(canvas)
        canvas.showPage()
    canvas.save()
    print(OUTPUT)


if __name__ == "__main__":
    main()
