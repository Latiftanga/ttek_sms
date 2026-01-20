import uuid
import secrets
import logging
from io import BytesIO
from django.conf import settings
from django.db import models, connection
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from PIL import Image, UnidentifiedImageError
import math
from encrypted_model_fields.fields import EncryptedCharField
from .choices import Gender

logger = logging.getLogger(__name__)


# Maximum image dimensions
PHOTO_MAX_SIZE = (128, 128)  # For student/teacher profile photos
LOGO_MAX_SIZE = (128, 128)   # For school logos
FAVICON_MAX_SIZE = (64, 64)  # For favicons (typically smaller)

# Allowed image types for photo uploads
ALLOWED_IMAGE_TYPES = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}
MAX_PHOTO_SIZE = 5 * 1024 * 1024  # 5MB

class Person(models.Model):
    """
    Abstract Person model. 
    Removes 'title' so it doesn't force it upon Students.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    middle_name = models.CharField(max_length=50, blank=True, default='')
    
    gender = models.CharField(
        max_length=1, 
        choices=Gender.choices,
        default=Gender.MALE
    )
    date_of_birth = models.DateField()
    photo = models.ImageField(upload_to='photos/', blank=True, null=True)

    # Contact & IDs
    phone_number = models.CharField(max_length=17, blank=True)
    address = models.TextField(blank=True, default='')
    email = models.EmailField(blank=True, null=True)
    
    nationality = models.CharField(max_length=50, default='Ghanaian')

    class Meta:
        abstract = True

    def __str__(self):
        parts = [self.first_name, self.middle_name, self.last_name]
        return " ".join(filter(None, parts))

    def save(self, *args, **kwargs):
        from django.core.exceptions import ValidationError

        # Resize photo if it's a new upload (has file attribute)
        if self.photo and hasattr(self.photo, 'file'):
            # Validate file size
            if hasattr(self.photo, 'size') and self.photo.size > MAX_PHOTO_SIZE:
                logger.warning(f"Photo upload rejected: size {self.photo.size} exceeds limit")
                raise ValidationError(f"Photo size must be less than {MAX_PHOTO_SIZE // (1024*1024)}MB")

            # Validate content type if available
            content_type = getattr(self.photo, 'content_type', None)
            if content_type and content_type not in ALLOWED_IMAGE_TYPES:
                logger.warning(f"Photo upload rejected: invalid type {content_type}")
                raise ValidationError(f"Invalid image type. Allowed: JPEG, PNG, GIF, WebP")

            try:
                img = Image.open(self.photo)

                # Validate it's actually an image by checking format
                if img.format and img.format.upper() not in ('JPEG', 'PNG', 'GIF', 'WEBP', 'JPG'):
                    logger.warning(f"Photo rejected: unsupported format {img.format}")
                    raise ValidationError("Unsupported image format")

                # Convert to RGB if necessary (for PNG with transparency)
                if img.mode in ('RGBA', 'P'):
                    img = img.convert('RGB')

                # Resize using thumbnail to maintain aspect ratio
                img.thumbnail(PHOTO_MAX_SIZE, Image.Resampling.LANCZOS)

                # Save to buffer as WebP (better compression than JPEG)
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
                # Invalid image file - reject the upload
                logger.warning(f"Could not process uploaded image: unidentified format")
                raise ValidationError("Invalid image file. Please upload a valid image.")
            except (IOError, OSError) as e:
                # File I/O errors - log and continue with original
                logger.warning(f"Image processing failed: {e}")

        super().save(*args, **kwargs)


def hex_to_oklch_values(hex_color):
    """
    Convert hex color to OKLCH values string for CSS.
    Returns format: "L% C H" (e.g., "54% 0.2 260")
    """
    # Remove # if present
    hex_color = hex_color.lstrip('#')

    # Convert hex to RGB (0-1 range)
    r = int(hex_color[0:2], 16) / 255
    g = int(hex_color[2:4], 16) / 255
    b = int(hex_color[4:6], 16) / 255

    # Convert RGB to linear RGB
    def to_linear(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r_lin = to_linear(r)
    g_lin = to_linear(g)
    b_lin = to_linear(b)

    # Convert to XYZ (D65)
    x = 0.4124564 * r_lin + 0.3575761 * g_lin + 0.1804375 * b_lin
    y = 0.2126729 * r_lin + 0.7151522 * g_lin + 0.0721750 * b_lin
    z = 0.0193339 * r_lin + 0.1191920 * g_lin + 0.9503041 * b_lin

    # Convert XYZ to OKLab
    l_ = 0.8189330101 * x + 0.3618667424 * y - 0.1288597137 * z
    m_ = 0.0329845436 * x + 0.9293118715 * y + 0.0361456387 * z
    s_ = 0.0482003018 * x + 0.2643662691 * y + 0.6338517070 * z

    l_ = l_ ** (1/3) if l_ >= 0 else -((-l_) ** (1/3))
    m_ = m_ ** (1/3) if m_ >= 0 else -((-m_) ** (1/3))
    s_ = s_ ** (1/3) if s_ >= 0 else -((-s_) ** (1/3))

    L = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
    a = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    b_val = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_

    # Convert OKLab to OKLCH
    C = math.sqrt(a * a + b_val * b_val)
    H = math.degrees(math.atan2(b_val, a))
    if H < 0:
        H += 360

    # Format for CSS: "L% C H"
    L_percent = round(L * 100)
    C_rounded = round(C, 3)
    H_rounded = round(H)

    return f"{L_percent}% {C_rounded} {H_rounded}"


class AcademicYear(models.Model):
    """
    Represents an academic year (e.g., 2024/2025).
    Each tenant has their own academic years.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(
        max_length=50,
        help_text="e.g., 2024/2025 Academic Year"
    )
    start_date = models.DateField()
    end_date = models.DateField()
    is_current = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Only one academic year can be current at a time"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-start_date']
        verbose_name = "Academic Year"
        verbose_name_plural = "Academic Years"

    def __str__(self):
        return self.name

    def clean(self):
        """Validate academic year data."""
        from django.core.exceptions import ValidationError

        if self.start_date and self.end_date:
            if self.start_date >= self.end_date:
                raise ValidationError({
                    'end_date': 'End date must be after start date.'
                })
            # Check for reasonable date range (max 2 years)
            from datetime import timedelta
            if (self.end_date - self.start_date) > timedelta(days=730):
                raise ValidationError({
                    'end_date': 'Academic year cannot span more than 2 years.'
                })

    def save(self, *args, **kwargs):
        self.full_clean()  # Run validation before saving
        # Ensure only one academic year is current
        if self.is_current:
            AcademicYear.objects.filter(is_current=True).exclude(pk=self.pk).update(is_current=False)
        super().save(*args, **kwargs)
        # Invalidate cache when academic year is saved
        cache_key = f'current_academic_year_{connection.schema_name}'
        cache.delete(cache_key)

    @classmethod
    def get_current(cls):
        """Get the current academic year with tenant-aware caching."""
        cache_key = f'current_academic_year_{connection.schema_name}'
        academic_year = cache.get(cache_key)
        if academic_year is None:
            academic_year = cls.objects.filter(is_current=True).first()
            if academic_year:
                cache.set(cache_key, academic_year, 60 * 60)  # Cache for 1 hour
        return academic_year


