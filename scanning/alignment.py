import cv2
import numpy as np

from .layout import PAGE_HEIGHT, PAGE_WIDTH, marker_centers

# Output pixels per PDF point. 3 gives roughly 216 dpi, plenty for bubbles.
WARP_SCALE = 3

MAX_ASPECT = 1.35   # markers must look roughly square
MIN_FILL = 0.85     # solid squares fill their bounding box; circles do not (~0.78)


def _binarizations(gray):
    """Yield dark-on-white masks, trying the simple method first."""
    blur = cv2.GaussianBlur(gray, (5, 5), 0)

    _, otsu = cv2.threshold(
        blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )
    yield otsu

    # Fallback for uneven lighting. The block must be bigger than a marker.
    block = int(min(gray.shape) * 0.12) | 1
    yield cv2.adaptiveThreshold(
        blur, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
        cv2.THRESH_BINARY_INV, block, 15,
    )


def _square_candidates(binary):
    """Return centroids of solid, roughly square, marker-sized blobs."""
    min_dim = min(binary.shape)
    min_side = 0.012 * min_dim
    max_side = 0.08 * min_dim

    contours, _ = cv2.findContours(
        binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE
    )

    found = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < min_side ** 2 or area > max_side ** 2:
            continue

        _, (rw, rh), _ = cv2.minAreaRect(contour)
        if rw == 0 or rh == 0:
            continue

        aspect = max(rw, rh) / min(rw, rh)
        fill = area / (rw * rh)
        if aspect > MAX_ASPECT or fill < MIN_FILL:
            continue

        # Real markers are solid; hollow boxes (like the ID write-in
        # squares) are not.
        bx, by, bw, bh = cv2.boundingRect(contour)
        mask = np.zeros((bh, bw), dtype=np.uint8)
        cv2.drawContours(
            mask, [contour - np.array([bx, by])], -1, 255, thickness=-1
        )
        if cv2.mean(binary[by:by + bh, bx:bx + bw], mask=mask)[0] < 200:
            continue

        m = cv2.moments(contour)
        found.append((m["m10"] / m["m00"], m["m01"] / m["m00"]))

    return found


def _pick_corners(candidates, width, height):
    """Pick the candidate nearest each image corner: TL, TR, BL, BR."""
    targets = [(0, 0), (width, 0), (0, height), (width, height)]
    picked = [
        min(candidates, key=lambda p: (p[0] - tx) ** 2 + (p[1] - ty) ** 2)
        for tx, ty in targets
    ]

    if len(set(picked)) < 4:
        return None

    # The four markers should enclose a large part of the image.
    quad = np.array(
        [picked[0], picked[1], picked[3], picked[2]], dtype=np.float32
    )
    if cv2.contourArea(quad) < 0.2 * width * height:
        return None

    return picked


def align_page(image):
    """
    Find the four corner markers and warp the image so the page fills
    PAGE_WIDTH x PAGE_HEIGHT points at WARP_SCALE pixels per point.

    Assumes the sheet is roughly upright (not rotated 90 or 180 degrees).
    Raises ValueError if the markers cannot be found.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape

    for binary in _binarizations(gray):
        candidates = _square_candidates(binary)
        if len(candidates) < 4:
            continue

        corners = _pick_corners(candidates, width, height)
        if corners is None:
            continue

        src = np.float32(corners)
        dst = np.float32([
            [x * WARP_SCALE, (PAGE_HEIGHT - y) * WARP_SCALE]
            for x, y in marker_centers()
        ])

        matrix = cv2.getPerspectiveTransform(src, dst)
        return cv2.warpPerspective(
            image,
            matrix,
            (
                int(round(PAGE_WIDTH * WARP_SCALE)),
                int(round(PAGE_HEIGHT * WARP_SCALE)),
            ),
            flags=cv2.INTER_LINEAR,
            borderValue=(255, 255, 255),
        )

    raise ValueError(
        "Could not find the four corner markers. Make sure the whole "
        "sheet is visible, flat, well lit, and printed with the markers "
        "intact."
    )