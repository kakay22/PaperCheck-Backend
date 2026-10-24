from pathlib import Path

ROOT = Path.cwd()
OUTPUT = ROOT / "enumeration_scanner_context.txt"

FILES = [
    "assessments/models.py",
    "assessments/serializers.py",
    "assessments/views.py",
    "assessments/urls.py",
    "scanning/models.py",
    "scanning/serializers.py",
    "scanning/views.py",
    "scanning/urls.py",
    "scanning/layout.py",
    "scanning/answer_sheets.py",
    "grading/models.py",
    "grading/serializers.py",
    "grading/views.py",
    "grading/urls.py",
    "schools/models.py",
    "schools/serializers.py",
    "schools/views.py",
    "schools/urls.py",
    "config/urls.py",
]

with OUTPUT.open("w", encoding="utf-8") as out:
    out.write("PAPERCHECK ENUMERATION SCANNER CONTEXT\n")
    out.write(f"Project root: {ROOT}\n\n")

    for relative in FILES:
        path = ROOT / relative
        out.write("\n" + "=" * 90 + "\n")
        out.write(f"FILE: {relative}\n")
        out.write("=" * 90 + "\n")

        if path.is_file():
            try:
                out.write(path.read_text(encoding="utf-8"))
            except Exception as exc:
                out.write(f"[Could not read file: {exc}]\n")
        else:
            out.write("[FILE NOT FOUND]\n")

        out.write("\n")

print(f"\nContext file created:\n{OUTPUT}")
print("Please upload enumeration_scanner_context.txt here.")
