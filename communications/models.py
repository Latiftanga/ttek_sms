import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class SMSMessage(models.Model):
    """Log of all SMS messages sent."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SENT = 'sent', 'Sent'
        FAILED = 'failed', 'Failed'
        DELIVERED = 'delivered', 'Delivered'

    class MessageType(models.TextChoices):
        GENERAL = 'general', 'General'
        ATTENDANCE = 'attendance', 'Attendance Alert'
        FEE_REMINDER = 'fee', 'Fee Reminder'
        ANNOUNCEMENT = 'announcement', 'Announcement'
        REPORT_FEEDBACK = 'report', 'Report Feedback'
        EXEAT = 'exeat', 'Exeat Notification'
        STAFF = 'staff', 'Staff Message'

    recipient_phone = models.CharField(max_length=20)
    recipient_name = models.CharField(max_length=100, blank=True)
    student = models.ForeignKey(
        'students.Student',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sms_messages'
    )
    message = models.TextField()
    message_type = models.CharField(
        max_length=20,
        choices=MessageType.choices,
        default=MessageType.GENERAL
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )
    provider_response = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='sent_sms'
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'SMS Message'
        verbose_name_plural = 'SMS Messages'
        indexes = [
            # Dashboard stats queries filter by date and status
            models.Index(fields=['created_at']),
            models.Index(fields=['status']),
            models.Index(fields=['created_at', 'status']),
            # Message history filters by type
            models.Index(fields=['message_type']),
            # Lookup by recipient phone
            models.Index(fields=['recipient_phone']),
        ]

    def __str__(self):
        return f"SMS to {self.recipient_phone} - {self.get_status_display()}"

    def mark_sent(self, response=''):
        self.status = self.Status.SENT
        self.sent_at = timezone.now()
        self.provider_response = str(response)
        self.save(update_fields=['status', 'sent_at', 'provider_response'])

    def mark_failed(self, error=''):
        self.status = self.Status.FAILED
        self.error_message = str(error)
        self.save(update_fields=['status', 'error_message'])


class SMSTemplate(models.Model):
    """Reusable SMS templates."""

    name = models.CharField(max_length=100)
    message_type = models.CharField(
        max_length=20,
        choices=SMSMessage.MessageType.choices,
        default=SMSMessage.MessageType.GENERAL
    )
    content = models.TextField(
        help_text="Placeholders: {student_name}, {class_name}, {school_name}, {date}, "
                  "{position}, {average}, {conduct}, {attendance}, {term}, {remark}"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        indexes = [
            # Finding active templates by type
            models.Index(fields=['message_type', 'is_active']),
        ]

    def __str__(self):
        return self.name

    def render(self, context):
        """Render template with context variables."""
        message = self.content
        for key, value in context.items():
            message = message.replace(f'{{{key}}}', str(value))
        return message


class EmailMessage(models.Model):
    """Log of all email messages sent."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SENT = 'sent', 'Sent'
        FAILED = 'failed', 'Failed'

    class MessageType(models.TextChoices):
        GENERAL = 'general', 'General'
        STAFF = 'staff', 'Staff Message'
        ANNOUNCEMENT = 'announcement', 'Announcement'

    recipient_email = models.EmailField()
    recipient_name = models.CharField(max_length=100, blank=True)
    teacher = models.ForeignKey(
        'teachers.Teacher',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='email_messages'
    )
    subject = models.CharField(max_length=255)
    message = models.TextField()
    message_type = models.CharField(
        max_length=20,
        choices=MessageType.choices,
        default=MessageType.GENERAL
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )
    error_message = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='sent_emails'
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Email Message'
        verbose_name_plural = 'Email Messages'
        indexes = [
            models.Index(fields=['created_at']),
            models.Index(fields=['status']),
            models.Index(fields=['created_at', 'status']),
            models.Index(fields=['message_type']),
        ]

    def __str__(self):
        return f"Email to {self.recipient_email} - {self.get_status_display()}"

    def mark_sent(self):
        self.status = self.Status.SENT
        self.sent_at = timezone.now()
        self.save(update_fields=['status', 'sent_at'])

    def mark_failed(self, error=''):
        self.status = self.Status.FAILED
        self.error_message = str(error)
        self.save(update_fields=['status', 'error_message'])


