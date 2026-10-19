from django.contrib import admin
from .models import School, Classroom, Student, Enrollment


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_active")
    search_fields = ("name", "code")
    list_filter = ("is_active",)


@admin.register(Classroom)
class ClassroomAdmin(admin.ModelAdmin):
    list_display = ("name", "school", "academic_year", "teacher", "is_active")
    list_filter = ("school", "academic_year", "is_active")
    search_fields = ("name", "school__name", "teacher__username")


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("student_id", "first_name", "last_name", "school", "is_active")
    search_fields = ("student_id", "first_name", "last_name")
    list_filter = ("school", "is_active")


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("student", "classroom", "status", "enrolled_at")
    list_filter = ("status", "classroom")
    search_fields = ("student__student_id", "student__last_name")