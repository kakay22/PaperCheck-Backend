
import os
import sys

import cv2
import django
import numpy as np
import pymupdf

from reportlab.lib import colors
from reportlab.pdfgen import canvas

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from assessments.models import Assessment
from schools.models import Enrollment, Student
from scanning.answer_sheets import draw_corner_markers, draw_student_id_grid
from scanning.layout import (
    MARGIN,
    PAGE_HEIGHT,
    PAGE_WIDTH,
    STUDENT_ID_DIGITS,
    marker_rects,
    student_id_box_rect,
    student_id_bubble_center,
)

STUDENT_ID = "2025-001"
FIRST, MIDDLE, LAST = "Kyle", "Brieva", "Calites"
DATE_TEXT = "10/21/2026"

PEN = (120, 50, 20)
PENCIL = (60, 60, 60)

OUTPUT_PDF = "enumeration_sheet.pdf"
OUTPUT_CLEAN = "shaded_enumeration_clean.png"
OUTPUT_PHOTO = "shaded_enumeration.jpg"

title = sys.argv[1] if len(sys.argv) > 1 else None

assessments = (
    Assessment.objects
    .filter(questions__question_type="ENUMERATION")
    .distinct()
)

if title:
    assessments = assessments.filter(title=title)

assessment = assessments.order_by("-id").first()

if assessment is None:
    raise SystemExit(
        "No assessment with enumeration questions found. "
        "Create an enumeration question first, or pass the assessment title."
    )

questions = list(
    assessment.questions
    .filter(question_type="ENUMERATION")
    .prefetch_related("key_items")
    .order_by("order")
)

if not questions:
    raise SystemExit("The selected assessment has no enumeration questions.")

classroom = assessment.classroom

student, _ = Student.objects.get_or_create(
    school=classroom.school,
    student_id=STUDENT_ID,
    defaults={
        "first_name": FIRST,
        "middle_name": MIDDLE,
        "last_name": LAST,
    },
)

Enrollment.objects.get_or_create(
    classroom=classroom,
    student=student,
)

grid_id = "".join(c for c in STUDENT_ID if c.isdigit()).zfill(
    STUDENT_ID_DIGITS
)

if len(grid_id) != STUDENT_ID_DIGITS:
    raise SystemExit(
        f"Student ID must fit {STUDENT_ID_DIGITS} digits in the ID grid."
    )

# Each overlay contains:
# (page number, PDF x coordinate, PDF y baseline, text)
overlays = []


