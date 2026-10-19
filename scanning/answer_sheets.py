
from io import BytesIO
import math

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


from .layout import (
    BUBBLE_RADIUS,
    BUBBLE_SPACING,
    BUBBLE_START_X,
    GRID_TOP,
    MARGIN,
    PAGE_HEIGHT,
    PAGE_WIDTH,
    QUESTION_X,
    QUESTIONS_PER_PAGE,
    ROW_HEIGHT,
    START_Y,
    bubble_center,
    row_baseline_y,
)

CONTENT_WIDTH = PAGE_WIDTH - (2 * MARGIN)

# Professional monochrome print palette
INK = colors.HexColor("#172033")
MUTED = colors.HexColor("#64748B")
LIGHT_BORDER = colors.HexColor("#D7DEE8")
ROW_SHADE = colors.HexColor("#F5F7FA")
HEADER_SHADE = colors.HexColor("#E9EEF5")
WHITE = colors.white


def draw_bubble(pdf, x, y, label=None, radius=6):
    """Draw a clean, empty answer bubble for OMR scanning."""
    pdf.setStrokeColor(INK)
    pdf.setLineWidth(0.9)
    pdf.circle(x, y, radius, stroke=1, fill=0)


def draw_horizontal_rule(pdf, x1, y, x2, color=LIGHT_BORDER, width=0.6):
    """Draw a consistent horizontal divider."""
    pdf.setStrokeColor(color)
    pdf.setLineWidth(width)
    pdf.line(x1, y, x2, y)


