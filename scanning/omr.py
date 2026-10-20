import cv2
import numpy as np

from .alignment import align_page

from .layout import (
    BUBBLE_RADIUS,
    ID_BUBBLE_RADIUS,
    PAGE_HEIGHT,
    PAGE_WIDTH,
    QUESTIONS_PER_PAGE,
    STUDENT_ID_DIGITS,
    bubble_center,
    student_id_bubble_center,
)

# Initial calibration settings. These will need testing against
# actual printed and scanned answer sheets.
DARK_PIXEL_THRESHOLD = 150
MIN_MARK_RATIO = 0.22
MIN_CONFIDENCE_GAP = 0.10


def _circle_dark_ratio(gray, center_x, center_y, radius):
    """
    Measure the proportion of dark pixels inside a bubble,
    excluding the printed outline.
    """
    height, width = gray.shape

    inner_radius = max(2, int(radius * 0.55))

    x1 = max(0, center_x - inner_radius)
    x2 = min(width, center_x + inner_radius + 1)
    y1 = max(0, center_y - inner_radius)
    y2 = min(height, center_y + inner_radius + 1)

    if x1 >= x2 or y1 >= y2:
        return 0.0

    roi = gray[y1:y2, x1:x2]

    yy, xx = np.ogrid[y1:y2, x1:x2]
    circle_mask = (
        (xx - center_x) ** 2 + (yy - center_y) ** 2
        <= inner_radius ** 2
    )

    pixels = roi[circle_mask]

    if pixels.size == 0:
        return 0.0

    return float(np.mean(pixels < DARK_PIXEL_THRESHOLD))


def detect_answers(image_path, assessment, page_index=0):
    """
    Detect shaded bubbles on a flat, upright image of a generated
    PaperCheck A4 answer sheet.

    page_index is zero-based: first page = 0.

    Bubble positions come from scanning/layout.py, which the PDF
    generator also imports. Do not hard-code grid positions here.

    This initial version assumes:
    - the entire A4 page is visible;
    - the page is upright and not perspective-distorted;
    - the image corresponds to the current answer-sheet layout.

    It does not yet process PDFs or correct perspective distortion.
    """
    image = cv2.imread(str(image_path))

    if image is None:
        raise ValueError(
            "Unable to read image. Use a supported JPG, PNG, or WEBP image."
        )

    height, width = image.shape[:2]

    if width < 400 or height < 500:
        raise ValueError(
            "Image resolution is too low for reliable bubble detection."
        )
    
    # Straighten the photo using the four corner markers. After this the
    # image is exactly page-shaped, so the code below is unchanged.
    image = align_page(image)
    height, width = image.shape[:2]

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Map PDF points to pixels. This assumes the whole page is visible.
    scale_x = width / PAGE_WIDTH
    scale_y = height / PAGE_HEIGHT
    bubble_radius = max(2, int(BUBBLE_RADIUS * min(scale_x, scale_y)))

    questions = list(
        assessment.questions
        .filter(question_type="MULTIPLE_CHOICE")
        .prefetch_related("options")
        .order_by("order")
    )

    page_start = page_index * QUESTIONS_PER_PAGE
    page_questions = questions[
        page_start:page_start + QUESTIONS_PER_PAGE
    ]

    results = []

    for row_index, question in enumerate(page_questions):
        options = list(question.options.all().order_by("label"))
        option_results = []

        for option_index, option in enumerate(options):
            pdf_x, pdf_y = bubble_center(row_index, option_index)
            pixel_x = int(round(pdf_x * scale_x))
            pixel_y = int(round((PAGE_HEIGHT - pdf_y) * scale_y))

            ratio = _circle_dark_ratio(
                gray,
                pixel_x,
                pixel_y,
                bubble_radius,
            )

            option_results.append({
                "label": option.label,
                "dark_ratio": round(ratio, 3),
            })

        ranked = sorted(
            option_results,
            key=lambda item: item["dark_ratio"],
            reverse=True,
        )

        marked = [
            option
            for option in option_results
            if option["dark_ratio"] >= MIN_MARK_RATIO
        ]

        selected_option = None
        confidence = None

        if not marked:
            answer_status = "BLANK"

        elif len(marked) > 1:
            answer_status = "MULTIPLE_MARKS"

        else:
            top = ranked[0]
            second_ratio = ranked[1]["dark_ratio"] if len(ranked) > 1 else 0.0
            gap = top["dark_ratio"] - second_ratio

            if gap < MIN_CONFIDENCE_GAP:
                answer_status = "UNCERTAIN"
            else:
                answer_status = "DETECTED"
                selected_option = top["label"]
                confidence = round(min(1.0, gap), 3)

        results.append({
            "question_id": question.id,
            "question_number": question.order,
            "status": answer_status,
            "selected_option": selected_option,
            "confidence": confidence,
            "options": option_results,
        })

    return {
        "assessment_id": assessment.id,
        "page_index": page_index,
        "questions_processed": len(results),
        "answers": results,
    }

def detect_student_id(image_path):
    """
    Read the student ID bubble grid from page 1 of a scanned sheet.

    Returns the ID as a string, with "?" for any digit that is blank,
    double-marked, or too close to call. `complete` is True only when
    every digit was read cleanly.
    """
    image = cv2.imread(str(image_path))

    if image is None:
        raise ValueError(
            "Unable to read image. Use a supported JPG, PNG, or WEBP image."
        )

    height, width = image.shape[:2]
    if width < 400 or height < 500:
        raise ValueError(
            "Image resolution is too low for reliable bubble detection."
        )

    image = align_page(image)
    height, width = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    scale_x = width / PAGE_WIDTH
    scale_y = height / PAGE_HEIGHT
    radius = max(2, int(ID_BUBBLE_RADIUS * min(scale_x, scale_y)))

    digits = []

    for position in range(STUDENT_ID_DIGITS):
        ratios = []

        for digit in range(10):
            pdf_x, pdf_y = student_id_bubble_center(position, digit)
            pixel_x = int(round(pdf_x * scale_x))
            pixel_y = int(round((PAGE_HEIGHT - pdf_y) * scale_y))
            ratios.append(
                round(_circle_dark_ratio(gray, pixel_x, pixel_y, radius), 3)
            )

        marked = [d for d, r in enumerate(ratios) if r >= MIN_MARK_RATIO]
        value = None

        if not marked:
            status = "BLANK"
        elif len(marked) > 1:
            status = "MULTIPLE_MARKS"
        else:
            top = marked[0]
            second = max(r for d, r in enumerate(ratios) if d != top)
            if ratios[top] - second < MIN_CONFIDENCE_GAP:
                status = "UNCERTAIN"
            else:
                status = "DETECTED"
                value = top

        digits.append({
            "position": position,
            "status": status,
            "value": value,
            "ratios": ratios,
        })

    return {
        "student_id": "".join(
            str(d["value"]) if d["value"] is not None else "?"
            for d in digits
        ),
        "complete": all(d["status"] == "DETECTED" for d in digits),
        "digits": digits,
    }