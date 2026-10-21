import os
import sys

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

STUDENT_ID = "2025-001"
FIRST, MIDDLE, LAST = "Kyle", "Brieva", "Calites"
DATE_TEXT = "10/21/2026"

PENCIL = (60, 60, 60)
PEN = (120, 50, 20)

# Optional: python gen_shaded_sheet.py "OMR Calibration Test (50 Q)"
title = sys.argv[1] if len(sys.argv) > 1 else None
qs = Assessment.objects.filter(questions__question_type="MULTIPLE_CHOICE").distinct()
assessment = (qs.filter(title=title) if title else qs).order_by("-id").first()
if assessment is None:
    raise SystemExit("No matching assessment with multiple-choice questions.")

if assessment.status == "DRAFT":
    Assessment.objects.filter(pk=assessment.pk).update(status="PUBLISHED")
    print("Assessment was a draft; published it.")

classroom = assessment.classroom
student, _ = Student.objects.get_or_create(
    school=classroom.school,
    student_id=STUDENT_ID,
    defaults={"first_name": FIRST, "middle_name": MIDDLE, "last_name": LAST},
)
Enrollment.objects.get_or_create(classroom=classroom, student=student)

grid_id = "".join(c for c in STUDENT_ID if c.isdigit()).zfill(STUDENT_ID_DIGITS)

doc = pymupdf.open(stream=generate_answer_sheet(assessment).read(), filetype="pdf")
pix = doc[0].get_pixmap(dpi=150)
img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
sx, sy = pix.width / PAGE_WIDTH, pix.height / PAGE_HEIGHT


def px(x, y):
    return int(round(x * sx)), int(round((PAGE_HEIGHT - y) * sy))


def fill(center, radius):
    cv2.circle(img, px(*center), int(round(radius * min(sx, sy))), PENCIL, -1)


# Handwritten name and date.
info_top = PAGE_HEIGHT - 108
full_name = f"{FIRST} {MIDDLE} {LAST}"
cv2.putText(img, full_name, px(MARGIN + 92, info_top - 39),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, PEN, 1, cv2.LINE_AA)
cv2.putText(img, DATE_TEXT, px(MARGIN + 92, info_top - 87),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, PEN, 1, cv2.LINE_AA)

# Student ID: digit written in each box, matching circle shaded.
for position, ch in enumerate(grid_id):
    bx, by, bw, bh = student_id_box_rect(position)
    (tw, th), _ = cv2.getTextSize(ch, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
    cx, cy = px(bx + bw / 2, by + bh / 2)
    cv2.putText(img, ch, (cx - tw // 2, cy + th // 2),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, PEN, 1, cv2.LINE_AA)
    fill(student_id_bubble_center(position, int(ch)), ID_BUBBLE_RADIUS)

questions = list(
    assessment.questions.filter(question_type="MULTIPLE_CHOICE")
    .prefetch_related("options").order_by("order")
)[:50]

total = len(questions)
blank_q, double_q = (total - 14, total - 13) if total >= 20 else (None, None)
wrong_from, wrong_to = (total - 19, total - 15) if total >= 20 else (0, -1)

clean_correct = 0
for slot, question in enumerate(questions):
    options = sorted(question.options.all(), key=lambda o: o.label)
    labels = [o.label for o in options]
    correct = next(o.label for o in options if o.is_correct)
    wrong = [l for l in labels if l != correct]
    n = question.order

    if n == blank_q:
        picks = []                    # left blank
    elif n == double_q:
        picks = [correct, wrong[0]]   # double-marked
    elif wrong_from <= slot + 1 <= wrong_to:
        picks = [wrong[slot % len(wrong)]]
    else:
        picks = [correct]

    for label in picks:
        fill(bubble_center(slot, labels.index(label)), BUBBLE_RADIUS)
    if picks == [correct]:
        clean_correct += 1

cv2.imwrite("shaded_sheet_clean.png", img)

# Photo-like version: tilted on a gray table, blurred, unevenly lit.
h, w = img.shape[:2]
src = np.float32([[0, 0], [w, 0], [0, h], [w, h]])
dst = np.float32([[60, 45], [w + 25, 60], [40, h + 30], [w + 45, h + 10]])
photo = cv2.warpPerspective(
    img, cv2.getPerspectiveTransform(src, dst), (w + 120, h + 110),
    borderValue=(110, 110, 110),
)
photo = cv2.GaussianBlur(photo, (3, 3), 0)
photo = (photo * np.linspace(0.85, 1.0, photo.shape[1])[None, :, None]).astype(np.uint8)
cv2.imwrite("shaded_sheet.jpg", photo, [cv2.IMWRITE_JPEG_QUALITY, 92])

print(f"Assessment {assessment.pk}: {assessment.title} ({total} questions)")
print(f"Student: {STUDENT_ID} {full_name} (grid shows {grid_id})")
print(f"Flagged for review: Q{blank_q} (blank) and Q{double_q} (double-marked)")
print(f"Cleanly correct: {clean_correct}. If you resolve Q{double_q} as the correct "
      f"answer and Q{blank_q} as Blank, the score is {clean_correct + 1} / {total}.")
print("Saved shaded_sheet.jpg (photo-like) and shaded_sheet_clean.png")