from rest_framework.routers import DefaultRouter
from .views import (
    SchoolViewSet,
    ClassroomViewSet,
    StudentViewSet,
    EnrollmentViewSet,
)

router = DefaultRouter()
router.register("schools", SchoolViewSet, basename="school")
router.register("classes", ClassroomViewSet, basename="classroom")
router.register("students", StudentViewSet, basename="student")
router.register("enrollments", EnrollmentViewSet, basename="enrollment")

urlpatterns = router.urls