def generate_answer_sheet(assessment):
    """
    Generate a professional printable multiple-choice answer sheet.

    Includes:
    - Assessment header and identification details
    - Student name, year/section, and date
    - A/B/C/D column headers
    - Aligned answer bubbles and alternating row shading
    - Page numbering and scanning instructions
    """
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)

    questions = list(
        assessment.questions
        .filter(question_type="MULTIPLE_CHOICE")
        .prefetch_related("options")
        .order_by("order")
    )

    pdf.setTitle(f"Answer Sheet - {assessment.title}")
    pdf.setAuthor("PaperCheck")

    questions_per_page = QUESTIONS_PER_PAGE
    total_pages = max(1, math.ceil(len(questions) / questions_per_page))

    for page_index in range(total_pages):
        page_questions = questions[
            page_index * questions_per_page:
            (page_index + 1) * questions_per_page
        ]

        left = MARGIN
        right = PAGE_WIDTH - MARGIN

        # --------------------------------------------------
        # TOP HEADER
        # --------------------------------------------------
        top = PAGE_HEIGHT - 38

        pdf.setFillColor(INK)
        pdf.setFont("Helvetica-Bold", 17)
        pdf.drawString(left, top, "PAPERCHECK")

        pdf.setFillColor(MUTED)
        pdf.setFont("Helvetica-Bold", 7.5)
        pdf.drawRightString(
            right,
            top + 2,
            "MULTIPLE-CHOICE ANSWER SHEET",
        )

        draw_horizontal_rule(pdf, left, top - 11, right, INK, 1.2)

        # Assessment title
        pdf.setFillColor(INK)
        pdf.setFont("Helvetica-Bold", 13)
        pdf.drawString(
            left,
            PAGE_HEIGHT - 78,
            assessment.title[:65],
        )

        pdf.setFillColor(MUTED)
        pdf.setFont("Helvetica", 8)
        pdf.drawString(
            left,
            PAGE_HEIGHT - 94,
            f"ASSESSMENT ID: {assessment.pk}",
        )
        pdf.drawRightString(
            right,
            PAGE_HEIGHT - 94,
            f"PAGE {page_index + 1} OF {total_pages}",
        )

        # --------------------------------------------------
        # STUDENT INFORMATION PANEL
        # --------------------------------------------------
        panel_top = PAGE_HEIGHT - 111
        panel_bottom = PAGE_HEIGHT - 177

        pdf.setFillColor(ROW_SHADE)
        pdf.roundRect(
            left,
            panel_bottom,
            CONTENT_WIDTH,
            panel_top - panel_bottom,
            5,
            stroke=0,
            fill=1,
        )

        pdf.setFillColor(INK)
        pdf.setFont("Helvetica-Bold", 8)
        pdf.drawString(left + 12, panel_top - 16, "STUDENT INFORMATION")

        # Student name
        pdf.setFillColor(MUTED)
        pdf.setFont("Helvetica-Bold", 7)
        pdf.drawString(left + 12, panel_top - 32, "STUDENT NAME")

        pdf.setStrokeColor(INK)
        pdf.setLineWidth(0.65)
        pdf.line(
            left + 100,
            panel_top - 34,
            right - 12,
            panel_top - 34,
        )

        # Year / Section
        pdf.setFillColor(MUTED)
        pdf.setFont("Helvetica-Bold", 7)
        pdf.drawString(left + 12, panel_top - 52, "YEAR / SECTION")

        pdf.setStrokeColor(INK)
        pdf.line(
            left + 100,
            panel_top - 54,
            left + 245,
            panel_top - 54,
        )

        # Date
        pdf.setFillColor(MUTED)
        pdf.setFont("Helvetica-Bold", 7)
        pdf.drawString(left + 260, panel_top - 52, "DATE")

        pdf.setStrokeColor(INK)
        pdf.line(
            left + 292,
            panel_top - 54,
            right - 12,
            panel_top - 54,
        )

        # Instructions
        instructions_y = PAGE_HEIGHT - 195

        pdf.setFillColor(INK)
        pdf.setFont("Helvetica-Bold", 8)
        pdf.drawString(left, instructions_y, "INSTRUCTIONS")

        pdf.setFillColor(MUTED)
        pdf.setFont("Helvetica", 7.5)
        pdf.drawString(
            left,
            instructions_y - 13,
            "Shade ONE circle completely for each question using a dark pencil.",
        )
        pdf.drawString(
            left,
            instructions_y - 25,
            "Keep this sheet flat and clean. Avoid stray marks and select only one answer.",
        )

        # --------------------------------------------------
        # ANSWER GRID
        # --------------------------------------------------
        grid_top = GRID_TOP
        start_y = START_Y

        row_height = ROW_HEIGHT
        question_x = QUESTION_X
        bubble_start_x = BUBBLE_START_X
        bubble_spacing = BUBBLE_SPACING

        # Get available answer labels from the first question.
        header_options = (
            list(page_questions[0].options.all().order_by("label"))
            if page_questions
            else []
        )

        # Grid section heading
        pdf.setFillColor(INK)
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(left, grid_top, "ANSWER GRID")

        pdf.setFillColor(MUTED)
        pdf.setFont("Helvetica", 7)
        pdf.drawRightString(
            right,
            grid_top,
            f"{len(page_questions)} QUESTIONS ON THIS PAGE",
        )

        # Column header background
        header_y = start_y + 8

        pdf.setFillColor(HEADER_SHADE)
        pdf.roundRect(
            left,
            header_y - 5,
            CONTENT_WIDTH,
            24,
            3,
            stroke=0,
            fill=1,
        )

        pdf.setFillColor(INK)
        pdf.setFont("Helvetica-Bold", 7.5)
        pdf.drawString(question_x, header_y + 3, "QUESTION")

        for option_index, option in enumerate(header_options):
            x = bubble_start_x + option_index * bubble_spacing

            if x + 12 > right:
                break

            pdf.drawCentredString(x, header_y + 3, option.label)

        # Question rows
        for row_index, question in enumerate(page_questions):
            y = start_y - 18 - row_index * row_height

            if y < 47:
                break

            # Alternating row shading
            if row_index % 2 == 0:
                pdf.setFillColor(ROW_SHADE)
                pdf.rect(
                    left,
                    y - 8,
                    CONTENT_WIDTH,
                    row_height,
                    stroke=0,
                    fill=1,
                )

            # Question number
            pdf.setFillColor(INK)
            pdf.setFont("Helvetica-Bold", 8.5)
            pdf.drawString(question_x, y - 1, str(question.order))

            # Answer bubbles aligned beneath A/B/C/D
            options = list(question.options.all().order_by("label"))

            for option_index, option in enumerate(options):
                x = bubble_start_x + option_index * bubble_spacing

                if x + 12 > right:
                    break

                draw_bubble(pdf, x, y + 1, radius=6)

            # Subtle row divider
            draw_horizontal_rule(
                pdf,
                left,
                y - 8,
                right,
                LIGHT_BORDER,
                0.35,
            )

        # --------------------------------------------------
        # FOOTER
        # --------------------------------------------------
        footer_y = 35

        draw_horizontal_rule(
            pdf,
            left,
            footer_y + 12,
            right,
            LIGHT_BORDER,
            0.7,
        )

        pdf.setFillColor(MUTED)
        pdf.setFont("Helvetica-Bold", 7)
        pdf.drawString(left, footer_y, "PAPERCHECK")

        pdf.setFont("Helvetica", 7)
        pdf.drawCentredString(
            PAGE_WIDTH / 2,
            footer_y,
            "For machine scanning: avoid folds and stray marks.",
        )

        pdf.drawRightString(
            right,
            footer_y,
            f"ID: {assessment.pk}",
        )

        pdf.showPage()

    pdf.save()
    buffer.seek(0)
    return buffer
