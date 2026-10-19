from rest_framework.routers import DefaultRouter
from .views import AssessmentViewSet, QuestionViewSet

router = DefaultRouter()
router.register("assessments", AssessmentViewSet, basename="assessment")
router.register("questions", QuestionViewSet, basename="question")

urlpatterns = router.urls