class Announcement(models.Model):
    """Announcements with optional SMS/Email push to staff, parents, or students."""

    class TargetGroup(models.TextChoices):
        ALL = 'all', 'All Staff'
        TEACHING = 'teaching', 'Teaching Staff'
        NON_TEACHING = 'non_teaching', 'Non-Teaching Staff'

    class Audience(models.TextChoices):
        STAFF = 'staff', 'Staff'
        PARENTS = 'parents', 'Parents'
        STUDENTS = 'students', 'Students'

    class Scope(models.TextChoices):
        ALL = 'all', 'All'
        TEACHING = 'teaching', 'Teaching Staff'
        NON_TEACHING = 'non_teaching', 'Non-Teaching Staff'
        LEVEL = 'level', 'By Level'
        CLASS = 'class', 'By Class'
        INDIVIDUAL = 'individual', 'Individual'

    class Priority(models.TextChoices):
        NORMAL = 'normal', 'Normal'
        URGENT = 'urgent', 'Urgent'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    message = models.TextField()
    # Legacy field — kept for backward compat with existing data
    target_group = models.CharField(
        max_length=15,
        choices=TargetGroup.choices,
        default=TargetGroup.ALL,
    )
    audience = models.CharField(
        max_length=10,
        choices=Audience.choices,
        default=Audience.STAFF,
    )
    scope = models.CharField(
        max_length=15,
        choices=Scope.choices,
        default=Scope.ALL,
    )
    scope_detail = models.CharField(
        max_length=255,
        blank=True,
        help_text='Class PK, level_type:number, or comma-separated IDs for individual',
    )
    priority = models.CharField(
        max_length=10,
        choices=Priority.choices,
        default=Priority.NORMAL,
    )
    sent_via_sms = models.BooleanField(default=False)
    sent_via_email = models.BooleanField(default=False)
    recipient_count = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='announcements',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['audience']),
        ]

    def __str__(self):
        return self.title

    def get_audience_display_label(self):
        """Return human-readable label like 'Parents — Basic 3' or 'Teaching Staff'."""
        from academics.models import Class as ClassModel

        audience_label = self.get_audience_display()

        if self.scope == self.Scope.ALL:
            if self.audience == self.Audience.STAFF:
                return 'All Staff'
            return f'All {audience_label}'

        if self.scope in (self.Scope.TEACHING, self.Scope.NON_TEACHING):
            return self.get_scope_display()

        if self.scope == self.Scope.LEVEL and self.scope_detail:
            try:
                level_type, level_number = self.scope_detail.split(':')
                class_obj = ClassModel(level_type=level_type, level_number=int(level_number))
                return f'{audience_label} — {class_obj.get_level_display()}'
            except (ValueError, AttributeError):
                return f'{audience_label} — {self.scope_detail}'

        if self.scope == self.Scope.CLASS and self.scope_detail:
            try:
                cls = ClassModel.objects.get(pk=self.scope_detail)
                return f'{audience_label} — {cls.name}'
            except ClassModel.DoesNotExist:
                return f'{audience_label} — Class'

        if self.scope == self.Scope.INDIVIDUAL:
            return f'{audience_label} — Individual'

        return audience_label


class AnnouncementRead(models.Model):
    """Tracks which users have read an announcement."""

    announcement = models.ForeignKey(
        Announcement,
        on_delete=models.CASCADE,
        related_name='reads',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='announcement_reads',
    )
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('announcement', 'user')
        indexes = [
            models.Index(fields=['announcement', 'user']),
        ]

    def __str__(self):
        return f"{self.user} read {self.announcement}"