def draw_header(pdf, page_number):
    left = MARGIN
    right = PAGE_WIDTH - MARGIN
    top = PAGE_HEIGHT - 38

    pdf.setFillColor(colors.HexColor("#172033"))
    pdf.setFont("Helvetica-Bold", 17)
    pdf.drawString(left, top, "PAPERCHECK")

    pdf.setFillColor(colors.HexColor("#64748B"))
    pdf.setFont("Helvetica-Bold", 7.5)
    pdf.drawRightString(right, top + 2, "ENUMERATION ANSWER SHEET")

    pdf.setStrokeColor(colors.HexColor("#172033"))
    pdf.setLineWidth(1.2)
    pdf.line(left, top - 11, right, top - 11)

    pdf.setFillColor(colors.HexColor("#172033"))
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(left, PAGE_HEIGHT - 78, assessment.title[:65])

    pdf.setFillColor(colors.HexColor("#64748B"))
    pdf.setFont("Helvetica", 8)
    pdf.drawString(
        left,
        PAGE_HEIGHT - 94,
        f"ASSESSMENT ID: {assessment.pk}",
    )
    pdf.drawRightString(
        right,
        PAGE_HEIGHT - 94,
        f"PAGE {page_number}",
    )

    # Student information area, matching the existing sheet's top layout.
    info_top = PAGE_HEIGHT - 108
    info_bottom = PAGE_HEIGHT - 212
    info_width = 246

    pdf.setFillColor(colors.HexColor("#F5F7FA"))
    pdf.roundRect(
        left,
        info_bottom,
        info_width,
        info_top - info_bottom,
        5,
        stroke=0,
        fill=1,
    )

    pdf.setFillColor(colors.HexColor("#172033"))
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawString(left + 12, info_top - 16, "STUDENT INFORMATION")

    fields = [
        ("NAME", 40, f"{FIRST} {MIDDLE} {LAST}"),
        ("YEAR / SECTION", 64, ""),
        ("DATE", 88, DATE_TEXT),
    ]

    for label, offset, value in fields:
        y = info_top - offset

        pdf.setFillColor(colors.HexColor("#64748B"))
        pdf.setFont("Helvetica-Bold", 7)
        pdf.drawString(left + 12, y, label)

        pdf.setStrokeColor(colors.HexColor("#172033"))
        pdf.setLineWidth(0.65)
        pdf.line(left + 88, y - 2, left + info_width - 12, y - 2)

        if value:
            overlays.append(
                (page_number - 1, left + 92, y - 1, value)
            )

    pdf.setFillColor(colors.HexColor("#172033"))
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawString(left, PAGE_HEIGHT - 230, "INSTRUCTIONS")

    pdf.setFillColor(colors.HexColor("#64748B"))
    pdf.setFont("Helvetica", 7.5)
    pdf.drawString(
        left,
        PAGE_HEIGHT - 243,
        "Write each answer on its numbered line.",
    )
    pdf.drawString(
        left,
        PAGE_HEIGHT - 254,
        "Use clear writing and keep answers inside the answer area.",
    )

    # Reuse the existing PaperCheck student ID bubble grid.
    draw_student_id_grid(pdf)

    # Write the ID digits and shade their matching bubbles on the image.
    for position, digit_char in enumerate(grid_id):
        bx, by, bw, bh = student_id_box_rect(position)
        overlays.append(
            (
                page_number - 1,
                bx + bw / 2,
                by + bh / 2,
                digit_char,
            )
        )


def question_answers(question):
    items = list(question.key_items.all().order_by("position"))
    answers = []

    for item in items:
        variants = item.variants or []
        answer = next(
            (str(value).strip() for value in variants if str(value).strip()),
            "",
        )
        answers.append(answer)

    count = int(getattr(question, "enum_item_count", 0) or len(items) or 1)

    while len(answers) < count:
        answers.append("Sample answer")

    return answers[:count]


buffer_path = OUTPUT_PDF
pdf = canvas.Canvas(buffer_path, pagesize=(PAGE_WIDTH, PAGE_HEIGHT))
pdf.setTitle(f"Enumeration Answer Sheet - {assessment.title}")
pdf.setAuthor("PaperCheck")

page_number = 1
draw_header(pdf, page_number)

# Keep questions in order and allow the sheet to continue to additional pages.
y = PAGE_HEIGHT - 365
bottom_limit = 55

for question in questions:
    answers = question_answers(question)
    block_height = 26 + len(answers) * 23 + 13

    if y - block_height < bottom_limit:
        pdf.setFillColor(colors.HexColor("#64748B"))
        pdf.setFont("Helvetica", 7)
        pdf.drawString(MARGIN, 35, "PAPERCHECK - ENUMERATION PRACTICE")
        draw_corner_markers(pdf)
        pdf.showPage()

        page_number += 1
        draw_header(pdf, page_number)
        y = PAGE_HEIGHT - 365

    pdf.setFillColor(colors.HexColor("#172033"))
    pdf.setFont("Helvetica-Bold", 9)
    prompt = f"{question.order}. {question.prompt}"
    pdf.drawString(MARGIN + 4, y, prompt[:105])

    answer_y = y - 25

    for item_number, answer in enumerate(answers, start=1):
        x = MARGIN + 18

        pdf.setFillColor(colors.HexColor("#64748B"))
        pdf.setFont("Helvetica", 8)
        pdf.drawString(x, answer_y, f"{item_number}.")

        line_start = x + 24
        line_end = PAGE_WIDTH - MARGIN - 12

        pdf.setStrokeColor(colors.HexColor("#AAB4C2"))
        pdf.setLineWidth(0.55)
        pdf.line(line_start, answer_y - 3, line_end, answer_y - 3)

        overlays.append(
            (
                page_number - 1,
                line_start + 4,
                answer_y,
                answer or "Sample answer",
            )
        )

        answer_y -= 23

    y -= block_height

