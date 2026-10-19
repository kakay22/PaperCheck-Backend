"""
Single source of truth for answer-sheet geometry.

All values are in PDF points (1/72 inch) with the origin at the bottom-left
of the A4 page, as ReportLab uses. answer_sheets.py (drawing) and omr.py
(reading) both import from here so they cannot drift apart.
"""

from reportlab.lib.pagesizes import A4

PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 42

QUESTIONS_PER_PAGE = 25
ROW_HEIGHT = 20

GRID_TOP = PAGE_HEIGHT - 247      # "ANSWER GRID" heading baseline
START_Y = GRID_TOP - 28           # column header reference line

QUESTION_X = MARGIN + 13
BUBBLE_START_X = MARGIN + 155
BUBBLE_SPACING = 48
BUBBLE_RADIUS = 6
BUBBLE_Y_OFFSET = 1               # bubble center sits 1 pt above text baseline


def row_baseline_y(row_index):
    """Text baseline of a question row (PDF coordinates)."""
    return START_Y - 18 - row_index * ROW_HEIGHT


def bubble_center(row_index, option_index):
    """Center of a bubble in PDF coordinates (x, y from bottom-left)."""
    x = BUBBLE_START_X + option_index * BUBBLE_SPACING
    y = row_baseline_y(row_index) + BUBBLE_Y_OFFSET
    return x, y