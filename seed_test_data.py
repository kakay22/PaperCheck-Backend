import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from assessments.models import Assessment, Question, QuestionOption

source = Assessment.objects.first()
if source is None:
    raise SystemExit("Create one assessment in the app first.")

assessment = Assessment.objects.create(
    classroom=source.classroom,
    title="OMR Calibration Test (50 Q)",
    created_by=source.created_by,
)

for number in range(1, 51):
    question = Question.objects.create(
        assessment=assessment,
        question_type="MULTIPLE_CHOICE",
        prompt=f"Test question {number}",
        order=number,
        points=1,
    )
    for index, label in enumerate("ABCD"):
        QuestionOption.objects.create(
            question=question,
            label=label,
            text=f"Option {label}",
            is_correct=(index == 0),
        )

print(f"Created assessment {assessment.pk} with 50 questions.")