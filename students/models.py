import secrets
import uuid
from datetime import timedelta

from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.utils import timezone


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

    # Link to User account for portal access
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='guardian_profile',
        help_text="Associated user account for guardian portal login"
    )

    # Personal Information
    full_name = models.CharField(_("full name"), max_length=255)
    phone_number = models.CharField(_("phone number"), max_length=20, unique=True)
    email = models.EmailField(_("email address"), blank=True, null=True)
    occupation = models.CharField(_("occupation"), max_length=100, blank=True)
    address = models.TextField(_("address"), blank=True)

    # Notification Preferences
    email_notifications = models.BooleanField(_("email notifications"), default=True)
    sms_notifications = models.BooleanField(_("SMS notifications"), default=True)
    academic_alerts = models.BooleanField(_("academic alerts"), default=True)
    attendance_alerts = models.BooleanField(_("attendance alerts"), default=True)
    fee_alerts = models.BooleanField(_("fee alerts"), default=True)
    announcement_alerts = models.BooleanField(_("announcement alerts"), default=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Guardian")
        verbose_name_plural = _("Guardians")
        ordering = ['full_name']
        indexes = [
            models.Index(fields=['phone_number'], name='students_gdn_phone_idx'),
            models.Index(fields=['email'], name='guardian_email_idx'),
            models.Index(fields=['user'], name='guardian_user_idx'),
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
        indexes = [
            models.Index(fields=['student', 'is_primary'], name='sg_student_primary_idx'),
            models.Index(fields=['guardian'], name='sg_guardian_idx'),
        ]

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
            # Common filter: is_active flag
            models.Index(fields=['is_active']),
            # Compound index for active students queries
            models.Index(fields=['is_active', 'status']),
            # Admission number lookups
            models.Index(fields=['admission_number']),
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
        """Return the primary guardian for this student. Caches result to avoid repeated queries."""
        # Use cached value if available (set by prefetch or previous call)
        if hasattr(self, '_cached_primary_guardian'):
            return self._cached_primary_guardian

        sg = self.student_guardians.filter(is_primary=True).select_related('guardian').first()
        self._cached_primary_guardian = sg.guardian if sg else None
        return self._cached_primary_guardian

    @property
    def guardian_name(self):
        """Backward compatible property for primary guardian's name."""
        guardian = self.get_primary_guardian()
        return guardian.full_name if guardian else None

    @property
    def guardian_phone(self):
        """Backward compatible property for primary guardian's phone."""
        guardian = self.get_primary_guardian()
        return guardian.phone_number if guardian else None

    @property
    def guardian_email(self):
        """Backward compatible property for primary guardian's email."""
        guardian = self.get_primary_guardian()
        return guardian.email if guardian else None

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
        """Override save to resize and validate photo if uploaded."""
        import logging
        from io import BytesIO
        from django.core.files.base import ContentFile
        from django.core.exceptions import ValidationError
        from PIL import Image, UnidentifiedImageError

        logger = logging.getLogger(__name__)
        PHOTO_MAX_SIZE = (150, 150)
        ALLOWED_IMAGE_TYPES = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}
        MAX_PHOTO_SIZE = 5 * 1024 * 1024  # 5MB

        # Validate and resize photo if it's a new upload
        if self.photo and hasattr(self.photo, 'file'):
            # Validate file size
            if hasattr(self.photo, 'size') and self.photo.size > MAX_PHOTO_SIZE:
                logger.warning("Student photo rejected: size exceeds limit")
                raise ValidationError("Photo size must be less than 5MB")

            # Validate content type if available
            content_type = getattr(self.photo, 'content_type', None)
            if content_type and content_type not in ALLOWED_IMAGE_TYPES:
                logger.warning(f"Student photo rejected: invalid type {content_type}")
                raise ValidationError("Invalid image type. Allowed: JPEG, PNG, GIF, WebP")

            try:
                img = Image.open(self.photo)

                # Validate it's actually an image
                if img.format and img.format.upper() not in ('JPEG', 'PNG', 'GIF', 'WEBP', 'JPG'):
                    raise ValidationError("Unsupported image format")

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
            except UnidentifiedImageError:
                logger.warning("Could not process student photo: unidentified format")
                raise ValidationError("Invalid image file. Please upload a valid image.")
            except (IOError, OSError) as e:
                logger.warning(f"Student photo processing failed: {e}")
                raise ValidationError(f"Failed to process photo: {e}")

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


class GuardianInvitation(models.Model):
    """
    Secure invitation tokens for guardian portal account creation.
    Guardians receive an email with a link to set their own password.
    """

    class Status(models.TextChoices):
        PENDING = 'pending', _('Pending')
        ACCEPTED = 'accepted', _('Accepted')
        EXPIRED = 'expired', _('Expired')
        CANCELLED = 'cancelled', _('Cancelled')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    guardian = models.ForeignKey(
        Guardian,
        on_delete=models.CASCADE,
        related_name='invitations'
    )
    token = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        help_text="Secure token for invitation link"
    )
    email = models.EmailField(help_text="Email address invitation was sent to")
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING
    )
    expires_at = models.DateTimeField(help_text="When this invitation expires")

    # Tracking
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='sent_guardian_invitations'
    )
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['token'], name='guardian_inv_token_idx'),
            models.Index(fields=['status'], name='guardian_inv_status_idx'),
            models.Index(fields=['guardian'], name='guardian_inv_guardian_idx'),
            models.Index(fields=['guardian', 'status'], name='guardian_inv_gdn_status_idx'),
            models.Index(fields=['email'], name='guardian_inv_email_idx'),
        ]

    def __str__(self):
        return f"Invitation for {self.guardian.full_name} ({self.status})"

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = self.generate_token()
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(hours=72)  # 3 days default
        super().save(*args, **kwargs)

    @staticmethod
    def generate_token():
        """Generate a cryptographically secure token."""
        return secrets.token_urlsafe(48)

    @property
    def is_valid(self):
        """Check if invitation is still valid (pending and not expired)."""
        return (
            self.status == self.Status.PENDING and
            self.expires_at > timezone.now()
        )

    @property
    def is_expired(self):
        """Check if invitation has expired."""
        return self.expires_at <= timezone.now()

    def mark_accepted(self):
        """Mark invitation as accepted."""
        self.status = self.Status.ACCEPTED
        self.accepted_at = timezone.now()
        self.save(update_fields=['status', 'accepted_at'])

    def mark_expired(self):
        """Mark invitation as expired."""
        self.status = self.Status.EXPIRED
        self.save(update_fields=['status'])

    def cancel(self):
        """Cancel this invitation."""
        self.status = self.Status.CANCELLED
        self.save(update_fields=['status'])

    @classmethod
    def create_for_guardian(cls, guardian, email, created_by=None, expires_hours=72):
        """
        Create a new invitation for a guardian.
        Cancels any existing pending invitations.
        """
        # Cancel existing pending invitations
        cls.objects.filter(
            guardian=guardian,
            status=cls.Status.PENDING
        ).update(status=cls.Status.CANCELLED)

        # Create new invitation
        return cls.objects.create(
            guardian=guardian,
            email=email,
            created_by=created_by,
            expires_at=timezone.now() + timedelta(hours=expires_hours)
        )

    @classmethod
    def get_by_token(cls, token):
        """Get a valid invitation by token, or None if not found/invalid."""
        try:
            invitation = cls.objects.select_related('guardian').get(token=token)
            # Auto-expire if past expiry date
            if invitation.status == cls.Status.PENDING and invitation.is_expired:
                invitation.mark_expired()
                return None
            return invitation if invitation.is_valid else None
        except cls.DoesNotExist:
            return None