class Term(models.Model):
    """
    Represents a term/semester within an academic year.
    Generic model that works for both Terms (Primary) and Semesters (SHS).
    """
    PERIOD_NUMBER_CHOICES = [
        (1, 'First'),
        (2, 'Second'),
        (3, 'Third'),
        (4, 'Fourth'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name='terms'
    )
    name = models.CharField(
        max_length=50,
        help_text="e.g., First Term, Semester One"
    )
    term_number = models.PositiveSmallIntegerField(
        choices=PERIOD_NUMBER_CHOICES,
        default=1,
        verbose_name="Period Number"
    )
    start_date = models.DateField()
    end_date = models.DateField()
    is_current = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Only one term can be current at a time"
    )

    # Grade locking
    grades_locked = models.BooleanField(
        default=False,
        help_text="When locked, scores cannot be modified"
    )
    grades_locked_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When grades were locked"
    )
    grades_locked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='locked_terms',
        help_text="User who locked the grades"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['academic_year', 'term_number']
        verbose_name = "Term"
        verbose_name_plural = "Terms"
        unique_together = ['academic_year', 'term_number']

    def __str__(self):
        return f"{self.name} - {self.academic_year.name}"

    def clean(self):
        """Validate term data."""
        from django.core.exceptions import ValidationError

        if self.start_date and self.end_date:
            if self.start_date >= self.end_date:
                raise ValidationError({
                    'end_date': 'End date must be after start date.'
                })

        # Validate term dates are within academic year
        if self.academic_year and self.start_date and self.end_date:
            if self.start_date < self.academic_year.start_date:
                raise ValidationError({
                    'start_date': 'Term start date cannot be before academic year start.'
                })
            if self.end_date > self.academic_year.end_date:
                raise ValidationError({
                    'end_date': 'Term end date cannot be after academic year end.'
                })

    def save(self, *args, **kwargs):
        self.full_clean()  # Run validation before saving
        # Ensure only one term is current
        if self.is_current:
            Term.objects.filter(is_current=True).exclude(pk=self.pk).update(is_current=False)
        super().save(*args, **kwargs)
        # Invalidate cache when term is saved
        cache_key = f'current_term_{connection.schema_name}'
        cache.delete(cache_key)

    @classmethod
    def get_current(cls):
        """Get the current term with tenant-aware caching."""
        cache_key = f'current_term_{connection.schema_name}'
        term = cache.get(cache_key)
        if term is None:
            term = cls.objects.filter(is_current=True).select_related('academic_year').first()
            if term:
                cache.set(cache_key, term, 60 * 60)  # Cache for 1 hour
        return term

    def lock_grades(self, user):
        """Lock grades for this term."""
        from django.utils import timezone
        self.grades_locked = True
        self.grades_locked_at = timezone.now()
        self.grades_locked_by = user
        self.save(update_fields=['grades_locked', 'grades_locked_at', 'grades_locked_by'])

    def unlock_grades(self):
        """Unlock grades for this term."""
        self.grades_locked = False
        self.grades_locked_at = None
        self.grades_locked_by = None
        self.save(update_fields=['grades_locked', 'grades_locked_at', 'grades_locked_by'])


