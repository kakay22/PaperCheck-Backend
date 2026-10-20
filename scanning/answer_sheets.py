from io import BytesIO
import math

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from .layout import (
    BUBBLE_OFFSET_X,
    BUBBLE_RADIUS,
    BUBBLE_SPACING,
    COLUMN_LEFTS,
    COLUMN_WIDTH,
    GRID_TOP,
    ID_BUBBLE_RADIUS,
    ID_LABEL_X,
    ID_PANEL_BOTTOM,
    ID_PANEL_LEFT,
    ID_PANEL_RIGHT,
    ID_PANEL_TOP,
    MARGIN,
    NUMBER_RIGHT_OFFSET,
    PAGE_HEIGHT,
    PAGE_WIDTH,
    QUESTIONS_PER_COLUMN,
    QUESTIONS_PER_PAGE,
    ROW_HEIGHT,
    START_Y,
    STUDENT_ID_DIGITS,
    bubble_center,
    marker_rects,
    row_baseline_y,
    student_id_box_rect,
    student_id_bubble_center,
)

CONTENT_WIDTH = PAGE_WIDTH - (2 * MARGIN)
MAX_CHOICES = 4  # A-D; the layout has room for four columns per question

# Professional monochrome print palette
INK = colors.HexColor("#172033")
MUTED = colors.HexColor("#64748B")
LIGHT_BORDER = colors.HexColor("#D7DEE8")
ROW_SHADE = colors.HexColor("#F5F7FA")
HEADER_SHADE = colors.HexColor("#E9EEF5")
WHITE = colors.white


def draw_bubble(pdf, x, y, radius=BUBBLE_RADIUS):
    """Draw a clean, empty bubble for OMR scanning."""
    pdf.setStrokeColor(INK)
    pdf.setLineWidth(0.9)
    pdf.circle(x, y, radius, stroke=1, fill=0)


def draw_horizontal_rule(pdf, x1, y, x2, color=LIGHT_BORDER, width=0.6):
    """Draw a consistent horizontal divider."""
    pdf.setStrokeColor(color)
    pdf.setLineWidth(width)
    pdf.line(x1, y, x2, y)


def draw_corner_markers(pdf):
    """Draw solid black alignment squares at the four page corners."""
    pdf.setFillColor(colors.black)
    for x, y, w, h in marker_rects():
        pdf.rect(x, y, w, h, stroke=0, fill=1)


def draw_student_id_grid(pdf):
    """Student ID: write-in box on top, digit bubbles 0-9 underneath."""
    pdf.setStrokeColor(LIGHT_BORDER)
    pdf.setLineWidth(0.8)
    pdf.roundRect(
        ID_PANEL_LEFT,
        ID_PANEL_BOTTOM,
        ID_PANEL_RIGHT - ID_PANEL_LEFT,
        ID_PANEL_TOP - ID_PANEL_BOTTOM,
        4,
        stroke=1,
        fill=0,
    )

    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 7.5)
    pdf.drawCentredString(
        (ID_PANEL_LEFT + ID_PANEL_RIGHT) / 2,
        ID_PANEL_TOP - 14,
        "STUDENT ID",
    )

    # Write-in boxes
    pdf.setStrokeColor(INK)
    pdf.setLineWidth(0.8)
    for position in range(STUDENT_ID_DIGITS):
        x, y, w, h = student_id_box_rect(position)
        pdf.rect(x, y, w, h, stroke=1, fill=0)

    # Row labels 0-9
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica-Bold", 7.5)
    for digit in range(10):
        _, y = student_id_bubble_center(0, digit)
        pdf.drawCentredString(ID_LABEL_X, y - 2.5, str(digit))

    # Digit bubbles
    for position in range(STUDENT_ID_DIGITS):
        for digit in range(10):
            x, y = student_id_bubble_center(position, digit)
            draw_bubble(pdf, x, y, radius=ID_BUBBLE_RADIUS)


