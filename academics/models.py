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
    required_electives = models.PositiveSmallIntegerField(
        default=3,
        help_text="Minimum number of elective subjects students must take (typically 3-4 for SHS)"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = "Programme"
        verbose_name_plural = "Programmes"

    def __str__(self):
        return self.name

    def get_available_electives(self):
        """Get all elective subjects available for this programme."""
        return Subject.objects.filter(
            is_core=False,
            programmes=self
        ).order_by('name')


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
        CRECHE = 'creche', _('Creche')
        NURSERY = 'nursery', _('Nursery')
        KG = 'kg', _('Kindergarten')
        BASIC = 'basic', _('Basic')
        SHS = 'shs', _('SHS')

    class AttendanceType(models.TextChoices):
        DAILY = 'daily', _('Daily Register')
        PER_LESSON = 'per_lesson', _('Per-Lesson')

    # Level info
    level_type = models.CharField(
        max_length=10,
        choices=LevelType.choices,
        default=LevelType.BASIC
    )
    level_number = models.PositiveSmallIntegerField(
        help_text="1, 2, 3, etc."
    )
    section = models.CharField(
        max_length=15,
        blank=True,
        default='',
        help_text="A, B, C or Red, Blue, Green, etc. (Optional)"
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

    # Configurable attendance type
    attendance_type = models.CharField(
        max_length=20,
        choices=AttendanceType.choices,
        default=AttendanceType.DAILY,
        help_text="Daily: one register per day. Per-Lesson: each teacher marks their lesson."
    )

    class Meta:
        ordering = ['level_type', 'level_number', 'programme', 'section']
        verbose_name = "Class"
        verbose_name_plural = "Classes"
        unique_together = ['level_type', 'level_number', 'programme', 'section']
        indexes = [
            models.Index(fields=['class_teacher'], name='class_teacher_idx'),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.name = self.generate_name()
        super().save(*args, **kwargs)

    def generate_name(self):
        """Generate class name based on level type."""
        suffix = f"-{self.section}" if self.section else ""

        if self.level_type == self.LevelType.CRECHE:
            return f"Creche{self.level_number}{suffix}"
        elif self.level_type == self.LevelType.NURSERY:
            return f"Nursery{self.level_number}{suffix}"
        elif self.level_type == self.LevelType.KG:
            return f"KG{self.level_number}{suffix}"
        elif self.level_type == self.LevelType.BASIC:
            return f"B{self.level_number}{suffix}"
        elif self.level_type == self.LevelType.SHS:
            # SHS: 1ART-A, 2BUS-B format
            prog_code = self.programme.code if self.programme else "GEN"
            return f"{self.level_number}{prog_code}{suffix}"
        return f"{self.level_type.upper()}{self.level_number}{suffix}"

    @property
    def level_display(self):
        """Human-readable level name."""
        if self.level_type == self.LevelType.CRECHE:
            return f"Creche {self.level_number}"
        elif self.level_type == self.LevelType.NURSERY:
            return f"Nursery {self.level_number}"
        elif self.level_type == self.LevelType.KG:
            return f"KG {self.level_number}"
        elif self.level_type == self.LevelType.BASIC:
            return f"Basic {self.level_number}"
        elif self.level_type == self.LevelType.SHS:
            return f"SHS {self.level_number}"
        return str(self.level_number)

    @property
    def is_lower_basic(self):
        """Check if class is Lower Basic (B1-B6, formerly Primary)."""
        return self.level_type == self.LevelType.BASIC and self.level_number <= 6

    @property
    def is_upper_basic(self):
        """Check if class is Upper Basic (B7-B9, formerly JHS)."""
        return self.level_type == self.LevelType.BASIC and self.level_number >= 7

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
        unique=True,
        help_text="e.g., Mathematics, English Language, Integrated Science"
    )
    short_name = models.CharField(
        max_length=20,
        unique=True,
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


class SubjectTemplate(models.Model):
    """
    A reusable template of subjects that can be quickly applied to any class.
    E.g., "Core Subjects", "Science Electives", etc.
    """
    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="e.g., Core Subjects, Science Electives"
    )
    subjects = models.ManyToManyField(
        Subject,
        related_name='templates',
        help_text="Subjects included in this template"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = "Subject Template"
        verbose_name_plural = "Subject Templates"

    def __str__(self):
        return self.name

    def apply_to_class(self, class_obj, default_teacher=None):
        """
        Apply this template to a class, creating ClassSubject entries.
        Skips subjects already assigned to the class.
        Returns tuple: (created_count, skipped_count)
        """
        created = 0
        skipped = 0

        existing_subjects = set(
            ClassSubject.objects.filter(class_assigned=class_obj)
            .values_list('subject_id', flat=True)
        )

        for subject in self.subjects.filter(is_active=True):
            if subject.id in existing_subjects:
                skipped += 1
                continue

            ClassSubject.objects.create(
                class_assigned=class_obj,
                subject=subject,
                teacher=default_teacher
            )
            created += 1

        return created, skipped


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
        indexes = [
            models.Index(fields=['teacher'], name='classsub_teacher_idx'),
        ]

    def __str__(self):
        return f"{self.subject.name} - {self.class_assigned.name}"


class StudentSubjectEnrollment(models.Model):
    """
    Tracks which subjects a student is enrolled in for their class.

    For core subjects: Auto-created when student is enrolled in a class
    For elective subjects: Manually created by form teacher

    This is especially important for SHS where students choose electives
    (e.g., French vs Literature, Economics vs Geography)
    """
    student = models.ForeignKey(
        'students.Student',
        on_delete=models.CASCADE,
        related_name='subject_enrollments'
    )
    class_subject = models.ForeignKey(
        ClassSubject,
        on_delete=models.CASCADE,
        related_name='student_enrollments'
    )
    enrolled_at = models.DateTimeField(auto_now_add=True)
    enrolled_by = models.ForeignKey(
        'teachers.Teacher',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='student_enrollments_created'
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ['student', 'class_subject']
        verbose_name = "Student Subject Enrollment"
        verbose_name_plural = "Student Subject Enrollments"
        ordering = ['student__last_name', 'class_subject__subject__name']
        indexes = [
            models.Index(fields=['student', 'is_active'], name='sse_student_active_idx'),
        ]

    def __str__(self):
        return f"{self.student} - {self.class_subject.subject.name}"

    @classmethod
    def enroll_student_in_class_subjects(cls, student, class_obj, enrolled_by=None):
        """
        Auto-enroll a student in ALL subjects for their class.

        All students get enrolled in all subjects assigned to their class,
        regardless of school level or core/elective status.

        Called when a student is enrolled in a new class.
        """
        class_subjects = ClassSubject.objects.filter(
            class_assigned=class_obj
        )

        enrollments = []
        for class_subject in class_subjects:
            enrollment, created = cls.objects.get_or_create(
                student=student,
                class_subject=class_subject,
                defaults={
                    'enrolled_by': enrolled_by,
                    'is_active': True
                }
            )
            if created:
                enrollments.append(enrollment)
            elif not enrollment.is_active:
                # Reactivate if previously deactivated
                enrollment.is_active = True
                enrollment.save()
                enrollments.append(enrollment)

        return enrollments

    @classmethod
    def enroll_student_in_core_subjects(cls, student, class_obj, enrolled_by=None):
        """Alias for backward compatibility."""
        return cls.enroll_student_in_class_subjects(student, class_obj, enrolled_by)

    @classmethod
    def get_student_subjects(cls, student, class_obj=None):
        """
        Get all subjects a student is enrolled in.
        If class_obj is provided, filter by that class.
        """
        queryset = cls.objects.filter(student=student, is_active=True)
        if class_obj:
            queryset = queryset.filter(class_subject__class_assigned=class_obj)
        return queryset.select_related('class_subject__subject', 'class_subject__teacher')


class AttendanceSession(models.Model):
    class SessionType(models.TextChoices):
        DAILY = 'Daily', _('Daily Register')
        LESSON = 'Lesson', _('Per-Lesson Attendance')

    class_assigned = models.ForeignKey(Class, on_delete=models.CASCADE, related_name='attendance_sessions')
    date = models.DateField(default=timezone.now)
    session_type = models.CharField(
        max_length=20,
        choices=SessionType.choices,
        default=SessionType.DAILY
    )
    created_by = models.ForeignKey('teachers.Teacher', on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Fields for lesson-based attendance (only used when session_type='Lesson')
    timetable_entry = models.ForeignKey(
        'TimetableEntry',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='attendance_sessions',
        help_text="The specific timetable slot for this attendance"
    )
    period = models.ForeignKey(
        'Period',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='attendance_sessions',
        help_text="The period during which attendance was taken"
    )
    class_subject = models.ForeignKey(
        'ClassSubject',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='attendance_sessions',
        help_text="The subject for this lesson attendance"
    )

    class Meta:
        ordering = ['-date']
        indexes = [
            models.Index(fields=['class_assigned', 'date'], name='attsess_class_date_idx'),
            models.Index(fields=['date'], name='attsess_date_idx'),
            models.Index(fields=['timetable_entry', 'date'], name='attsess_entry_date_idx'),
            models.Index(fields=['class_subject', 'date'], name='attsess_subj_date_idx'),
        ]
        constraints = [
            # Daily: one per class per day
            models.UniqueConstraint(
                fields=['class_assigned', 'date'],
                condition=models.Q(session_type='Daily'),
                name='unique_daily_session'
            ),
            # Lesson: one per timetable entry per day
            models.UniqueConstraint(
                fields=['class_assigned', 'date', 'timetable_entry'],
                condition=models.Q(session_type='Lesson'),
                name='unique_lesson_session'
            ),
        ]

    def __str__(self):
        if self.session_type == self.SessionType.LESSON and self.class_subject:
            return f"{self.class_assigned} - {self.class_subject.subject.name} - {self.date}"
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
        indexes = [
            models.Index(fields=['session', 'student'], name='attrec_sess_stud_idx'),
            models.Index(fields=['student', 'status'], name='attrec_stud_status_idx'),
        ]


class Period(models.Model):
    """
    Defines time slots for the school timetable.
    Example: Period 1: 8:00 AM - 8:40 AM
    """
    name = models.CharField(
        max_length=50,
        unique=True,
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
        from datetime import datetime
        start = datetime.combine(datetime.today(), self.start_time)
        end = datetime.combine(datetime.today(), self.end_time)
        return int((end - start).total_seconds() / 60)


class Classroom(models.Model):
    """Physical classroom/room where lessons are held."""

    class RoomType(models.TextChoices):
        REGULAR = 'regular', 'Regular Classroom'
        LAB = 'lab', 'Laboratory'
        COMPUTER = 'computer', 'Computer Lab'
        LIBRARY = 'library', 'Library'
        HALL = 'hall', 'Assembly Hall'
        OTHER = 'other', 'Other'

    name = models.CharField(
        max_length=50,
        unique=True,
        help_text="e.g., Room 101, Science Lab 1"
    )
    code = models.CharField(
        max_length=10,
        blank=True,
        help_text="Short code e.g., R101, LAB1"
    )
    capacity = models.PositiveIntegerField(
        default=40,
        help_text="Maximum seating capacity"
    )
    room_type = models.CharField(
        max_length=20,
        choices=RoomType.choices,
        default=RoomType.REGULAR
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = "Classroom"
        verbose_name_plural = "Classrooms"

    def __str__(self):
        if self.code:
            return f"{self.name} ({self.code})"
        return self.name


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
        related_name='timetable_entries',
        help_text="Starting period for this lesson"
    )
    weekday = models.PositiveSmallIntegerField(
        choices=Weekday.choices
    )
    is_double = models.BooleanField(
        default=False,
        help_text="If true, this lesson spans two consecutive periods"
    )
    classroom = models.ForeignKey(
        Classroom,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='timetable_entries',
        help_text="Physical room where this lesson is held"
    )

    class Meta:
        ordering = ['weekday', 'period__order']
        verbose_name = "Timetable Entry"
        verbose_name_plural = "Timetable Entries"
        indexes = [
            # Index for grid display (fetching by day)
            models.Index(fields=['weekday', 'period'], name='timetable_weekday_period_idx'),
            # Index for conflict checking
            models.Index(fields=['class_subject', 'period', 'weekday'], name='timetable_conflict_check_idx'),
            # Index for teacher schedule lookup
            models.Index(fields=['weekday'], name='timetable_weekday_idx'),
        ]

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