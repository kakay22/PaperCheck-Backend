
from django.contrib.auth import password_validation
from rest_framework import serializers

from .models import User


class MyAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "role",
            "is_active",
            "date_joined",
        ]
        read_only_fields = [
            "id",
            "username",
            "role",
            "is_active",
            "date_joined",
        ]


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
    )
    new_password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
    )
    confirm_password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
    )

    def validate_current_password(self, value):
        user = self.context["request"].user

        if not user.check_password(value):
            raise serializers.ValidationError(
                "Your current password is incorrect."
            )

        return value

    def validate(self, attrs):
        new_password = attrs["new_password"]
        confirm_password = attrs["confirm_password"]
        user = self.context["request"].user

        if new_password != confirm_password:
            raise serializers.ValidationError({
                "confirm_password": "The passwords do not match."
            })

        if user.check_password(new_password):
            raise serializers.ValidationError({
                "new_password": "Your new password must differ from your current password."
            })

        password_validation.validate_password(
            new_password,
            user=user,
        )

        return attrs


class RegisterTeacherSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        style={"input_type": "password"},
    )
    confirm_password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        style={"input_type": "password"},
    )

    class Meta:
        model = User
        fields = [
            "first_name",
            "last_name",
            "username",
            "email",
            "password",
            "confirm_password",
        ]

    def validate_username(self, value):
        value = value.strip()

        if not value:
            raise serializers.ValidationError(
                "Username is required."
            )

        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError(
                "This username is already taken."
            )

        return value

    def validate_email(self, value):
        value = value.strip().lower()

        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError(
                "An account with this email already exists."
            )

        return value

    def validate_first_name(self, value):
        value = value.strip()

        if not value:
            raise serializers.ValidationError(
                "First name is required."
            )

        return value

    def validate_last_name(self, value):
        value = value.strip()

        if not value:
            raise serializers.ValidationError(
                "Last name is required."
            )

        return value

    def validate(self, attrs):
        if attrs["password"] != attrs["confirm_password"]:
            raise serializers.ValidationError({
                "confirm_password": "The passwords do not match."
            })

        # Validate against the prospective teacher account.
        prospective_user = User(
            username=attrs["username"],
            email=attrs["email"],
            first_name=attrs["first_name"],
            last_name=attrs["last_name"],
            role=User.Role.TEACHER,
        )

        password_validation.validate_password(
            attrs["password"],
            user=prospective_user,
        )

        return attrs

    def create(self, validated_data):
        validated_data.pop("confirm_password")
        raw_password = validated_data.pop("password")

        # Never accept the role from the registration request.
        user = User(
            **validated_data,
            role=User.Role.TEACHER,
        )
        user.set_password(raw_password)
        user.save()

        return user
