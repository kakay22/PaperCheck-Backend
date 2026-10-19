from rest_framework import serializers
from .models import Assessment, Question, QuestionOption


class QuestionOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionOption
        fields = ["id", "label", "text", "is_correct"]
        read_only_fields = ["id"]


class QuestionSerializer(serializers.ModelSerializer):
    options = QuestionOptionSerializer(many=True, required=False)

    class Meta:
        model = Question
        fields = [
            "id", "assessment", "question_type",
            "prompt", "order", "points", "required", "options",
        ]
        read_only_fields = ["id"]

    def validate(self, attrs):
        question_type = attrs.get(
            "question_type",
            getattr(self.instance, "question_type", None),
        )
        options = attrs.get("options")

        if question_type == Question.Type.MULTIPLE_CHOICE:
            if self.instance is None and options is None:
                raise serializers.ValidationError({
                    "options": "Provide answer choices for a new multiple-choice question."
                })

            if options is not None:
                labels = [option["label"] for option in options]

                if len(labels) < 2:
                    raise serializers.ValidationError({
                        "options": "Provide at least two choices."
                    })

                if len(labels) != len(set(labels)):
                    raise serializers.ValidationError({
                        "options": "Choice labels must be unique."
                    })

                if sum(bool(option.get("is_correct")) for option in options) != 1:
                    raise serializers.ValidationError({
                        "options": "Exactly one choice must be marked correct."
                    })

        return attrs

    def create(self, validated_data):
        options_data = validated_data.pop("options", [])
        question = Question.objects.create(**validated_data)

        for option in options_data:
            QuestionOption.objects.create(
                question=question,
                **option,
            )

        return question

    def update(self, instance, validated_data):
        options_data = validated_data.pop("options", None)

        for field, value in validated_data.items():
            setattr(instance, field, value)

        instance.save()

        if options_data is not None:
            instance.options.all().delete()

            for option in options_data:
                QuestionOption.objects.create(
                    question=instance,
                    **option,
                )

        return instance


class AssessmentSerializer(serializers.ModelSerializer):
    classroom_name = serializers.CharField(
        source="classroom.name",
        read_only=True,
    )
    created_by_username = serializers.CharField(
        source="created_by.username",
        read_only=True,
    )
    total_points = serializers.DecimalField(
        max_digits=9,
        decimal_places=2,
        read_only=True,
    )
    question_count = serializers.SerializerMethodField()

    class Meta:
        model = Assessment
        fields = [
            "id", "classroom", "classroom_name",
            "title", "instructions", "description", "status",
            "created_by", "created_by_username",
            "created_at", "updated_at", "total_points",
            "question_count",
        ]
        read_only_fields = [
            "id",
            "created_by",
            "created_at",
            "updated_at",
            "status",
        ]

    def get_question_count(self, obj):
        return obj.questions.count()