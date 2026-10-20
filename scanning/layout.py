"""
Single source of truth for answer-sheet geometry.

All values are in PDF points (1/72 inch), origin at the bottom-left of the
A4 page (ReportLab convention). answer_sheets.py (drawing) and omr.py
(reading) both import from here so they cannot drift apart.
"""

from reportlab.lib.pagesizes import A4

PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 42

# --- Answer grid: two columns of 25 per page ---
QUESTIONS_PER_COLUMN = 25
COLUMNS = 2
QUESTIONS_PER_PAGE = QUESTIONS_PER_COLUMN * COLUMNS
ROW_HEIGHT = 17

COLUMN_WIDTH = 245
COLUMN_LEFTS = [MARGIN, PAGE_WIDTH - MARGIN - COLUMN_WIDTH]

GRID_TOP = PAGE_HEIGHT - 322      # "ANSWER GRID" heading baseline
START_Y = GRID_TOP - 28           # column header reference line

NUMBER_RIGHT_OFFSET = 46          # question number is right-aligned here
BUBBLE_OFFSET_X = 66              # column A center, relative to column left
BUBBLE_SPACING = 40
BUBBLE_RADIUS = 6
BUBBLE_Y_OFFSET = 1               # bubble center sits 1 pt above text baseline


def row_baseline_y(row):
    """Text baseline of a row within a column (PDF coordinates)."""
    return START_Y - 18 - row * ROW_HEIGHT


def bubble_center(slot, option_index):
    """
    Center of an answer bubble in PDF coordinates.
    slot: question position on the page, 0-49 (0-24 left column,
    25-49 right column). option_index: 0 = A, 1 = B, ...
    """
    column, row = divmod(slot, QUESTIONS_PER_COLUMN)
    x = COLUMN_LEFTS[column] + BUBBLE_OFFSET_X + option_index * BUBBLE_SPACING
    y = row_baseline_y(row) + BUBBLE_Y_OFFSET
    return x, y


# --- Corner alignment markers (solid black squares) ---
MARKER_SIZE = 18
MARKER_INSET = 14  # distance from page edge to the marker's outer edge


def marker_rects():
    """
    Four corner markers as (x, y, size, size) in PDF coordinates.
    Order: top-left, top-right, bottom-left, bottom-right.
    """
    left = MARKER_INSET
    right = PAGE_WIDTH - MARKER_INSET - MARKER_SIZE
    bottom = MARKER_INSET
    top = PAGE_HEIGHT - MARKER_INSET - MARKER_SIZE
    return [
        (left, top, MARKER_SIZE, MARKER_SIZE),
        (right, top, MARKER_SIZE, MARKER_SIZE),
        (left, bottom, MARKER_SIZE, MARKER_SIZE),
        (right, bottom, MARKER_SIZE, MARKER_SIZE),
    ]


def marker_centers():
    """Marker centers in PDF coordinates, same order as marker_rects()."""
    return [(x + w / 2, y + h / 2) for x, y, w, h in marker_rects()]


# --- Student ID: write-in boxes on top, digit bubbles (0-9) underneath ---
STUDENT_ID_DIGITS = 8

ID_PANEL_LEFT = 300
ID_PANEL_RIGHT = PAGE_WIDTH - MARGIN
ID_PANEL_TOP = PAGE_HEIGHT - 108
ID_PANEL_BOTTOM = PAGE_HEIGHT - 304

ID_LABEL_X = ID_PANEL_LEFT + 14   # x of the 0-9 row labels
ID_START_X = ID_PANEL_LEFT + 40   # x of the first digit column

ID_BOX_WIDTH = 20
ID_BOX_HEIGHT = 18
ID_BOX_TOP = ID_PANEL_TOP - 24

ID_ROW_PITCH = 14
ID_BUBBLE_RADIUS = 5

ID_DIGIT_SPACING = min(
    26,
    (ID_PANEL_RIGHT - 14 - ID_START_X) / max(STUDENT_ID_DIGITS - 1, 1),
)


def student_id_bubble_center(position, digit):
    """
    Center of an ID bubble in PDF coordinates.
    position: 0 = leftmost digit column. digit: 0-9 (row 0 is at the top).
    """
    x = ID_START_X + position * ID_DIGIT_SPACING
    y = ID_BOX_TOP - ID_BOX_HEIGHT - 14 - digit * ID_ROW_PITCH
    return x, y


def student_id_box_rect(position):
    """Write-in box (x, y, width, height) above a digit column."""
    cx = ID_START_X + position * ID_DIGIT_SPACING
    return (
        cx - ID_BOX_WIDTH / 2,
        ID_BOX_TOP - ID_BOX_HEIGHT,
        ID_BOX_WIDTH,
        ID_BOX_HEIGHT,
    )