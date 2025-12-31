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
        self.save()

    def mark_failed(self, error=''):
        self.status = self.Status.FAILED
        self.error_message = str(error)
        self.save()


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