pdf.setFillColor(colors.HexColor("#64748B"))
pdf.setFont("Helvetica", 7)
pdf.drawString(MARGIN, 35, "PAPERCHECK - ENUMERATION PRACTICE")
draw_corner_markers(pdf)
pdf.save()

# Render the PDF pages and add simulated pen writing and shaded student ID.
doc = pymupdf.open(OUTPUT_PDF)
rendered_pages = []

for page_index, page in enumerate(doc):
    pix = page.get_pixmap(dpi=150, alpha=False)
    img = np.frombuffer(
        pix.samples, dtype=np.uint8
    ).reshape(pix.height, pix.width, pix.n)

    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

    sx = pix.width / PAGE_WIDTH
    sy = pix.height / PAGE_HEIGHT

    def px(x, y):
        return (
            int(round(x * sx)),
            int(round((PAGE_HEIGHT - y) * sy)),
        )

    # Handwritten-style name, date, ID, and enumeration answers.
    for overlay_page, x, y, text in overlays:
        if overlay_page != page_index:
            continue

        point = px(x, y)

        if len(text) == 1 and text.isdigit():
            # Student ID digit in its write-in box.
            cv2.putText(
                img,
                text,
                point,
                cv2.FONT_HERSHEY_SIMPLEX,
                0.40,
                PEN,
                1,
                cv2.LINE_AA,
            )
        else:
            cv2.putText(
                img,
                text[:90],
                point,
                cv2.FONT_HERSHEY_SIMPLEX,
                0.43,
                PEN,
                1,
                cv2.LINE_AA,
            )

    # Shade the corresponding student ID bubbles.
    for position, digit_char in enumerate(grid_id):
        center = student_id_bubble_center(position, int(digit_char))
        cv2.circle(
            img,
            px(*center),
            int(round(5 * min(sx, sy))),
            PENCIL,
            -1,
        )

    rendered_pages.append(img)

if not rendered_pages:
    raise SystemExit("Failed to render the enumeration sheet.")

clean = rendered_pages[0]
cv2.imwrite(OUTPUT_CLEAN, clean)

# Make a photo-like version of the first page.
h, w = clean.shape[:2]
src = np.float32([
    [0, 0],
    [w - 1, 0],
    [0, h - 1],
    [w - 1, h - 1],
])
dst = np.float32([
    [60, 45],
    [w + 25, 60],
    [40, h + 30],
    [w + 45, h + 10],
])

photo = cv2.warpPerspective(
    clean,
    cv2.getPerspectiveTransform(src, dst),
    (w + 120, h + 110),
    borderValue=(110, 110, 110),
)
photo = cv2.GaussianBlur(photo, (3, 3), 0)
photo = (
    photo * np.linspace(0.85, 1.0, photo.shape[1])[None, :, None]
).clip(0, 255).astype(np.uint8)

cv2.imwrite(
    OUTPUT_PHOTO,
    photo,
    [cv2.IMWRITE_JPEG_QUALITY, 92],
)

print(f"Assessment {assessment.pk}: {assessment.title}")
print(f"Enumeration questions: {len(questions)}")
print(f"Student: {STUDENT_ID} - {FIRST} {MIDDLE} {LAST}")
print(f"Saved PDF: {os.path.abspath(OUTPUT_PDF)}")
print(f"Saved clean image: {os.path.abspath(OUTPUT_CLEAN)}")
print(f"Saved photo-like image: {os.path.abspath(OUTPUT_PHOTO)}")
print(
    "Note: answers are simulated pen-style text. "
    "The current OMR scanner does not grade written enumeration answers."
)
