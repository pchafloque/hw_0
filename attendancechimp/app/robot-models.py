# LLM-generated data model for AttendanceChimp (HW3, step 5)
#
# LLM used: Claude (Anthropic), model claude-opus-5-5
#
# Prompt:
#   "Write a Django models.py for an app called AttendanceChimp. It tracks class
#   attendance with QR codes. There are two kinds of users, students and
#   instructors. Each course has one instructor, and students can enroll in many
#   courses. Each lecture belongs to a course. Students upload a photo of the QR
#   code shown in class, and each upload belongs to a student and (optionally) a
#   lecture. The design should be simple to use, support attendance analytics,
#   and be robust to cheating. Put extra emphasis on preventing cheating."

import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


def default_qr_token():
    """Unguessable token printed in the lecture's QR code."""
    return secrets.token_urlsafe(16)


class InstructorProfile(models.Model):
    """Instructor-specific data attached to a Django user account."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name="instructor_profile")
    department = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return self.user.get_full_name() or self.user.username


class StudentProfile(models.Model):
    """Student-specific data attached to a Django user account."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name="student_profile")
    student_number = models.CharField(max_length=20, unique=True)

    def __str__(self):
        return self.user.get_full_name() or self.user.username


class Course(models.Model):
    """A course with one instructor and a weekly meeting schedule."""
    WEEKDAYS = "MTWRFSU"

    code = models.CharField(max_length=20)
    name = models.CharField(max_length=200)
    term = models.CharField(max_length=20)  # e.g. "Autumn 2026"
    instructor = models.ForeignKey(InstructorProfile, on_delete=models.PROTECT,
                                   related_name="courses")
    meeting_days = models.CharField(max_length=7, help_text="Letters from MTWRFSU, e.g. 'TR'")
    start_time = models.TimeField()
    end_time = models.TimeField()
    students = models.ManyToManyField(StudentProfile, through="Enrollment",
                                      related_name="courses")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["code", "term"], name="unique_course_per_term"),
        ]

    def __str__(self):
        return f"{self.code} ({self.term})"


class Enrollment(models.Model):
    """Junction table between StudentProfile and Course."""
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    enrolled_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)  # False if the student drops

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["student", "course"], name="unique_enrollment"),
        ]


class Lecture(models.Model):
    """One class meeting. The QR token is only valid during a short window."""
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="lectures")
    date = models.DateField()
    qr_token = models.CharField(max_length=64, unique=True, default=default_qr_token)
    qr_valid_from = models.DateTimeField(default=timezone.now)
    qr_valid_minutes = models.PositiveIntegerField(default=15)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["course", "date"], name="one_lecture_per_day"),
        ]

    def qr_is_open(self, at=None):
        """True if a check-in at time `at` falls inside the QR window."""
        at = at or timezone.now()
        return self.qr_valid_from <= at <= self.qr_valid_from + timedelta(minutes=self.qr_valid_minutes)

    def rotate_qr(self):
        """Issue a new token, e.g. if the old one was shared outside class."""
        self.qr_token = default_qr_token()
        self.qr_valid_from = timezone.now()
        self.save(update_fields=["qr_token", "qr_valid_from"])


class QRCodeUpload(models.Model):
    """A student's photo of a lecture QR code, plus checks used to flag cheating."""
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"

    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name="uploads")
    lecture = models.ForeignKey(Lecture, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="uploads")
    image = models.ImageField(upload_to="qr_uploads/%Y/%m/%d/")
    image_sha256 = models.CharField(max_length=64, db_index=True)  # same photo reused by two students
    decoded_token = models.CharField(max_length=64, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    client_ip = models.GenericIPAddressField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    rejection_reason = models.CharField(max_length=200, blank=True)

    class Meta:
        constraints = [
            # At most one accepted check-in per student per lecture.
            models.UniqueConstraint(fields=["student", "lecture"],
                                    condition=models.Q(status="accepted"),
                                    name="one_accepted_checkin"),
        ]
        indexes = [models.Index(fields=["lecture", "status"])]
