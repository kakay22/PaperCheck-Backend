
from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

urlpatterns = [
    path("admin/", admin.site.urls),

    # Authentication
    path(
        "api/v1/auth/login/",
        TokenObtainPairView.as_view(),
        name="token_obtain_pair",
    ),
    path(
        "api/v1/auth/refresh/",
        TokenRefreshView.as_view(),
        name="token_refresh",
    ),

    # Account settings
    path("api/v1/auth/", include("accounts.urls")),

    # Existing application routes
    path("api/v1/", include("schools.urls")),
    path("api/v1/", include("assessments.urls")),
    path("api/v1/", include("scanning.urls")),
]
