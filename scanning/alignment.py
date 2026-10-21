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


from itertools import combinations

PAGE_ASPECT = 595.28 / 841.89  # width / height of the A4 sheet


def _order_quad(points):
    """Order four points as TL, TR, BL, BR."""
    pts = sorted(points, key=lambda p: p[1])
    top = sorted(pts[:2], key=lambda p: p[0])
    bottom = sorted(pts[2:], key=lambda p: p[0])
    return [top[0], top[1], bottom[0], bottom[1]]


def _pick_corners(candidates, width, height):
    """Pick the four candidates that best form an A4-shaped quadrilateral."""
    if len(candidates) > 14:
        # Keep the candidates farthest from the image center; markers sit
        # at the sheet's corners.
        cx, cy = width / 2, height / 2
        candidates = sorted(
            candidates,
            key=lambda p: -((p[0] - cx) ** 2 + (p[1] - cy) ** 2),
        )[:14]

    best = None
    best_score = 0.0

    for combo in combinations(candidates, 4):
        tl, tr, bl, br = _order_quad(combo)
        quad = np.array([tl, tr, br, bl], dtype=np.float32)

        area = cv2.contourArea(quad)
        if area < 0.2 * width * height:
            continue
        if not cv2.isContourConvex(quad.astype(np.int32)):
            continue

        top = np.hypot(tr[0] - tl[0], tr[1] - tl[1])
        bottom = np.hypot(br[0] - bl[0], br[1] - bl[1])
        left = np.hypot(bl[0] - tl[0], bl[1] - tl[1])
        right = np.hypot(br[0] - tr[0], br[1] - tr[1])

        if min(left, right) == 0 or min(top, bottom) == 0:
            continue

        aspect = ((top + bottom) / 2) / ((left + right) / 2)
        # Perspective changes proportions, so allow a wide tolerance.
        mismatch = abs(aspect - PAGE_ASPECT) / PAGE_ASPECT
        if mismatch > 0.35:
            continue

        score = area * (1 - mismatch)
        if score > best_score:
            best_score = score
            best = [tl, tr, bl, br]

    return best


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