class SchoolSettings(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    """
    Stores configuration specific to this School (Tenant).
    """
    PERIOD_TYPE_CHOICES = [
        ('term', 'Terms (Basic)'),
        ('semester', 'Semesters (SHS)'),
    ]

    EDUCATION_SYSTEM_CHOICES = [
        ('basic', 'Basic Only (Creche - Basic 9)'),
        ('shs', 'SHS Only'),
        ('both', 'Both Basic and SHS'),
    ]

    # Branding
    logo = models.ImageField(upload_to='school_logos/', blank=True, null=True)
    favicon = models.ImageField(upload_to='school_favicons/', blank=True, null=True)
    display_name = models.CharField(max_length=50, blank=True)
    motto = models.CharField(max_length=200, blank=True)

    # Academic Settings
    academic_period_type = models.CharField(
        max_length=10,
        choices=PERIOD_TYPE_CHOICES,
        default='term',
        help_text="Terms for Basic, Semesters for SHS"
    )
    education_system = models.CharField(
        max_length=10,
        choices=EDUCATION_SYSTEM_CHOICES,
        default='both',
        help_text="Which educational levels this school supports"
    )

    # Visual Identity - Colors (stored as HEX)
    primary_color = models.CharField(max_length=7, default="#4F46E5", help_text="Main brand color")
    secondary_color = models.CharField(max_length=7, default="#7C3AED", help_text="Secondary brand color")
    accent_color = models.CharField(max_length=7, default="#F59E0B", help_text="Accent/highlight color")

    # OKLCH values (auto-generated, not editable)
    primary_color_oklch = models.CharField(max_length=50, blank=True, editable=False)
    secondary_color_oklch = models.CharField(max_length=50, blank=True, editable=False)
    accent_color_oklch = models.CharField(max_length=50, blank=True, editable=False)

    # SMS Configuration
    SMS_BACKEND_CHOICES = [
        ('console', 'Console (Development)'),
        ('arkesel', 'Arkesel'),
        ('hubtel', 'Hubtel'),
        ('africastalking', "Africa's Talking"),
    ]
    sms_backend = models.CharField(
        max_length=20,
        choices=SMS_BACKEND_CHOICES,
        default='console',
        help_text="SMS provider to use for sending messages"
    )
    sms_api_key = models.CharField(
        max_length=255,
        blank=True,
        help_text="Arkesel API key (get from https://sms.arkesel.com/user/sms-api/info)"
    )
    sms_sender_id = models.CharField(
        max_length=11,
        blank=True,
        help_text="Sender ID shown on SMS (max 11 characters)"
    )
    sms_enabled = models.BooleanField(
        default=False,
        help_text="Enable SMS messaging for this school"
    )

    # Email Configuration
    EMAIL_BACKEND_CHOICES = [
        ('console', 'Console (Development)'),
        ('smtp', 'SMTP'),
    ]
    email_backend = models.CharField(
        max_length=20,
        choices=EMAIL_BACKEND_CHOICES,
        default='console',
        help_text="Email provider to use"
    )
    email_enabled = models.BooleanField(
        default=False,
        help_text="Enable custom email settings for this school"
    )

    # SMTP Settings
    email_host = models.CharField(
        max_length=255,
        blank=True,
        help_text="SMTP server hostname (e.g., smtp.gmail.com)"
    )
    email_port = models.PositiveIntegerField(
        default=587,
        help_text="SMTP port (587 for TLS, 465 for SSL)"
    )
    email_use_tls = models.BooleanField(
        default=True,
        help_text="Use TLS encryption"
    )
    email_use_ssl = models.BooleanField(
        default=False,
        help_text="Use SSL encryption (mutually exclusive with TLS)"
    )
    email_host_user = models.CharField(
        max_length=255,
        blank=True,
        help_text="SMTP username/email"
    )
    email_host_password = EncryptedCharField(
        max_length=500,
        blank=True,
        help_text="SMTP password (encrypted)"
    )

    # From address
    email_from_address = models.EmailField(
        blank=True,
        help_text="Default 'From' email address"
    )
    email_from_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Display name for 'From' address"
    )

    # Setup wizard tracking
    setup_completed = models.BooleanField(
        default=False,
        help_text="Whether the initial setup wizard has been completed"
    )
    setup_completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When setup was completed"
    )

    @property
    def period_label(self):
        """Return 'Term' or 'Semester' based on setting."""
        return 'Semester' if self.academic_period_type == 'semester' else 'Term'

    @property
    def period_label_plural(self):
        """Return 'Terms' or 'Semesters' based on setting."""
        return 'Semesters' if self.academic_period_type == 'semester' else 'Terms'

    def get_allowed_level_types(self):
        """
        Return list of allowed level types based on tenant's education_system.
        Delegates to the School (tenant) model for the actual configuration.
        Returns tuples of (value, display_name) matching Class.LevelType choices.
        """
        from django.db import connection
        from schools.models import School

        try:
            tenant = School.objects.get(schema_name=connection.schema_name)
            return tenant.get_allowed_level_types()
        except School.DoesNotExist:
            # Fallback to 'both' if tenant not found
            return [
                ('creche', 'Creche'),
                ('nursery', 'Nursery'),
                ('kg', 'Kindergarten'),
                ('basic', 'Basic'),
                ('shs', 'SHS'),
            ]

    @property
    def education_system_display(self):
        """Return the display name for the education system from tenant."""
        from django.db import connection
        from schools.models import School

        try:
            tenant = School.objects.get(schema_name=connection.schema_name)
            return tenant.education_system_display
        except School.DoesNotExist:
            return 'Both Basic and SHS'

    @property
    def has_houses(self):
        """Check if school has houses support. Delegates to tenant."""
        from django.db import connection
        from schools.models import School

        try:
            tenant = School.objects.get(schema_name=connection.schema_name)
            return tenant.has_houses
        except School.DoesNotExist:
            return True  # Default to True if tenant not found

    @property
    def has_programmes(self):
        """Check if school has programmes support. Delegates to tenant."""
        from django.db import connection
        from schools.models import School

        try:
            tenant = School.objects.get(schema_name=connection.schema_name)
            return tenant.has_programmes
        except School.DoesNotExist:
            return True  # Default to True if tenant not found

    def _resize_image(self, image_field, max_size, preserve_transparency=False):
        """Resize an image field to max dimensions, converting to WebP."""
        if not image_field or not hasattr(image_field, 'file'):
            return

        try:
            img = Image.open(image_field)

            # Handle RGBA/transparency for logos/favicons
            if img.mode in ('RGBA', 'LA', 'P'):
                if preserve_transparency:
                    # Keep as PNG for transparency
                    img.thumbnail(max_size, Image.Resampling.LANCZOS)
                    buffer = BytesIO()
                    img.save(buffer, format='PNG', optimize=True)
                    buffer.seek(0)
                    filename = image_field.name.rsplit('.', 1)[0] + '.png'
                    image_field.save(filename, ContentFile(buffer.read()), save=False)
                    return
                else:
                    img = img.convert('RGB')

            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            buffer = BytesIO()
            img.save(buffer, format='WEBP', quality=85, optimize=True)
            buffer.seek(0)
            filename = image_field.name.rsplit('.', 1)[0] + '.webp'
            image_field.save(filename, ContentFile(buffer.read()), save=False)
        except (UnidentifiedImageError, Exception) as e:
            logger.warning(f"Could not process image: {e}")

    def save(self, *args, **kwargs):
        self.pk = 1

        # Resize logo and favicon if uploaded
        self._resize_image(self.logo, LOGO_MAX_SIZE, preserve_transparency=True)
        self._resize_image(self.favicon, FAVICON_MAX_SIZE, preserve_transparency=True)

        # Convert HEX colors to OKLCH for DaisyUI theming
        if self.primary_color:
            self.primary_color_oklch = hex_to_oklch_values(self.primary_color)
        if self.secondary_color:
            self.secondary_color_oklch = hex_to_oklch_values(self.secondary_color)
        if self.accent_color:
            self.accent_color_oklch = hex_to_oklch_values(self.accent_color)
        super().save(*args, **kwargs)
        # Clear tenant-specific cache
        cache_key = f'school_settings_{connection.schema_name}'
        cache.delete(cache_key)

    @classmethod
    def load(cls):
        """
        Load or create the singleton SchoolSettings instance.
        Uses tenant-specific cache key to prevent cross-tenant data leakage.
        """
        # Use tenant-specific cache key to isolate settings per schema
        cache_key = f'school_settings_{connection.schema_name}'
        profile = cache.get(cache_key)

        if profile is None:
            # Get first settings object or create one (singleton pattern)
            profile = cls.objects.first()
            if profile is None:
                profile = cls.objects.create()
            cache.set(cache_key, profile, 60 * 60 * 24)  # Cache for 24 hours

        return profile

    class Meta:
        verbose_name = "School Settings"
        verbose_name_plural = "School Settings"

    def __str__(self):
        return "School Profile & Settings"


