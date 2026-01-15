import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from core.models import Person  # Importing your abstract model
from core.choices import PersonTitle as Title


class Teacher(Person):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Status(models.TextChoices):
        ACTIVE = 'active', _('Active')
        INACTIVE = 'inactive', _('Inactive')
        PENDING = 'pending', _('Pending')

    # Link to User account
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='teacher_profile',
        help_text="Associated user account for login"
    )

    # Specific Teacher Fields
    title = models.CharField(
        max_length=10,
        choices=Title.choices,
        default=Title.MR
    )
    staff_id = models.CharField(max_length=20, unique=True, help_text="Unique Employee ID")
    subject_specialization = models.CharField(max_length=100, help_text="e.g. Mathematics, Science")
    employment_date = models.DateField(default=timezone.now)
    status = models.CharField(
        max_length=10, 
        choices=Status.choices, 
        default=Status.ACTIVE
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['status'], name='teachers_status_idx'),
        ]

    @property
    def full_name(self):
        parts = [self.first_name, self.middle_name, self.last_name]
        return " ".join(filter(None, parts))

    def __str__(self):
        return f"{self.get_title_display()} {self.full_name}"


class TeacherInvitation(models.Model):
    """
    Secure invitation tokens for teacher account creation.
    Teachers receive an email with a link to set their own password.
    """

    class Status(models.TextChoices):
        PENDING = 'pending', _('Pending')
        ACCEPTED = 'accepted', _('Accepted')
        EXPIRED = 'expired', _('Expired')
        CANCELLED = 'cancelled', _('Cancelled')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    teacher = models.ForeignKey(
        Teacher,
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
        related_name='sent_teacher_invitations'
    )
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['token'], name='teacher_inv_token_idx'),
            models.Index(fields=['status'], name='teacher_inv_status_idx'),
        ]

    def __str__(self):
        return f"Invitation for {self.teacher.full_name} ({self.status})"

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
    def create_for_teacher(cls, teacher, email, created_by=None, expires_hours=72):
        """
        Create a new invitation for a teacher.
        Cancels any existing pending invitations.
        """
        # Cancel existing pending invitations
        cls.objects.filter(
            teacher=teacher,
            status=cls.Status.PENDING
        ).update(status=cls.Status.CANCELLED)

        # Create new invitation
        return cls.objects.create(
            teacher=teacher,
            email=email,
            created_by=created_by,
            expires_at=timezone.now() + timedelta(hours=expires_hours)
        )

    @classmethod
    def get_by_token(cls, token):
        """Get a valid invitation by token, or None if not found/invalid."""
        try:
            invitation = cls.objects.select_related('teacher').get(token=token)
            # Auto-expire if past expiry date
            if invitation.status == cls.Status.PENDING and invitation.is_expired:
                invitation.mark_expired()
                return None
            return invitation if invitation.is_valid else None
        except cls.DoesNotExist:
            return None