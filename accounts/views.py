
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError as DjangoValidationError

from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated, AllowAny

from .serializers import (
    MyAccountSerializer,
    ChangePasswordSerializer,
    RegisterTeacherSerializer,
)


class MyAccountView(generics.RetrieveUpdateAPIView):
    """
    Retrieve or update only the authenticated user's own account.
    """

    serializer_class = MyAccountSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self):
        return self.request.user


class ChangePasswordView(APIView):
    """
    Change the authenticated user's password after verifying
    their current password.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

        user = request.user
        new_password = serializer.validated_data["new_password"]

        try:
            password_validation.validate_password(
                new_password,
                user=user,
            )
        except DjangoValidationError as exc:
            raise ValidationError({
                "new_password": list(exc.messages)
            })

        user.set_password(new_password)
        user.save(update_fields=["password"])

        return Response(
            {"detail": "Password changed successfully."},
            status=status.HTTP_200_OK,
        )


class TeacherRegistrationView(generics.CreateAPIView):
    """
    Public registration endpoint for teacher accounts.
    The role is always assigned by the backend.
    """

    serializer_class = RegisterTeacherSerializer
    permission_classes = [AllowAny]
    authentication_classes = []
    http_method_names = ["post", "options", "head"]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        return Response(
            {
                "detail": "Teacher account created successfully.",
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "email": user.email,
                    "role": user.role,
                },
            },
            status=status.HTTP_201_CREATED,
        )