def generate_verification_code():
    """Generate a unique 12-character verification code."""
    return secrets.token_urlsafe(9)[:12].upper()


class DocumentVerification(models.Model):
    """
    Stores verification records for generated PDF documents.
    Allows external parties to verify document authenticity.
    """
    class DocumentType(models.TextChoices):
        REPORT_CARD = 'report_card', _('Report Card')
        TRANSCRIPT = 'transcript', _('Transcript')
        STUDENT_PROFILE = 'student_profile', _('Student Profile')
        STAFF_PROFILE = 'staff_profile', _('Staff Profile')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    verification_code = models.CharField(
        max_length=12,
        unique=True,
        default=generate_verification_code,
        db_index=True,
        help_text="Unique code for document verification"
    )
    document_type = models.CharField(
        max_length=20,
        choices=DocumentType.choices,
    )

    # Document metadata
    student_name = models.CharField(max_length=200)
    student_admission_number = models.CharField(max_length=50)
    document_title = models.CharField(
        max_length=200,
        help_text="e.g., 'Report Card - Term 1 2024/2025'"
    )

    # Optional references (stored as strings for flexibility)
    student_id = models.CharField(max_length=50, blank=True)
    term_id = models.CharField(max_length=50, blank=True)
    academic_year = models.CharField(max_length=100, blank=True)

    # Timestamps
    generated_at = models.DateTimeField(default=timezone.now)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='generated_documents'
    )

    # Verification tracking
    verification_count = models.PositiveIntegerField(default=0)
    last_verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-generated_at']
        verbose_name = "Document Verification"
        verbose_name_plural = "Document Verifications"
        indexes = [
            models.Index(fields=['verification_code']),
            models.Index(fields=['student_admission_number']),
            models.Index(fields=['document_type', 'generated_at']),
        ]

    def __str__(self):
        return f"{self.verification_code} - {self.document_title}"

    def record_verification(self):
        """Record that this document was verified."""
        self.verification_count += 1
        self.last_verified_at = timezone.now()
        self.save(update_fields=['verification_count', 'last_verified_at'])

    @classmethod
    def create_for_document(cls, document_type, title, user=None, term=None, academic_year=None,
                            student=None, teacher=None):
        """
        Create a verification record for a document.

        Args:
            document_type: One of DocumentType choices
            title: Document title string
            user: User who generated the document (optional)
            term: Term model instance (optional)
            academic_year: Academic year string (optional)
            student: Student model instance (optional)
            teacher: Teacher model instance (optional)

        Returns:
            DocumentVerification instance
        """
        # Handle both student and teacher documents
        if student:
            person_name = student.full_name
            person_id_number = student.admission_number
            person_pk = str(student.pk)
        elif teacher:
            person_name = teacher.full_name
            person_id_number = teacher.staff_id
            person_pk = str(teacher.pk)
        else:
            raise ValueError("Either student or teacher must be provided")

        return cls.objects.create(
            document_type=document_type,
            student_name=person_name,  # Using same field for both (name field)
            student_admission_number=person_id_number,  # Using same field for both (ID number field)
            document_title=title,
            student_id=person_pk,  # Using same field for both (PK reference)
            term_id=str(term.pk) if term else '',
            academic_year=academic_year or '',
            generated_by=user,
        )


