import uuid

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

    @property
    def full_name(self):
        parts = [self.first_name, self.middle_name, self.last_name]
        return " ".join(filter(None, parts))

    def __str__(self):
        return f"{self.get_title_display()} {self.full_name}"