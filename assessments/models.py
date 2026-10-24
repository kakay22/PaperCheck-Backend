from django.conf import settings
from django.db import models


class Assessment(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PUBLISHED = "PUBLISHED", "Published"
        CLOSED = "CLOSED", "Closed"

    classroom = models.ForeignKey(
        "schools.Classroom",
        on_delete=models.PROTECT,
        related_name="assessments",
    )
    title = models.CharField(max_length=200)
    instructions = models.TextField(blank=True)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_assessments",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    @property
    def total_points(self):
        return sum(question.points for question in self.questions.all())


class Question(models.Model):
    class Type(models.TextChoices):
        MULTIPLE_CHOICE = "MULTIPLE_CHOICE", "Multiple Choice"
        ENUMERATION = "ENUMERATION", "Enumeration"
        SHORT_ANSWER = "SHORT_ANSWER", "Short Answer"
        ESSAY = "ESSAY", "Essay"

    assessment = models.ForeignKey(
        Assessment,
        on_delete=models.CASCADE,
        related_name="questions",
    )
    question_type = models.CharField(
        max_length=20,
        choices=Type.choices,
        default=Type.MULTIPLE_CHOICE,
    )
    prompt = models.TextField()
    order = models.PositiveIntegerField()
    points = models.DecimalField(max_digits=7, decimal_places=2, default=1)
    required = models.BooleanField(default=True)

    enum_ordered = models.BooleanField(default=False)
    enum_item_count = models.PositiveSmallIntegerField(null=True, blank=True)
    enum_points_per_item = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True
    )

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(
                fields=["assessment", "order"],
                name="unique_question_order_per_assessment",
            )
        ]

    def __str__(self):
        return f"{self.assessment.title} - Question {self.order}"


class QuestionOption(models.Model):
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="options",
    )
    label = models.CharField(max_length=5)
    text = models.CharField(max_length=500)
    is_correct = models.BooleanField(default=False)

    class Meta:
        ordering = ["label"]
        constraints = [
            models.UniqueConstraint(
                fields=["question", "label"],
                name="unique_option_label_per_question",
            )
        ]

    def __str__(self):
        return f"{self.question} - {self.label}"

class EnumerationKeyItem(models.Model):
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="key_items",
    )
    position = models.PositiveSmallIntegerField()
    # Accepted spellings for this item, e.g. ["mitochondria", "mitochondrion"]
    variants = models.JSONField(default=list)

    class Meta:
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(
                fields=["question", "position"],
                name="unique_key_item_position_per_question",
            )
        ]

    def __str__(self):
        return f"{self.question} - item {self.position}"