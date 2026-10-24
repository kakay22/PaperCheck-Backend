from rest_framework import serializers
from .models import Assessment, EnumerationKeyItem, Question, QuestionOption


class QuestionOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionOption
        fields = ["id", "label", "text", "is_correct"]
        read_only_fields = ["id"]


class EnumerationKeyItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = EnumerationKeyItem
        fields = ["id", "position", "variants"]
        read_only_fields = ["id"]

    def validate_variants(self, value):
        if not isinstance(value, list) or not value:
            raise serializers.ValidationError("Provide at least one accepted answer.")

        cleaned = []
        seen = set()
        for variant in value:
            if not isinstance(variant, str) or not variant.strip():
                raise serializers.ValidationError("Answers must be non-empty text.")
            text = " ".join(variant.split())
            if text.lower() in seen:
                continue
            seen.add(text.lower())
            cleaned.append(text)
        return cleaned

class QuestionSerializer(serializers.ModelSerializer):
    options = QuestionOptionSerializer(many=True, required=False)

    key_items = EnumerationKeyItemSerializer(many=True, required=False)

    class Meta:
        model = Question
        fields = [
            "id", "assessment", "question_type",
            "prompt", "order", "points", "required", "options",
            "enum_ordered", "enum_item_count", "enum_points_per_item",
            "key_items",
        ]
        read_only_fields = ["id"]

    
    def validate(self, attrs):
        question_type = attrs.get(
            "question_type",
            getattr(self.instance, "question_type", None),
        )
        options = attrs.get("options")

        # Multiple-choice validation
        if question_type == Question.Type.MULTIPLE_CHOICE:
            if self.instance is None and options is None:
                raise serializers.ValidationError({
                    "options": (
                        "Provide answer choices for a new "
                        "multiple-choice question."
                    )
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

                if sum(
                    bool(option.get("is_correct"))
                    for option in options
                ) != 1:
                    raise serializers.ValidationError({
                        "options": (
                            "Exactly one choice must be marked correct."
                        )
                    })

        # Enumeration validation
        elif question_type == Question.Type.ENUMERATION:

            def current(name, default=None):
                return attrs.get(
                    name,
                    getattr(self.instance, name, default),
                )

            count = current("enum_item_count")
            per_item = current("enum_points_per_item")
            ordered = current("enum_ordered", False)
            key_items = attrs.get("key_items")

            if count is None or not 1 <= count <= 20:
                raise serializers.ValidationError({
                    "enum_item_count": (
                        "Enter how many items students must list (1 to 20)."
                    )
                })

            if per_item is None or per_item <= 0:
                raise serializers.ValidationError({
                    "enum_points_per_item": (
                        "Points per item must be greater than zero."
                    )
                })

            if key_items is None:
                if self.instance is None:
                    raise serializers.ValidationError({
                        "key_items": "Provide the accepted answers."
                    })

                existing_items = list(
                    self.instance.key_items.all()
                )
                key_count = len(existing_items)

                positions = [
                    item.position for item in existing_items
                ]

                if len(positions) != len(set(positions)):
                    raise serializers.ValidationError({
                        "key_items": (
                            "Each answer needs a unique position."
                        )
                    })

            else:
                key_count = len(key_items)
                positions = [
                    item["position"] for item in key_items
                ]

                if len(positions) != len(set(positions)):
                    raise serializers.ValidationError({
                        "key_items": (
                            "Each answer needs a unique position."
                        )
                    })

            # Validate answer positions against the configured item count.
            if any(position < 1 or position > count for position in positions):
                raise serializers.ValidationError({
                    "key_items": (
                        f"Answer positions must be between 1 and {count}."
                    )
                })

            # Check duplicate accepted answers for unordered enumerations.
            if not ordered:
                if key_items is None:
                    items_to_check = [
                        {
                            "position": item.position,
                            "variants": item.variants or [],
                        }
                        for item in existing_items
                    ]
                else:
                    items_to_check = key_items

                seen = {}

                for item in items_to_check:
                    for variant in item.get("variants", []):
                        normalized = " ".join(
                            str(variant).split()
                        ).casefold()

                        if not normalized:
                            continue

                        if (
                            normalized in seen
                            and seen[normalized] != item["position"]
                        ):
                            raise serializers.ValidationError({
                                "key_items": (
                                    f'"{variant}" is listed under '
                                    "two different items."
                                )
                            })

                        seen[normalized] = item["position"]

            if ordered and key_count != count:
                raise serializers.ValidationError({
                    "key_items": (
                        f"An ordered list needs exactly {count} answers."
                    )
                })

            if not ordered and key_count < count:
                raise serializers.ValidationError({
                    "key_items": (
                        f"Provide at least {count} accepted answers."
                    )
                })

            # Enumeration points are calculated automatically.
            attrs["points"] = count * per_item

        return attrs


    def create(self, validated_data):
        options_data = validated_data.pop("options", [])
        key_items_data = validated_data.pop("key_items", [])

        # Calculate enumeration points automatically.
        if validated_data.get("question_type") == "ENUMERATION":
            count = validated_data.get("enum_item_count")
            per_item = validated_data.get("enum_points_per_item")

            if count is not None and per_item is not None:
                validated_data["points"] = count * per_item

        question = Question.objects.create(**validated_data)

        for item in key_items_data:
            EnumerationKeyItem.objects.create(
                question=question,
                **item,
            )

        for option in options_data:
            QuestionOption.objects.create(
                question=question,
                **option,
            )

        return question
    
    def update(self, instance, validated_data):
        options_data = validated_data.pop("options", None)
        key_items_data = validated_data.pop("key_items", None)

        for field, value in validated_data.items():
            setattr(instance, field, value)

        # Recalculate enumeration points when updating a question.
        if instance.question_type == "ENUMERATION":
            count = instance.enum_item_count
            per_item = instance.enum_points_per_item

            if count is not None and per_item is not None:
                instance.points = count * per_item

        instance.save()

        if options_data is not None:
            instance.options.all().delete()

            for option in options_data:
                QuestionOption.objects.create(
                    question=instance,
                    **option,
                )

        if key_items_data is not None:
            instance.key_items.all().delete()

            for item in key_items_data:
                EnumerationKeyItem.objects.create(
                    question=instance,
                    **item,
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