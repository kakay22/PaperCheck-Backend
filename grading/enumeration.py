
from decimal import Decimal


def normalize_answer(value):
    """
    Normalize text for case-insensitive, whitespace-insensitive matching.
    Example: "  Cell   Membrane " -> "cell membrane"
    """
    if value is None:
        return ""

    return " ".join(str(value).split()).casefold()


def split_student_answers(answers):
    """
    Accept either a list of answers or newline-separated text.
    Blank entries are retained so ordered answers keep their positions.
    """
    if isinstance(answers, str):
        return answers.splitlines()

    if isinstance(answers, (list, tuple)):
        return ["" if answer is None else str(answer) for answer in answers]

    raise ValueError("Answers must be a list of strings or newline-separated text.")


def score_enumeration_answer(question, answers):
    """
    Score an enumeration question using its accepted key items.

    Ordered question:
        A response earns credit only when it matches the key at the
        corresponding position.

    Unordered question:
        A response may match any accepted key item, but each key item
        can earn points only once.

    Returns scoring details without saving anything to the database.
    """
    if question.question_type != "ENUMERATION":
        raise ValueError("The supplied question is not an enumeration question.")

    if question.enum_item_count is None:
        raise ValueError("The question has no configured enumeration item count.")

    if question.enum_points_per_item is None:
        raise ValueError("The question has no configured points per item.")

    student_answers = split_student_answers(answers)
    key_items = list(question.key_items.all().order_by("position"))

    if not key_items:
        raise ValueError("This enumeration question has no answer key.")

    points_per_item = Decimal(str(question.enum_points_per_item))
    earned_points = Decimal("0.00")
    used_key_positions = set()
    results = []

    # Build a normalized lookup for unordered matching.
    accepted_answers = {}

    if not question.enum_ordered:
        for key_item in key_items:
            for variant in key_item.variants or []:
                normalized = normalize_answer(variant)
                if normalized:
                    accepted_answers[normalized] = key_item

    for index in range(question.enum_item_count):
        answer = (
            student_answers[index].strip()
            if index < len(student_answers)
            else ""
        )
        normalized_answer = normalize_answer(answer)

        matched_item = None

        if normalized_answer:
            if question.enum_ordered:
                # Only the key item at this position can earn credit.
                matched_item = next(
                    (
                        item
                        for item in key_items
                        if item.position == index + 1
                    ),
                    None,
                )

                if matched_item:
                    accepted = {
                        normalize_answer(variant)
                        for variant in (matched_item.variants or [])
                    }
                    if normalized_answer not in accepted:
                        matched_item = None

            else:
                # Any accepted key item can match, but only once.
                candidate = accepted_answers.get(normalized_answer)

                if (
                    candidate is not None
                    and candidate.position not in used_key_positions
                ):
                    matched_item = candidate

        correct = matched_item is not None

        if correct:
            earned_points += points_per_item
            used_key_positions.add(matched_item.position)

        results.append({
            "position": index + 1,
            "answer": answer,
            "is_correct": correct,
            "matched_key_position": (
                matched_item.position if matched_item else None
            ),
            "awarded_points": (
                str(points_per_item) if correct else "0.00"
            ),
        })

    maximum_points = Decimal(str(question.points))

    return {
        "question_id": question.id,
        "question_type": question.question_type,
        "ordered": question.enum_ordered,
        "answers": results,
        "earned_points": str(earned_points),
        "maximum_points": str(maximum_points),
        "is_correct": earned_points >= maximum_points,
    }
