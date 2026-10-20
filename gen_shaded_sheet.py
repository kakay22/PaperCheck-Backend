
"""
Generate shaded PaperCheck OMR test images.

Run from the Django backend root:
    python gen_shaded_sheet.py

Outputs:
    shaded_sheet_clean.png
    shaded_sheet.jpg

The script uses the real answer-sheet PDF and shared OMR coordinates.
"""

import os
from pathlib import Path

import cv2
import django
import numpy as np
import pymupdf

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from assessments.models import Assessment
from schools.models import Enrollment, Student
from scanning.answer_sheets import generate_answer_sheet
from scanning.layout import (
    BUBBLE_RADIUS,
    ID_BUBBLE_RADIUS,
    MARGIN,
    PAGE_HEIGHT,
    PAGE_WIDTH,
    STUDENT_ID_DIGITS,
    bubble_center,
    student_id_box_rect,
    student_id_bubble_center,
)

# =========================================================
# CONFIGURATION
# =========================================================

TITLE = "OMR Calibration Test (25 Q)"

STUDENT_ID = "2025-001"
FIRST = "Kyle"
MIDDLE = "Brieva"
LAST = "Calites"

DATE_TEXT = "10/20/2026"

OUTPUT_DIR = Path.cwd()
CLEAN_OUTPUT = OUTPUT_DIR / "shaded_sheet_clean.png"
PHOTO_OUTPUT = OUTPUT_DIR / "shaded_sheet.jpg"

# BGR colors used by OpenCV.
PENCIL = (60, 60, 60)
PEN = (120, 50, 20)

# Test behavior:
# 1-15: correct answers
# 16-18: one incorrect answer
# 19-20: another incorrect answer
# 21: incorrect answer
# 22: blank
# 23: double-marked
# 24: correct answer
# 25: incorrect answer

# =========================================================
# FIND ASSESSMENT AND STUDENT
# =========================================================

assessment = (
    Assessment.objects
    .filter(title=TITLE)
    .order_by("-id")
    .first()
)

if assessment is None:
    existing_titles = list(
        Assessment.objects.values_list("title", flat=True)
    )
    raise SystemExit(
        f"Assessment '{TITLE}' was not found.\n"
        f"Existing assessments: {existing_titles}"
    )

if assessment.status != "PUBLISHED":
    raise SystemExit(
        f"Assessment '{assessment.title}' is currently "
        f"'{assessment.status}'. Publish it through the admin "
        "interface before generating a scan test sheet."
    )

classroom = assessment.classroom

student, created = Student.objects.get_or_create(
    school=classroom.school,
    student_id=STUDENT_ID,
    defaults={
        "first_name": FIRST,
        "middle_name": MIDDLE,
        "last_name": LAST,
    },
)

# Keep existing student details intact.
Enrollment.objects.get_or_create(
    classroom=classroom,
    student=student,
)

full_name = f"{FIRST} {MIDDLE} {LAST}"

# The ID bubble grid stores digits only, without hyphens.
# Example: 2025-001 -> 002025001 for a 9-digit grid.
grid_id = "".join(char for char in STUDENT_ID if char.isdigit())
grid_id = grid_id.zfill(STUDENT_ID_DIGITS)

if len(grid_id) != STUDENT_ID_DIGITS:
    raise SystemExit(
        f"Student ID {STUDENT_ID!r} cannot fit the "
        f"{STUDENT_ID_DIGITS}-digit OMR grid."
    )

# =========================================================
# LOAD MULTIPLE-CHOICE QUESTIONS
# =========================================================

questions = list(
    assessment.questions
    .filter(question_type="MULTIPLE_CHOICE")
    .prefetch_related("options")
    .order_by("order")
)

if not questions:
    raise SystemExit("This assessment has no multiple-choice questions.")

# This script creates a single-image test sheet.
# Multi-page assessments need a separate image for each page.
if len(questions) > 50:
    raise SystemExit(
        f"This assessment has {len(questions)} multiple-choice "
        "questions. It requires multiple pages. This script's "
        "single-image output is intended for assessments with "
        "50 or fewer multiple-choice questions."
    )

if len(questions) != 25:
    print(
        f"WARNING: The assessment contains {len(questions)} "
        "multiple-choice questions, not 25."
    )

# =========================================================
# RENDER THE REAL GENERATED ANSWER SHEET
# =========================================================

pdf_bytes = generate_answer_sheet(assessment).read()

with pymupdf.open(stream=pdf_bytes, filetype="pdf") as document:
    if len(document) != 1:
        raise SystemExit(
            f"The generated answer sheet contains {len(document)} pages. "
            "This script currently produces a single-page test image."
        )

    pixmap = document[0].get_pixmap(dpi=200, alpha=False)

    # PyMuPDF returns RGB; OpenCV uses BGR.
    image = np.frombuffer(
        pixmap.samples,
        dtype=np.uint8,
    ).reshape(pixmap.height, pixmap.width, pixmap.n)

    if pixmap.n == 3:
        image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
    elif pixmap.n == 4:
        image = cv2.cvtColor(image, cv2.COLOR_RGBA2BGR)

    image = image.copy()

sx = image.shape[1] / PAGE_WIDTH
sy = image.shape[0] / PAGE_HEIGHT


def px(x, y):
    """Convert PDF coordinates (origin bottom-left) to image pixels."""
    return (
        int(round(x * sx)),
        int(round((PAGE_HEIGHT - y) * sy)),
    )


