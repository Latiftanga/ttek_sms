import uuid
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _


class Student(models.Model):
    """
    Represents a student enrolled in the school.
    """
    class Gender(models.TextChoices):
        MALE = 'M', _('Male')
        FEMALE = 'F', _('Female')

    class Status(models.TextChoices):
        ACTIVE = 'active', _('Active')
        GRADUATED = 'graduated', _('Graduated')
        WITHDRAWN = 'withdrawn', _('Withdrawn')
        SUSPENDED = 'suspended', _('Suspended')
        TRANSFERRED = 'transferred', _('Transferred')

    class GuardianRelationship(models.TextChoices):
        FATHER = 'father', _('Father')
        MOTHER = 'mother', _('Mother')
        GUARDIAN = 'guardian', _('Guardian')
        UNCLE = 'uncle', _('Uncle')
        AUNT = 'aunt', _('Aunt')
        GRANDPARENT = 'grandparent', _('Grandparent')
        SIBLING = 'sibling', _('Sibling')
        OTHER = 'other', _('Other')

    # Personal Information
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    other_names = models.CharField(max_length=100, blank=True)
    date_of_birth = models.DateField()
    gender = models.CharField(max_length=1, choices=Gender.choices)
    photo = models.ImageField(upload_to='students/photos/', blank=True, null=True)

    # Contact Information
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=20, blank=True, help_text="Student's phone (if any)")

    # Guardian Information
    guardian_name = models.CharField(max_length=200)
    guardian_phone = models.CharField(max_length=20)
    guardian_email = models.EmailField(blank=True)
    guardian_relationship = models.CharField(
        max_length=20,
        choices=GuardianRelationship.choices,
        default=GuardianRelationship.GUARDIAN
    )
    guardian_address = models.TextField(blank=True)

    # Admission Details
    admission_number = models.CharField(
        max_length=50,
        unique=True,
        help_text="Unique student ID/admission number"
    )
    admission_date = models.DateField()

    # Enrollment
    current_class = models.ForeignKey(
        'academics.Class',
        on_delete=models.PROTECT,
        related_name='students',
        null=True,
        blank=True
    )

    # Status
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE
    )

    # Optional User Account
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='student_profile'
    )

    # Metadata
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['last_name', 'first_name']
        verbose_name = "Student"
        verbose_name_plural = "Students"

    def __str__(self):
        return f"{self.full_name} ({self.admission_number})"

    @property
    def full_name(self):
        """Return full name of student."""
        names = [self.first_name]
        if self.other_names:
            names.append(self.other_names)
        names.append(self.last_name)
        return ' '.join(names)

    @property
    def age(self):
        """Calculate student's age."""
        from datetime import date
        today = date.today()
        return today.year - self.date_of_birth.year - (
            (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
        )

    def get_enrollment_history(self):
        """Return all enrollments ordered by academic year."""
        return self.enrollments.select_related(
            'academic_year', 'class_assigned'
        ).order_by('-academic_year__start_date')

    def get_current_enrollment(self):
        """Return the active enrollment for current academic year."""
        from core.models import AcademicYear
        current_year = AcademicYear.get_current()
        if current_year:
            return self.enrollments.filter(
                academic_year=current_year,
                status=Enrollment.Status.ACTIVE
            ).first()
        return None


class Enrollment(models.Model):
    """
    Tracks a student's enrollment in a class for a specific academic year.
    This provides historical record of student progression through classes.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    class Status(models.TextChoices):
        ACTIVE = 'active', _('Active')
        PROMOTED = 'promoted', _('Promoted')
        REPEATED = 'repeated', _('Repeated')
        WITHDRAWN = 'withdrawn', _('Withdrawn')
        TRANSFERRED = 'transferred', _('Transferred')
        GRADUATED = 'graduated', _('Graduated')

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='enrollments'
    )
    academic_year = models.ForeignKey(
        'core.AcademicYear',
        on_delete=models.PROTECT,
        related_name='enrollments'
    )
    class_assigned = models.ForeignKey(
        'academics.Class',
        on_delete=models.PROTECT,
        related_name='enrollments'
    )
    enrolled_on = models.DateField(auto_now_add=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE
    )
    remarks = models.TextField(blank=True, help_text="Notes about this enrollment")

    # Track promotion source
    promoted_from = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='promoted_to',
        help_text="The enrollment this student was promoted from"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-academic_year__start_date', 'student__last_name']
        unique_together = ['student', 'academic_year']
        verbose_name = "Enrollment"
        verbose_name_plural = "Enrollments"

    def __str__(self):
        return f"{self.student.full_name} - {self.class_assigned.name} ({self.academic_year})"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Update student's current_class if this is an active enrollment
        if self.status == self.Status.ACTIVE:
            from core.models import AcademicYear
            current_year = AcademicYear.get_current()
            if current_year and self.academic_year == current_year:
                Student.objects.filter(pk=self.student_id).update(
                    current_class=self.class_assigned
                )
