import os
import random

import cv2
import django
import numpy as np
import pymupdf

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from assessments.models import Assessment
from scanning.answer_sheets import generate_answer_sheet
from scanning.layout import (
    BUBBLE_RADIUS,
    PAGE_HEIGHT,
    PAGE_WIDTH,
    QUESTIONS_PER_PAGE,
    bubble_center,
)
from scanning.omr import detect_answers

PAGE = 0

assessment = (
    Assessment.objects.filter(questions__question_type="MULTIPLE_CHOICE")
    .distinct()
    .order_by("-id")
    .first()
)
if assessment is None:
    raise SystemExit("No assessment with multiple-choice questions found.")

doc = pymupdf.open(stream=generate_answer_sheet(assessment).read(), filetype="pdf")
pix = doc[PAGE].get_pixmap(dpi=150)
img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

sx, sy = pix.width / PAGE_WIDTH, pix.height / PAGE_HEIGHT

questions = list(
    assessment.questions.filter(question_type="MULTIPLE_CHOICE").order_by("order")
)[PAGE * QUESTIONS_PER_PAGE:(PAGE + 1) * QUESTIONS_PER_PAGE]

random.seed(1)
expected = {}

for slot, question in enumerate(questions):
    # Every 7th question blank, every 11th double-marked.
    if (slot + 1) % 7 == 0:
        expected[question.order] = "BLANK"
        continue

    labels = sorted(o.label for o in question.options.all())
    picks = [random.randrange(len(labels))]
    if (slot + 1) % 11 == 0:
        picks.append((picks[0] + 1) % len(labels))
        expected[question.order] = "MULTIPLE_MARKS"
    else:
        expected[question.order] = labels[picks[0]]

    for col in picks:
        x, y = bubble_center(slot, col)
        px = int(round(x * sx))
        py = int(round((PAGE_HEIGHT - y) * sy))
        r = int(round(BUBBLE_RADIUS * min(sx, sy)))
        cv2.circle(img, (px, py), r, (40, 40, 40), -1)

cv2.imwrite("filled_page1.png", img)

result = detect_answers("filled_page1.png", assessment, page_index=PAGE)

correct = 0
for ans in result["answers"]:
    want = expected[ans["question_number"]]
    got = ans["selected_option"] or ans["status"]
    ok = got == want
    correct += ok
    if not ok:
        print(f"Q{ans['question_number']}: expected {want}, got {got}  {ans['options']}")

print(f"{correct}/{len(result['answers'])} matched. Saved filled_page1.png")