class Notification(models.Model):
    """
    User notifications for various system events.
    """
    class NotificationType(models.TextChoices):
        INFO = 'info', 'Information'
        SUCCESS = 'success', 'Success'
        WARNING = 'warning', 'Warning'
        ERROR = 'error', 'Error'

    class Category(models.TextChoices):
        SYSTEM = 'system', 'System'
        ACADEMIC = 'academic', 'Academic'
        ATTENDANCE = 'attendance', 'Attendance'
        FINANCE = 'finance', 'Finance'
        STUDENT = 'student', 'Student'
        TEACHER = 'teacher', 'Teacher'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    notification_type = models.CharField(
        max_length=20,
        choices=NotificationType.choices,
        default=NotificationType.INFO
    )
    category = models.CharField(
        max_length=20,
        choices=Category.choices,
        default=Category.SYSTEM
    )
    icon = models.CharField(max_length=50, blank=True, default='')
    link = models.CharField(max_length=255, blank=True, default='')
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read']),
            models.Index(fields=['user', '-created_at']),
        ]

    def __str__(self):
        return f"{self.title} - {self.user}"

    def mark_as_read(self):
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])

    @classmethod
    def create_notification(cls, user, title, message, notification_type='info',
                           category='system', icon='', link=''):
        """Create a notification for a user."""
        return cls.objects.create(
            user=user,
            title=title,
            message=message,
            notification_type=notification_type,
            category=category,
            icon=icon,
            link=link,
        )

    @classmethod
    def notify_admins(cls, title, message, notification_type='info', category='system', icon='', link=''):
        """Send notification to all school admins."""
        from accounts.models import User
        admins = User.objects.filter(
            models.Q(is_superuser=True) | models.Q(is_school_admin=True)
        )
        notifications = []
        for admin in admins:
            notifications.append(cls(
                user=admin,
                title=title,
                message=message,
                notification_type=notification_type,
                category=category,
                icon=icon,
                link=link,
            ))
        return cls.objects.bulk_create(notifications)

    @classmethod
    def unread_count(cls, user):
        """Get unread notification count for a user."""
        return cls.objects.filter(user=user, is_read=False).count()
