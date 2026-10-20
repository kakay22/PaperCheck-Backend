import cv2

from .alignment import WARP_SCALE, align_page
from .layout import (
    BUBBLE_RADIUS,
    PAGE_HEIGHT,
    QUESTIONS_PER_PAGE,
    bubble_center,
)
from .omr import MIN_MARK_RATIO

GREEN = (0, 170, 0)
RED = (0, 0, 230)
AMBER = (0, 165, 255)


def _ring(image, slot, option_index, color):
    x, y = bubble_center(slot, option_index)
    center = (
        int(round(x * WARP_SCALE)),
        int(round((PAGE_HEIGHT - y) * WARP_SCALE)),
    )
    radius = int(round(BUBBLE_RADIUS * WARP_SCALE)) + 4
    cv2.circle(image, center, radius, color, 3)


def render_marked_sheet(image_path, assessment, results_by_question):
    """
    Return JPEG bytes of the straightened sheet with rings on the bubbles.
    results_by_question maps question id -> ScanResult.
    """
    image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError("Unable to read the uploaded image.")

    sheet = align_page(image)

    questions = list(
        assessment.questions
        .filter(question_type="MULTIPLE_CHOICE")
        .prefetch_related("options")
        .order_by("order")
    )[:QUESTIONS_PER_PAGE * 2]

    for slot, question in enumerate(questions):
        options = sorted(question.options.all(), key=lambda o: o.label)
        labels = [option.label for option in options]
        correct_index = next(
            (i for i, option in enumerate(options) if option.is_correct), None
        )

        result = results_by_question.get(question.id)
        selected = (result.selected_label if result else "").strip().upper()

        if selected in labels:
            chosen = labels.index(selected)
            if chosen == correct_index:
                _ring(sheet, slot, chosen, GREEN)
            else:
                _ring(sheet, slot, chosen, RED)
                if correct_index is not None:
                    _ring(sheet, slot, correct_index, GREEN)
        else:
            # Blank or unresolved: show what was marked, then the answer.
            if result:
                for detail in result.option_details or []:
                    if (
                        detail.get("label") in labels
                        and detail.get("dark_ratio", 0) >= MIN_MARK_RATIO
                    ):
                        _ring(sheet, slot, labels.index(detail["label"]), AMBER)
            if correct_index is not None:
                _ring(sheet, slot, correct_index, GREEN)

    ok, buffer = cv2.imencode(".jpg", sheet, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise ValueError("Could not render the marked sheet.")
    return buffer.tobytes()