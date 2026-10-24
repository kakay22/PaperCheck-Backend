
from PIL import Image, ImageDraw, ImageFont
import os
import random

# Output image
OUTPUT = "enumeration_sample_kyle_calites.jpg"

WIDTH, HEIGHT = 1240, 1754
image = Image.new("RGB", (WIDTH, HEIGHT), "#fffdf7")
draw = ImageDraw.Draw(image)

def get_font(size, bold=False):
    candidates = [
        r"C:\Windows\Fonts\arialbd.ttf" if bold
        else r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\calibrib.ttf" if bold
        else r"C:\Windows\Fonts\calibri.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()

title_font = get_font(38, True)
heading_font = get_font(27, True)
body_font = get_font(25)
hand_font = get_font(29)
small_font = get_font(21)

# Paper border and heading
draw.rounded_rectangle(
    (45, 40, WIDTH - 45, HEIGHT - 40),
    radius=18, outline="#c9c9c9", width=2
)

draw.text((85, 80), "PAPERCHECK - ENUMERATION PRACTICE",
          font=title_font, fill="#172033")

draw.line((85, 145, WIDTH - 85, 145), fill="#334155", width=3)

draw.text((85, 175), "Student: Kyle Calites",
          font=body_font, fill="#222222")
draw.text((85, 220), "Student ID: 2026-001",
          font=body_font, fill="#222222")
draw.text((85, 265), "Date: October 22, 2026",
          font=body_font, fill="#222222")

draw.line((85, 315, WIDTH - 85, 315), fill="#b8bec8", width=2)

draw.text((85, 355), "Directions",
          font=heading_font, fill="#172033")
draw.text(
    (85, 400),
    "Write each answer on the numbered line below.",
    font=body_font, fill="#333333"
)

questions = [
    {
        "question": "1. List three renewable energy sources.",
        "answers": [
            "1. Solar energy",
            "2. Wind energy",
            "3. Hydroelectric power",
        ],
    },
    {
        "question": "2. List two states of water.",
        "answers": [
            "4. Solid",
            "5. Liquid",
        ],
    },
]

y = 485
for item in questions:
    draw.text((85, y), item["question"],
              font=heading_font, fill="#172033")
    y += 62

    for answer in item["answers"]:
        # Simulated handwritten-style blue ink
        x = 125 + random.randint(-2, 2)
        draw.text(
            (x, y),
            answer,
            font=hand_font,
            fill="#234f91",
            stroke_width=0,
        )
        y += 58

    y += 45

draw.line((85, y + 15, WIDTH - 85, y + 15),
          fill="#b8bec8", width=2)
draw.text(
    (85, y + 45),
    "Teacher's notes:",
    font=small_font,
    fill="#555555",
)
draw.line(
    (85, y + 100, WIDTH - 85, y + 100),
    fill="#d1d5db", width=2
)

image.save(OUTPUT, quality=95)
print(f"Sample enumeration paper created: {os.path.abspath(OUTPUT)}")
