"""
Utility functions for academics module, especially for per-lesson attendance.
"""
from django.utils import timezone


def get_current_period():
    """
    Get the currently active period based on current time.
    Returns the Period object if found, None otherwise.
    """
    from .models import Period

    now = timezone.localtime().time()
    return Period.objects.filter(
        is_active=True,
        is_break=False,
        start_time__lte=now,
        end_time__gte=now
    ).first()


def get_current_lesson_for_teacher(teacher, class_obj=None):
    """
    Get the current lesson from timetable for a teacher.

    Args:
        teacher: Teacher instance
        class_obj: Optional Class instance to filter by specific class

    Returns:
        dict with keys: entry, period, is_current, class_obj, subject
        or None if no current lesson
    """
    from .models import TimetableEntry, Period

    now = timezone.localtime()
    current_time = now.time()
    today_weekday = now.isoweekday()  # 1=Monday, 7=Sunday

    # Get current period
    current_period = Period.objects.filter(
        is_active=True,
        is_break=False,
        start_time__lte=current_time,
        end_time__gte=current_time
    ).first()

    if not current_period:
        return None

    # Find timetable entry for this teacher, period, and weekday
    entry_query = TimetableEntry.objects.filter(
        class_subject__teacher=teacher,
        period=current_period,
        weekday=today_weekday
    ).select_related(
        'class_subject__class_assigned',
        'class_subject__subject',
        'period'
    )

    if class_obj:
        entry_query = entry_query.filter(class_subject__class_assigned=class_obj)

    entry = entry_query.first()

    if not entry:
        return None

    return {
        'entry': entry,
        'period': current_period,
        'is_current': True,
        'class_obj': entry.class_subject.class_assigned,
        'subject': entry.class_subject.subject,
        'class_subject': entry.class_subject,
    }


def should_use_lesson_attendance(class_obj):
    """
    Check if a class is configured for per-lesson attendance.

    Args:
        class_obj: Class instance

    Returns:
        bool: True if class uses per-lesson attendance
    """
    from .models import Class
    return class_obj.attendance_type == Class.AttendanceType.PER_LESSON


def get_students_for_lesson(class_obj, class_subject=None):
    """
    Get students for a lesson, considering elective enrollment.

    For core subjects: All students in the class
    For elective subjects: Only students enrolled in that elective

    Args:
        class_obj: Class instance
        class_subject: Optional ClassSubject instance

    Returns:
        QuerySet of Student objects
    """
    from students.models import Student
    from .models import StudentSubjectEnrollment

    # Get all active students in the class
    base_query = Student.objects.filter(
        current_class=class_obj,
        status='active'
    ).order_by('first_name', 'last_name')

    # If no specific subject, return all students
    if not class_subject:
        return base_query

    # Check if the subject is core
    if class_subject.subject.is_core:
        return base_query

    # For elective subjects, filter by enrollment
    enrolled_student_ids = StudentSubjectEnrollment.objects.filter(
        class_subject=class_subject,
        is_active=True
    ).values_list('student_id', flat=True)

    return base_query.filter(id__in=enrolled_student_ids)


def get_lesson_attendance_stats(class_obj, start_date=None, end_date=None):
    """
    Get attendance statistics for a class with per-lesson attendance.

    Args:
        class_obj: Class instance
        start_date: Optional start date for the report period
        end_date: Optional end date for the report period

    Returns:
        dict with subject-wise attendance statistics
    """
    from django.db.models import Count, Q
    from .models import AttendanceSession, AttendanceRecord, ClassSubject

    if not start_date:
        start_date = timezone.now().date() - timezone.timedelta(days=7)
    if not end_date:
        end_date = timezone.now().date()

    # Get all subjects for this class
    class_subjects = ClassSubject.objects.filter(
        class_assigned=class_obj
    ).select_related('subject', 'teacher')

    # Single query: session counts and attendance stats per class_subject.
    # records__isnull=False excludes sessions nobody actually saved attendance
    # for yet (opening the "take attendance" screen creates the session row
    # before Save is tapped) - otherwise "sessions" would over-count relative
    # to what was really marked. The join to records fans out one row per
    # record, so count distinct session ids rather than raw joined rows.
    session_counts = dict(
        AttendanceSession.objects.filter(
            class_assigned=class_obj,
            session_type=AttendanceSession.SessionType.LESSON,
            date__gte=start_date,
            date__lte=end_date,
            records__isnull=False,
        ).values('class_subject_id').annotate(
            count=Count('id', distinct=True)
        ).values_list('class_subject_id', 'count')
    )

    record_stats = {
        row['session__class_subject_id']: row
        for row in AttendanceRecord.objects.filter(
            session__class_assigned=class_obj,
            session__session_type=AttendanceSession.SessionType.LESSON,
            session__date__gte=start_date,
            session__date__lte=end_date,
        ).values('session__class_subject_id').annotate(
            total=Count('id'),
            present=Count('id', filter=Q(status='P')),
            absent=Count('id', filter=Q(status='A')),
            late=Count('id', filter=Q(status='L')),
            excused=Count('id', filter=Q(status='E')),
        )
    }

    stats = []
    for cs in class_subjects:
        sc = session_counts.get(cs.id, 0)
        rs = record_stats.get(cs.id, {})

        present_cnt = rs.get('present', 0) or 0
        late_cnt = rs.get('late', 0) or 0
        absent_cnt = rs.get('absent', 0) or 0
        present_total = present_cnt + late_cnt
        countable = present_total + absent_cnt
        rate = round((present_total / countable) * 100, 1) if countable > 0 else 0

        stats.append({
            'class_subject': cs,
            'subject': cs.subject,
            'teacher': cs.teacher,
            'sessions': sc,
            'present': present_cnt,
            'absent': absent_cnt,
            'late': late_cnt,
            'excused': rs.get('excused', 0) or 0,
            'rate': rate,
        })

    return stats
