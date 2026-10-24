
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    AnswerSheetDownloadView,
    EnumerationAnswerReviewView,
    ScanUploadView,
    ScanJobViewSet,
    ScanFileConfirmDetectedView,
    ScanFilePreviewView,
    ScanFileProcessView,
    ScanFileResultsView,
    ScanResultReviewView,
    ScanFileGradeView,
    SubmissionApproveView,
    SubmissionListView,
    SubmissionAuditHistoryView,
    SubmissionEnumerationAnswersView,
    ScanFileEnumerationReviewView
)

router = DefaultRouter()
router.register("scan-jobs", ScanJobViewSet, basename="scan-job")

urlpatterns = [
    # Answer sheet and scan uploads
    path(
        "assessments/<int:assessment_id>/answer-sheet/",
        AnswerSheetDownloadView.as_view(),
        name="answer-sheet-download",
    ),
    path(
        "assessments/<int:assessment_id>/scan-uploads/",
        ScanUploadView.as_view(),
        name="scan-upload",
    ),

    # Scan processing and answer review
    path(
        "scan-files/<int:scan_file_id>/process/",
        ScanFileProcessView.as_view(),
        name="scan-file-process",
    ),
    path(
        "scan-files/<int:scan_file_id>/results/",
        ScanFileResultsView.as_view(),
        name="scan-file-results",
    ),
    path(
        "scan-results/<int:scan_result_id>/review/",
        ScanResultReviewView.as_view(),
        name="scan-result-review",
    ),
    path(
        "scan-files/<int:scan_file_id>/confirm-detected/",
        ScanFileConfirmDetectedView.as_view(),
        name="scan-file-confirm-detected",
    ),
    path(
        "scan-files/<int:scan_file_id>/preview/",
        ScanFilePreviewView.as_view(),
        name="scan-file-preview",
    ),

    # Grading
    path(
        "scan-files/<int:scan_file_id>/grade/",
        ScanFileGradeView.as_view(),
        name="scan-file-grade",
    ),
    path(
        "submissions/",
        SubmissionListView.as_view(),
        name="submission-list",
    ),
    path(
        "submissions/<int:submission_id>/approve/",
        SubmissionApproveView.as_view(),
        name="submission-approve",
    ),
    path(
        "submissions/<int:submission_id>/audit-history/",
        SubmissionAuditHistoryView.as_view(),
        name="submission-audit-history",
    ),

    path(
        "submissions/<int:submission_id>/enumeration-answers/",
        SubmissionEnumerationAnswersView.as_view(),
        name="submission-enumeration-answers",
    ),

    path(
        "submissions/<int:submission_id>/answers/<int:answer_id>/review/",
        EnumerationAnswerReviewView.as_view(),
        name="enumeration-answer-review",
    ),

    path(
        "scan-files/<int:scan_file_id>/enumeration-review/",
        ScanFileEnumerationReviewView.as_view(),
        name="scan-file-enumeration-review",
    ),

    # Scan job listing
    path("", include(router.urls)),
]