class HouseMaster(models.Model):
    """
    Assigns a teacher as housemaster for a house in a specific academic year.
    One teacher can be marked as Senior Housemaster (Discipline Master) per year.
    """
    teacher = models.ForeignKey(
        'teachers.Teacher',
        on_delete=models.CASCADE,
        related_name='housemaster_assignments'
    )
    house = models.ForeignKey(
        House,
        on_delete=models.CASCADE,
        related_name='housemaster_assignments'
    )
    academic_year = models.ForeignKey(
        'core.AcademicYear',
        on_delete=models.CASCADE,
        related_name='housemaster_assignments'
    )
    is_senior = models.BooleanField(
        default=False,
        help_text="Senior Housemaster (Discipline Master) - approves external exeats"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-academic_year__start_date', 'house__name']
        unique_together = ['house', 'academic_year']  # One housemaster per house per year
        verbose_name = "House Master"
        verbose_name_plural = "House Masters"

    def __str__(self):
        senior = " (Senior)" if self.is_senior else ""
        return f"{self.teacher.full_name} - {self.house.name}{senior} ({self.academic_year})"

    @classmethod
    def get_senior_housemaster(cls, academic_year=None):
        """Get the senior housemaster for the given or current academic year."""
        from core.models import AcademicYear
        if not academic_year:
            academic_year = AcademicYear.get_current()
        if not academic_year:
            return None
        return cls.objects.filter(
            academic_year=academic_year,
            is_senior=True,
            is_active=True
        ).select_related('teacher').first()

    @classmethod
    def get_for_house(cls, house, academic_year=None):
        """Get the housemaster for a specific house."""
        from core.models import AcademicYear
        if not academic_year:
            academic_year = AcademicYear.get_current()
        if not academic_year:
            return None
        return cls.objects.filter(
            house=house,
            academic_year=academic_year,
            is_active=True
        ).select_related('teacher').first()


class Exeat(models.Model):
    """
    Tracks student exeat (permission to leave campus) requests.
    Internal exeats are approved by housemaster.
    External exeats require housemaster recommendation + senior housemaster approval.
    """
    class ExeatType(models.TextChoices):
        INTERNAL = 'internal', _('Internal (Within town, same day return)')
        EXTERNAL = 'external', _('External (Outside school location)')

    class Status(models.TextChoices):
        PENDING = 'pending', _('Pending')
        RECOMMENDED = 'recommended', _('Recommended')  # For external - awaiting senior approval
        APPROVED = 'approved', _('Approved')
        REJECTED = 'rejected', _('Rejected')
        ACTIVE = 'active', _('Active (Student out)')
        COMPLETED = 'completed', _('Completed (Returned)')
        OVERDUE = 'overdue', _('Overdue')
        CANCELLED = 'cancelled', _('Cancelled')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='exeats'
    )
    exeat_type = models.CharField(
        max_length=10,
        choices=ExeatType.choices,
        default=ExeatType.INTERNAL
    )
    reason = models.TextField(help_text="Reason for the exeat request")
    destination = models.CharField(max_length=255, help_text="Where the student is going")

    # Departure details
    departure_date = models.DateField()
    departure_time = models.TimeField()
    expected_return_date = models.DateField()
    expected_return_time = models.TimeField()

    # Actual departure/return (filled when student departs/returns)
    actual_departure = models.DateTimeField(null=True, blank=True)
    actual_return = models.DateTimeField(null=True, blank=True)

    # Contact information (for emergency)
    contact_phone = models.CharField(max_length=20, blank=True, help_text="Emergency contact phone")
    contact_person = models.CharField(max_length=100, blank=True, help_text="Emergency contact person name")

    # Status tracking
    status = models.CharField(
        max_length=15,
        choices=Status.choices,
        default=Status.PENDING
    )

    # Request tracking
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='exeat_requests'
    )
    housemaster = models.ForeignKey(
        'teachers.Teacher',
        on_delete=models.SET_NULL,
        null=True,
        related_name='exeats_as_housemaster',
        help_text="The student's housemaster handling this request"
    )

    # Recommendation (for external exeats)
    recommended_by = models.ForeignKey(
        'teachers.Teacher',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='exeats_recommended',
        help_text="Housemaster who recommended (external exeats)"
    )
    recommended_at = models.DateTimeField(null=True, blank=True)

    # Approval
    approved_by = models.ForeignKey(
        'teachers.Teacher',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='exeats_approved'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)

    # Notifications
    guardian_notified_approval = models.BooleanField(default=False)
    guardian_notified_return = models.BooleanField(default=False)
    guardian_notified_overdue = models.BooleanField(default=False)

    # SMS audit trail - links to actual SMS messages for tracking delivery
    approval_sms = models.ForeignKey(
        'communications.SMSMessage',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='exeat_approvals',
        help_text="SMS sent when exeat was approved"
    )
    return_sms = models.ForeignKey(
        'communications.SMSMessage',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='exeat_returns',
        help_text="SMS sent when student returned"
    )

    notes = models.TextField(blank=True, help_text="Additional notes")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Exeat"
        verbose_name_plural = "Exeats"
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['student', 'status']),
            models.Index(fields=['exeat_type', 'status']),
            models.Index(fields=['departure_date']),
        ]

    def __str__(self):
        return f"{self.student.full_name} - {self.get_exeat_type_display()} ({self.status})"

    @property
    def is_overdue(self):
        """Check if the exeat is overdue."""
        if self.status not in [self.Status.ACTIVE, self.Status.APPROVED]:
            return False
        from datetime import datetime
        expected = datetime.combine(self.expected_return_date, self.expected_return_time)
        return timezone.now() > timezone.make_aware(expected) if timezone.is_naive(expected) else timezone.now() > expected

    def mark_departed(self):
        """Mark student as departed."""
        if self.status == self.Status.APPROVED:
            self.actual_departure = timezone.now()
            self.status = self.Status.ACTIVE
            self.save(update_fields=['actual_departure', 'status', 'updated_at'])

    def mark_returned(self):
        """Mark student as returned."""
        self.actual_return = timezone.now()
        self.status = self.Status.COMPLETED
        self.save(update_fields=['actual_return', 'status', 'updated_at'])

    def recommend(self, teacher):
        """Housemaster recommends external exeat for senior approval."""
        self.recommended_by = teacher
        self.recommended_at = timezone.now()
        self.status = self.Status.RECOMMENDED
        self.save(update_fields=['recommended_by', 'recommended_at', 'status', 'updated_at'])

    def approve(self, teacher):
        """Approve the exeat."""
        self.approved_by = teacher
        self.approved_at = timezone.now()
        self.status = self.Status.APPROVED
        self.save(update_fields=['approved_by', 'approved_at', 'status', 'updated_at'])

    def reject(self, reason=''):
        """Reject the exeat."""
        self.status = self.Status.REJECTED
        self.rejection_reason = reason
        self.save(update_fields=['status', 'rejection_reason', 'updated_at'])
