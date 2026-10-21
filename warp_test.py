import os

import cv2
import django
import numpy as np

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from assessments.models import Assessment
from scanning.alignment import align_page
from scanning.omr import detect_answers

assessment = (
    Assessment.objects.filter(questions__question_type="MULTIPLE_CHOICE")
    .distinct()
    .order_by("-id")
    .first()
)

img = cv2.imread("filled_page1.png")
h, w = img.shape[:2]

src = np.float32([[0, 0], [w, 0], [0, h], [w, h]])
dst = np.float32([[140, 110], [w + 60, 150], [90, h + 70], [w + 110, h + 30]])

matrix = cv2.getPerspectiveTransform(src, dst)
bad = cv2.warpPerspective(img, matrix, (w + 250, h + 250), borderValue=(120, 120, 120))
bad = cv2.GaussianBlur(bad, (3, 3), 0)

gradient = np.linspace(0.75, 1.0, bad.shape[1])[None, :, None]
bad = (bad * gradient).astype(np.uint8)

cv2.imwrite("distorted_page1.png", bad)
cv2.imwrite("aligned_page1.png", align_page(bad))

clean = detect_answers("filled_page1.png", assessment, page_index=0)
messy = detect_answers("distorted_page1.png", assessment, page_index=0)

same = 0
for a, b in zip(clean["answers"], messy["answers"]):
    key_a = (a["status"], a["selected_option"])
    key_b = (b["status"], b["selected_option"])
    if key_a == key_b:
        same += 1
    else:
        print(f"Q{a['question_number']}: clean {key_a}, distorted {key_b}")

print(f"{same}/{len(clean['answers'])} identical. Saved distorted_page1.png and aligned_page1.png")