import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from scanning.models import ScanFile, ScanResult
from scanning.preview import render_marked_sheet

sf = ScanFile.objects.filter(status="COMPLETED").order_by("-id").first()
print("scan file:", sf.pk, sf.file.path, "exists:", os.path.isfile(sf.file.path))

results = {r.question_id: r for r in ScanResult.objects.filter(scan_file=sf)}
jpeg = render_marked_sheet(sf.file.path, sf.scan_job.assessment, results)
open("preview_check.jpg", "wb").write(jpeg)
print("OK, saved preview_check.jpg", len(jpeg), "bytes")