def generate_answer_sheet(assessment):
    """
    Generate a printable multiple-choice answer sheet.

    Each page holds up to 50 questions in two columns of 25, plus a
    student ID bubble grid and four corner alignment markers.

    Geometry comes from scanning/layout.py, which the OMR detector also
    imports. Do not hard-code grid positions here.
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

    total_pages = max(1, math.ceil(len(questions) / QUESTIONS_PER_PAGE))

    for page_index in range(total_pages):
        page_questions = questions[
            page_index * QUESTIONS_PER_PAGE:
            (page_index + 1) * QUESTIONS_PER_PAGE
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
        pdf.drawRightString(right, top + 2, "MULTIPLE-CHOICE ANSWER SHEET")

        draw_horizontal_rule(pdf, left, top - 11, right, INK, 1.2)

        pdf.setFillColor(INK)
        pdf.setFont("Helvetica-Bold", 13)
        pdf.drawString(left, PAGE_HEIGHT - 78, assessment.title[:65])

        pdf.setFillColor(MUTED)
        pdf.setFont("Helvetica", 8)
        pdf.drawString(left, PAGE_HEIGHT - 94, f"ASSESSMENT ID: {assessment.pk}")
        pdf.drawRightString(
            right,
            PAGE_HEIGHT - 94,
            f"PAGE {page_index + 1} OF {total_pages}",
        )

        # --------------------------------------------------
        # STUDENT INFORMATION (left of the ID grid)
        # --------------------------------------------------
        info_width = ID_PANEL_LEFT - 12 - left
        info_top = PAGE_HEIGHT - 108
        info_bottom = PAGE_HEIGHT - 212

        pdf.setFillColor(ROW_SHADE)
        pdf.roundRect(
            left,
            info_bottom,
            info_width,
            info_top - info_bottom,
            5,
            stroke=0,
            fill=1,
        )

        pdf.setFillColor(INK)
        pdf.setFont("Helvetica-Bold", 8)
        pdf.drawString(left + 12, info_top - 16, "STUDENT INFORMATION")

        fields = [("NAME", 40), ("YEAR / SECTION", 64), ("DATE", 88)]
        pdf.setLineWidth(0.65)
        for label, offset in fields:
            pdf.setFillColor(MUTED)
            pdf.setFont("Helvetica-Bold", 7)
            pdf.drawString(left + 12, info_top - offset, label)

            pdf.setStrokeColor(INK)
            pdf.line(
                left + 88,
                info_top - offset - 2,
                left + info_width - 12,
                info_top - offset - 2,
            )

        # Instructions
        instructions_y = PAGE_HEIGHT - 230

        pdf.setFillColor(INK)
        pdf.setFont("Helvetica-Bold", 8)
        pdf.drawString(left, instructions_y, "INSTRUCTIONS")

        pdf.setFillColor(MUTED)
        pdf.setFont("Helvetica", 7.5)
        instruction_lines = [
            "Use a dark pencil. Shade ONE circle per question.",
            "Fill the circle completely; erase changes cleanly.",
            "Student ID: write one digit in each box, then shade",
            "the matching circle below it. Keep the sheet flat.",
        ]
        for line_index, line in enumerate(instruction_lines):
            pdf.drawString(left, instructions_y - 13 - line_index * 11, line)

        # --------------------------------------------------
        # STUDENT ID GRID
        # --------------------------------------------------
        draw_student_id_grid(pdf)

        # --------------------------------------------------
        # ANSWER GRID
        # --------------------------------------------------
        columns_used = 2 if len(page_questions) > QUESTIONS_PER_COLUMN else 1

        pdf.setFillColor(INK)
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(left, GRID_TOP, "ANSWER GRID")

        pdf.setFillColor(MUTED)
        pdf.setFont("Helvetica", 7)
        pdf.drawRightString(
            right,
            GRID_TOP,
            f"{len(page_questions)} QUESTIONS ON THIS PAGE",
        )

        header_y = START_Y + 8

        pdf.setFillColor(HEADER_SHADE)
        pdf.roundRect(left, header_y - 5, CONTENT_WIDTH, 24, 3, stroke=0, fill=1)

        header_options = (
            list(page_questions[0].options.all().order_by("label"))[:MAX_CHOICES]
            if page_questions
            else []
        )

        pdf.setFillColor(INK)
        pdf.setFont("Helvetica-Bold", 7.5)
        for column in range(columns_used):
            col_left = COLUMN_LEFTS[column]
            pdf.drawRightString(
                col_left + NUMBER_RIGHT_OFFSET, header_y + 3, "NO."
            )
            for option_index, option in enumerate(header_options):
                x = col_left + BUBBLE_OFFSET_X + option_index * BUBBLE_SPACING
                pdf.drawCentredString(x, header_y + 3, option.label)

        # Thin separator between the two columns
        if columns_used == 2:
            gap_x = (COLUMN_LEFTS[0] + COLUMN_WIDTH + COLUMN_LEFTS[1]) / 2
            bottom_y = row_baseline_y(QUESTIONS_PER_COLUMN - 1) - 8
            pdf.setStrokeColor(LIGHT_BORDER)
            pdf.setLineWidth(0.6)
            pdf.line(gap_x, header_y - 5, gap_x, bottom_y)

        # Question rows
        for slot, question in enumerate(page_questions):
            column, row = divmod(slot, QUESTIONS_PER_COLUMN)
            col_left = COLUMN_LEFTS[column]
            y = row_baseline_y(row)

            if row % 2 == 0:
                pdf.setFillColor(ROW_SHADE)
                pdf.rect(
                    col_left,
                    y - 8,
                    COLUMN_WIDTH,
                    ROW_HEIGHT,
                    stroke=0,
                    fill=1,
                )

            pdf.setFillColor(INK)
            pdf.setFont("Helvetica-Bold", 8.5)
            pdf.drawRightString(
                col_left + NUMBER_RIGHT_OFFSET, y - 1, f"{question.order}."
            )

            options = list(question.options.all().order_by("label"))[:MAX_CHOICES]
            for option_index, _option in enumerate(options):
                bx, by = bubble_center(slot, option_index)
                draw_bubble(pdf, bx, by, radius=BUBBLE_RADIUS)

            draw_horizontal_rule(
                pdf,
                col_left,
                y - 8,
                col_left + COLUMN_WIDTH,
                LIGHT_BORDER,
                0.35,
            )

        # --------------------------------------------------
        # FOOTER
        # --------------------------------------------------
        footer_y = 35

        draw_horizontal_rule(pdf, left, footer_y + 12, right, LIGHT_BORDER, 0.7)

        pdf.setFillColor(MUTED)
        pdf.setFont("Helvetica-Bold", 7)
        pdf.drawString(left, footer_y, "PAPERCHECK")

        pdf.setFont("Helvetica", 7)
        pdf.drawCentredString(
            PAGE_WIDTH / 2,
            footer_y,
            "For machine scanning: avoid folds and stray marks.",
        )

        pdf.drawRightString(right, footer_y, f"ID: {assessment.pk}")

        draw_corner_markers(pdf)

        pdf.showPage()

    pdf.save()
    buffer.seek(0)
    return buffer