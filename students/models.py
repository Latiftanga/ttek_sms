import uuid
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _


class House(models.Model):
    """
    Represents a school house for grouping students.
    Used for inter-house competitions, organizing students, etc.
    """
    name = models.CharField(
        _("house name"),
        max_length=50,
        unique=True,
        help_text="e.g., Blue House, Nkrumah House"
    )
    color = models.CharField(
        _("color name"),
        max_length=30,
        blank=True,
        help_text="e.g., Blue, Red, Green"
    )
    color_code = models.CharField(
        _("color code"),
        max_length=7,
        blank=True,
        help_text="Hex color code e.g., #3B82F6"
    )
    motto = models.CharField(
        _("motto"),
        max_length=255,
        blank=True
    )
    description = models.TextField(_("description"), blank=True)
    is_active = models.BooleanField(_("active"), default=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("House")
        verbose_name_plural = _("Houses")
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def student_count(self):
        """Return count of active students in this house."""
        return self.students.filter(status='active').count()


class Guardian(models.Model):
    """
    Represents a guardian or parent of a student.
    A guardian can be associated with multiple students.
    """
    class Relationship(models.TextChoices):
        FATHER = 'father', _('Father')
        MOTHER = 'mother', _('Mother')
        BROTHER = 'brother', _('Brother')
        SISTER = 'sister', _('Sister')
        UNCLE = 'uncle', _('Uncle')
        AUNT = 'aunt', _('Aunt')
        GRANDFATHER = 'grandfather', _('Grandfather')
        GRANDMOTHER = 'grandmother', _('Grandmother')
        GUARDIAN = 'guardian', _('Guardian')
        OTHER = 'other', _('Other')

    # Personal Information
    full_name = models.CharField(_("full name"), max_length=255)
    phone_number = models.CharField(_("phone number"), max_length=20, unique=True)
    email = models.EmailField(_("email address"), blank=True, null=True)
    occupation = models.CharField(_("occupation"), max_length=100, blank=True)
    address = models.TextField(_("address"), blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Guardian")
        verbose_name_plural = _("Guardians")
        ordering = ['full_name']
        indexes = [
            models.Index(fields=['phone_number'], name='students_gdn_phone_idx'),
        ]

    def __str__(self):
        return self.full_name

    @classmethod
    def get_or_create_by_phone(cls, phone_number, full_name, **defaults):
        """
        Get existing guardian by phone or create new one.
        Prevents duplicates by using phone_number as unique identifier.
        """
        guardian, created = cls.objects.get_or_create(
            phone_number=phone_number,
            defaults={'full_name': full_name, **defaults}
        )
        return guardian, created


class StudentGuardian(models.Model):
    """
    Through model for Student-Guardian many-to-many relationship.
    Stores the relationship type and whether this is the primary guardian.
    """
    student = models.ForeignKey(
        'Student',
        on_delete=models.CASCADE,
        related_name='student_guardians'
    )
    guardian = models.ForeignKey(
        Guardian,
        on_delete=models.CASCADE,
        related_name='guardian_students'
    )
    relationship = models.CharField(
        _("relationship"),
        max_length=20,
        choices=Guardian.Relationship.choices,
        default=Guardian.Relationship.GUARDIAN
    )
    is_primary = models.BooleanField(
        _("primary guardian"),
        default=False,
        help_text=_("Is this the primary guardian/contact?")
    )
    is_emergency_contact = models.BooleanField(
        _("emergency contact"),
        default=True,
        help_text=_("Can be contacted in emergencies?")
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Student Guardian")
        verbose_name_plural = _("Student Guardians")
        unique_together = ['student', 'guardian']
        ordering = ['-is_primary', 'guardian__full_name']

    def __str__(self):
        return f"{self.guardian.full_name} ({self.get_relationship_display()}) - {self.student.full_name}"

    def save(self, *args, **kwargs):
        # If this is set as primary, unset other primary guardians for this student
        if self.is_primary:
            StudentGuardian.objects.filter(
                student=self.student,
                is_primary=True
            ).exclude(pk=self.pk).update(is_primary=False)
        super().save(*args, **kwargs)


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

    # Guardians (Many-to-Many through StudentGuardian)
    guardians = models.ManyToManyField(
        Guardian,
        through='StudentGuardian',
        related_name='wards',
        blank=True
    )

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

    # House
    house = models.ForeignKey(
        House,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='students',
        help_text="School house the student belongs to"
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
        indexes = [
            # Frequently filtered by status (active, graduated, etc.)
            models.Index(fields=['status']),
            # Frequently joined/filtered by current_class
            models.Index(fields=['current_class']),
            # Common filter: active students in a class
            models.Index(fields=['current_class', 'status']),
        ]

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

    def get_primary_guardian(self):
        """Return the primary guardian for this student."""
        sg = self.student_guardians.filter(is_primary=True).select_related('guardian').first()
        return sg.guardian if sg else None

    def get_guardians_with_relationships(self):
        """Return all guardians with their relationship info."""
        return self.student_guardians.select_related('guardian').all()

    def add_guardian(self, guardian, relationship, is_primary=False, is_emergency_contact=True):
        """Add a guardian to this student."""
        sg, created = StudentGuardian.objects.get_or_create(
            student=self,
            guardian=guardian,
            defaults={
                'relationship': relationship,
                'is_primary': is_primary,
                'is_emergency_contact': is_emergency_contact
            }
        )
        if not created:
            # Update existing relationship
            sg.relationship = relationship
            sg.is_primary = is_primary
            sg.is_emergency_contact = is_emergency_contact
            sg.save()
        return sg

    def remove_guardian(self, guardian):
        """Remove a guardian from this student."""
        return self.student_guardians.filter(guardian=guardian).delete()

    def save(self, *args, **kwargs):
        """Override save to resize photo if uploaded."""
        from io import BytesIO
        from django.core.files.base import ContentFile
        from PIL import Image

        PHOTO_MAX_SIZE = (150, 150)

        # Resize photo if it's a new upload
        if self.photo and hasattr(self.photo, 'file'):
            try:
                img = Image.open(self.photo)

                # Convert to RGB if necessary (for PNG with transparency)
                if img.mode in ('RGBA', 'P'):
                    img = img.convert('RGB')

                # Resize using thumbnail to maintain aspect ratio
                img.thumbnail(PHOTO_MAX_SIZE, Image.Resampling.LANCZOS)

                # Save to buffer as WebP (better compression)
                buffer = BytesIO()
                img.save(buffer, format='WEBP', quality=80, optimize=True)
                buffer.seek(0)

                # Generate filename with .webp extension
                filename = self.photo.name.rsplit('.', 1)[0] + '.webp'
                if '/' in filename:
                    filename = filename.rsplit('/', 1)[-1]

                # Replace the photo with resized version
                self.photo.save(filename, ContentFile(buffer.read()), save=False)
            except Exception:
                # If image processing fails, continue with original
                pass

        super().save(*args, **kwargs)


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
        indexes = [
            # Frequently filtered by academic year
            models.Index(fields=['academic_year']),
            # Frequently filtered by status
            models.Index(fields=['status']),
            # Common query: active enrollments for a year
            models.Index(fields=['academic_year', 'status']),
            # Lookup enrollments by class
            models.Index(fields=['class_assigned']),
        ]

    def __str__(self):
        return f"{self.student.full_name} - {self.class_assigned.name} ({self.academic_year})"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
