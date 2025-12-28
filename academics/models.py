from django.db import models
from django.utils.translation import gettext_lazy as _
from teachers.models import Teacher
from django.utils import timezone


class Programme(models.Model):
    """
    SHS Programmes (General Arts, Business, Science, etc.)
    Only applicable to SHS level.
    """
    name = models.CharField(
        max_length=100,
        help_text="e.g., General Arts, Business, Science"
    )
    code = models.CharField(
        max_length=10,
        unique=True,
        help_text="e.g., ART, BUS, SCI"
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = "Programme"
        verbose_name_plural = "Programmes"

    def __str__(self):
        return self.name


class Class(models.Model):
    """
    Represents a class/classroom grouping of students.

    For Basic (KG, Primary, JHS):
        - Name format: B1-A, B1-B, JHS2-A, KG1-A

    For SHS:
        - Name auto-generated: Level + Programme Code + Section
        - Example: 1ART-A, 2BUS-B, 3SCI-A
    """
    class LevelType(models.TextChoices):
        KG = 'kg', _('Kindergarten')
        PRIMARY = 'primary', _('Primary')
        JHS = 'jhs', _('JHS')
        SHS = 'shs', _('SHS')

    # Level info
    level_type = models.CharField(
        max_length=10,
        choices=LevelType.choices,
        default=LevelType.PRIMARY
    )
    level_number = models.PositiveSmallIntegerField(
        help_text="1, 2, 3, etc."
    )
    section = models.CharField(
        max_length=5,
        help_text="A, B, C, etc."
    )

    # SHS specific
    programme = models.ForeignKey(
        Programme,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='classes',
        help_text="Required for SHS only"
    )

    # Auto-generated class name
    name = models.CharField(
        max_length=20,
        editable=False,
        help_text="Auto-generated: B1-A, JHS2-B, 1ART-A"
    )

    capacity = models.PositiveIntegerField(
        default=35,
        help_text="Maximum number of students"
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class_teacher = models.ForeignKey(
        'teachers.Teacher',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_classes',
        help_text="The form tutor or class teacher responsible for this class."
    )

    class Meta:
        ordering = ['level_type', 'level_number', 'programme', 'section']
        verbose_name = "Class"
        verbose_name_plural = "Classes"
        unique_together = ['level_type', 'level_number', 'programme', 'section']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.name = self.generate_name()
        super().save(*args, **kwargs)

    def generate_name(self):
        """Generate class name based on level type."""
        if self.level_type == self.LevelType.KG:
            return f"KG{self.level_number}-{self.section}"
        elif self.level_type == self.LevelType.PRIMARY:
            return f"B{self.level_number}-{self.section}"
        elif self.level_type == self.LevelType.JHS:
            # JHS is B7-B9, so add 6 to get actual Basic number
            basic_num = self.level_number + 6
            return f"B{basic_num}-{self.section}"
        elif self.level_type == self.LevelType.SHS:
            # SHS: 1ART-A, 2BUS-B format
            prog_code = self.programme.code if self.programme else "GEN"
            return f"{self.level_number}{prog_code}-{self.section}"
        return f"{self.level_type.upper()}{self.level_number}-{self.section}"

    @property
    def level_display(self):
        """Human-readable level name."""
        if self.level_type == self.LevelType.KG:
            return f"KG {self.level_number}"
        elif self.level_type == self.LevelType.PRIMARY:
            return f"Basic {self.level_number}"
        elif self.level_type == self.LevelType.JHS:
            return f"JHS {self.level_number}"
        elif self.level_type == self.LevelType.SHS:
            return f"SHS {self.level_number}"
        return str(self.level_number)

    @classmethod
    def get_by_level_type(cls, level_type):
        """Get all classes of a specific level type."""
        return cls.objects.filter(level_type=level_type, is_active=True)


class Subject(models.Model):
    """
    Represents a subject taught at the school.
    Subjects can be core (mandatory) or elective.
    """
    name = models.CharField(
        max_length=100,
        help_text="e.g., Mathematics, English Language, Integrated Science"
    )
    short_name = models.CharField(
        max_length=20,
        help_text="e.g., MATH, ENG, INT SCI"
    )
    code = models.CharField(
        max_length=20,
        blank=True,
        help_text="Optional subject code"
    )
    description = models.TextField(blank=True)
    is_core = models.BooleanField(
        default=True,
        help_text="Core subjects are mandatory"
    )
    # SHS subjects can be programme-specific
    programmes = models.ManyToManyField(
        Programme,
        blank=True,
        related_name='subjects',
        help_text="For SHS electives: which programmes offer this subject"
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_core', 'name']
        verbose_name = "Subject"
        verbose_name_plural = "Subjects"

    def __str__(self):
        return self.name


class ClassSubject(models.Model):
    """
    Links a Class to a Subject and assigns a specific Teacher.
    Example: 'Mr. Smith' teaches 'Mathematics' to 'JHS 2 B'.
    """
    class_assigned = models.ForeignKey(
        Class, 
        on_delete=models.CASCADE, 
        related_name='subjects'
    )
    subject = models.ForeignKey(
        Subject, 
        on_delete=models.CASCADE,
        related_name='class_allocations'
    )
    teacher = models.ForeignKey(
        Teacher, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='subject_assignments'
    )
    
    # Optional: Periods per week for timetable generation later
    periods_per_week = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ['class_assigned', 'subject']
        verbose_name = "Subject Allocation"
        verbose_name_plural = "Subject Allocations"

    def __str__(self):
        return f"{self.subject.name} - {self.class_assigned.name}"


class AttendanceSession(models.Model):
    class_assigned = models.ForeignKey(Class, on_delete=models.CASCADE, related_name='attendance_sessions')
    date = models.DateField(default=timezone.now)
    # Optional: 'Morning', 'Afternoon', or specific Subject
    session_type = models.CharField(max_length=20, default='Daily', choices=[('Daily', 'Daily Register')]) 
    created_by = models.ForeignKey('teachers.Teacher', on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['class_assigned', 'date', 'session_type']
        ordering = ['-date']

    def __str__(self):
        return f"{self.class_assigned} - {self.date}"


class AttendanceRecord(models.Model):
    class Status(models.TextChoices):
        PRESENT = 'P', 'Present'
        ABSENT = 'A', 'Absent'
        LATE = 'L', 'Late'
        EXCUSED = 'E', 'Excused'

    session = models.ForeignKey(AttendanceSession, on_delete=models.CASCADE, related_name='records')
    student = models.ForeignKey('students.Student', on_delete=models.CASCADE, related_name='attendance_records')
    status = models.CharField(max_length=1, choices=Status.choices, default=Status.PRESENT)
    remarks = models.CharField(max_length=100, blank=True)

    class Meta:
        unique_together = ['session', 'student']


class Period(models.Model):
    """
    Defines time slots for the school timetable.
    Example: Period 1: 8:00 AM - 8:40 AM
    """
    name = models.CharField(
        max_length=50,
        help_text="e.g., Period 1, Morning Assembly, Break"
    )
    start_time = models.TimeField()
    end_time = models.TimeField()
    order = models.PositiveSmallIntegerField(
        default=0,
        help_text="Display order in timetable"
    )
    is_break = models.BooleanField(
        default=False,
        help_text="True if this is a break period (not for classes)"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['order', 'start_time']
        verbose_name = "Period"
        verbose_name_plural = "Periods"

    def __str__(self):
        return f"{self.name} ({self.start_time.strftime('%H:%M')} - {self.end_time.strftime('%H:%M')})"

    @property
    def duration_minutes(self):
        """Calculate duration in minutes."""
        from datetime import datetime, timedelta
        start = datetime.combine(datetime.today(), self.start_time)
        end = datetime.combine(datetime.today(), self.end_time)
        return int((end - start).total_seconds() / 60)


class TimetableEntry(models.Model):
    """
    Assigns a ClassSubject to a specific day and period.
    Example: JHS 2A has Mathematics during Period 1 on Monday.
    """
    class Weekday(models.IntegerChoices):
        MONDAY = 1, 'Monday'
        TUESDAY = 2, 'Tuesday'
        WEDNESDAY = 3, 'Wednesday'
        THURSDAY = 4, 'Thursday'
        FRIDAY = 5, 'Friday'

    class_subject = models.ForeignKey(
        ClassSubject,
        on_delete=models.CASCADE,
        related_name='timetable_entries'
    )
    period = models.ForeignKey(
        Period,
        on_delete=models.CASCADE,
        related_name='timetable_entries'
    )
    weekday = models.PositiveSmallIntegerField(
        choices=Weekday.choices
    )

    class Meta:
        ordering = ['weekday', 'period__order']
        verbose_name = "Timetable Entry"
        verbose_name_plural = "Timetable Entries"

    def __str__(self):
        return f"{self.class_subject} - {self.get_weekday_display()} {self.period.name}"

    @property
    def teacher(self):
        return self.class_subject.teacher

    @property
    def subject(self):
        return self.class_subject.subject

    @property
    def class_assigned(self):
        return self.class_subject.class_assigned