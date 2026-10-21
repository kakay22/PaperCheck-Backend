
from django.urls import path

from .views import (
    MyAccountView,
    ChangePasswordView,
    TeacherRegistrationView,
)

urlpatterns = [
    path(
        "register/",
        TeacherRegistrationView.as_view(),
        name="teacher-register",
    ),
    path(
        "me/",
        MyAccountView.as_view(),
        name="my-account",
    ),
    path(
        "change-password/",
        ChangePasswordView.as_view(),
        name="change-password",
    ),
]