def fill(center_pdf, radius_pdf, color=PENCIL):
    """Fill a bubble using the shared OMR layout coordinates."""
    center = px(*center_pdf)
    radius = max(1, int(round(radius_pdf * min(sx, sy))))

    cv2.circle(
        image,
        center,
        radius,
        color,
        thickness=-1,
        lineType=cv2.LINE_AA,
    )


# =========================================================
# WRITE STUDENT NAME AND DATE
# =========================================================

info_top = PAGE_HEIGHT - 108

cv2.putText(
    image,
    full_name,
    px(MARGIN + 92, info_top - 40 + 1),
    cv2.FONT_HERSHEY_SIMPLEX,
    0.6,
    PEN,
    1,
    cv2.LINE_AA,
)

cv2.putText(
    image,
    DATE_TEXT,
    px(MARGIN + 92, info_top - 88 + 1),
    cv2.FONT_HERSHEY_SIMPLEX,
    0.55,
    PEN,
    1,
    cv2.LINE_AA,
)

# =========================================================
# SHADE THE STUDENT ID BUBBLES
# =========================================================

for position, digit_char in enumerate(grid_id):
    digit = int(digit_char)

    bx, by, bw, bh = student_id_box_rect(position)

    (text_width, text_height), _ = cv2.getTextSize(
        digit_char,
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        1,
    )

    center_x, center_y = px(
        bx + bw / 2,
        by + bh / 2,
    )

    cv2.putText(
        image,
        digit_char,
        (
            center_x - text_width // 2,
            center_y + text_height // 2,
        ),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        PEN,
        1,
        cv2.LINE_AA,
    )

    fill(
        student_id_bubble_center(position, digit),
        ID_BUBBLE_RADIUS,
    )

# =========================================================
# SHADE ANSWERS USING THE SHARED LAYOUT
# =========================================================

expected_correct = 0
answer_summary = []

for slot, question in enumerate(questions):
    options = sorted(
        question.options.all(),
        key=lambda option: option.label,
    )

    labels = [option.label for option in options]

    if not labels:
        raise SystemExit(
            f"Question {question.order} has no answer options."
        )

    correct_options = [
        option.label for option in options if option.is_correct
    ]

    if len(correct_options) != 1:
        raise SystemExit(
            f"Question {question.order} must have exactly one "
            f"correct option; found {correct_options}."
        )

    correct = correct_options[0]
    wrong = [label for label in labels if label != correct]
    question_number = question.order

    # Default: shade the correct answer.
    if 16 <= question_number <= 18:
        picks = [wrong[0]]

    elif 19 <= question_number <= 20:
        picks = [wrong[min(1, len(wrong) - 1)]]

    elif question_number == 21:
        picks = [wrong[-1]]

    elif question_number == 22:
        picks = []

    elif question_number == 23:
        picks = [correct, wrong[0]]

    elif question_number == 25:
        picks = [wrong[min(1, len(wrong) - 1)]]

    else:
        picks = [correct]

    # Use the page-local slot, matching detect_answers().
    for label in picks:
        option_index = labels.index(label)

        fill(
            bubble_center(slot, option_index),
            BUBBLE_RADIUS,
        )

    if picks == [correct]:
        expected_correct += 1

    answer_summary.append(
        f"Q{question_number}: "
        f"{', '.join(picks) if picks else 'BLANK'}"
    )

# =========================================================
# SAVE CLEAN DIGITAL SHEET
# =========================================================

if not cv2.imwrite(str(CLEAN_OUTPUT), image):
    raise SystemExit(f"Could not save {CLEAN_OUTPUT}")

# =========================================================
# CREATE PHOTO-LIKE VERSION
# =========================================================

height, width = image.shape[:2]

source_points = np.float32([
    [0, 0],
    [width - 1, 0],
    [0, height - 1],
    [width - 1, height - 1],
])

destination_points = np.float32([
    [60, 45],
    [width + 25, 60],
    [40, height + 30],
    [width + 45, height + 10],
])

matrix = cv2.getPerspectiveTransform(
    source_points,
    destination_points,
)

photo = cv2.warpPerspective(
    image,
    matrix,
    (width + 120, height + 110),
    borderValue=(110, 110, 110),
)

# Slight blur to simulate a camera photo.
photo = cv2.GaussianBlur(photo, (3, 3), 0)

# Gentle horizontal lighting variation.
gradient = np.linspace(
    0.88,
    1.0,
    photo.shape[1],
    dtype=np.float32,
)[None, :, None]

photo = np.clip(
    photo.astype(np.float32) * gradient,
    0,
    255,
).astype(np.uint8)

if not cv2.imwrite(
    str(PHOTO_OUTPUT),
    photo,
    [cv2.IMWRITE_JPEG_QUALITY, 92],
):
    raise SystemExit(f"Could not save {PHOTO_OUTPUT}")

# =========================================================
# REPORT
# =========================================================

print()
print("=" * 55)
print("PAPERCHECK SHADED SHEET GENERATED")
print("=" * 55)
print(f"Assessment: {assessment.pk} — {assessment.title}")
print(f"Classroom: {classroom}")
print(f"Student: {STUDENT_ID} — {full_name}")
print(f"ID digits shaded in grid: {grid_id}")
print(f"Multiple-choice questions: {len(questions)}")
print(f"Expected correct answers: {expected_correct}")
print()
print(f"Clean image: {CLEAN_OUTPUT}")
print(f"Photo-like image: {PHOTO_OUTPUT}")
print()
print("Test answers:")
for line in answer_summary:
    print(f"  {line}")
print("=" * 55)
