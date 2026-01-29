"""
Utility functions for academics module, especially for per-lesson attendance.
"""
from django.utils import timezone
from datetime import datetime


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


def get_teacher_lessons_today(teacher, class_obj=None):
    """
    Get all of a teacher's lessons for today with attendance status.

    Args:
        teacher: Teacher instance
        class_obj: Optional Class instance to filter by specific class

    Returns:
        List of dicts with lesson info and attendance status
    """
    from .models import TimetableEntry, AttendanceSession, Class

    now = timezone.localtime()
    current_time = now.time()
    today = now.date()
    today_weekday = now.isoweekday()

    # Get all timetable entries for today
    entries_query = TimetableEntry.objects.filter(
        class_subject__teacher=teacher,
        weekday=today_weekday
    ).select_related(
        'class_subject__class_assigned',
        'class_subject__subject',
        'period',
        'classroom'
    ).order_by('period__order')

    if class_obj:
        entries_query = entries_query.filter(class_subject__class_assigned=class_obj)

    entries = list(entries_query)

    # Get existing attendance sessions for these entries today
    entry_ids = [e.id for e in entries]
    existing_sessions = {
        s.timetable_entry_id: s
        for s in AttendanceSession.objects.filter(
            timetable_entry_id__in=entry_ids,
            date=today,
            session_type=AttendanceSession.SessionType.LESSON
        )
    }

    lessons = []
    for entry in entries:
        class_obj_for_entry = entry.class_subject.class_assigned

        # Determine status
        is_past = entry.period.end_time < current_time
        is_current = entry.period.start_time <= current_time <= entry.period.end_time
        is_upcoming = entry.period.start_time > current_time

        session = existing_sessions.get(entry.id)
        attendance_taken = session is not None

        # Only show for per-lesson classes
        uses_lesson_attendance = should_use_lesson_attendance(class_obj_for_entry)

        lessons.append({
            'entry': entry,
            'period': entry.period,
            'class_obj': class_obj_for_entry,
            'subject': entry.class_subject.subject,
            'class_subject': entry.class_subject,
            'classroom': entry.classroom,
            'is_past': is_past,
            'is_current': is_current,
            'is_upcoming': is_upcoming,
            'attendance_taken': attendance_taken,
            'session': session,
            'uses_lesson_attendance': uses_lesson_attendance,
        })

    return lessons


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

    stats = []
    for cs in class_subjects:
        # Get sessions for this subject in the date range
        sessions = AttendanceSession.objects.filter(
            class_assigned=class_obj,
            class_subject=cs,
            session_type=AttendanceSession.SessionType.LESSON,
            date__gte=start_date,
            date__lte=end_date
        )

        session_count = sessions.count()

        if session_count == 0:
            stats.append({
                'class_subject': cs,
                'subject': cs.subject,
                'teacher': cs.teacher,
                'sessions': 0,
                'present': 0,
                'absent': 0,
                'late': 0,
                'rate': 0,
            })
            continue

        # Get attendance records
        records = AttendanceRecord.objects.filter(
            session__in=sessions
        ).aggregate(
            total=Count('id'),
            present=Count('id', filter=Q(status='P')),
            absent=Count('id', filter=Q(status='A')),
            late=Count('id', filter=Q(status='L')),
            excused=Count('id', filter=Q(status='E')),
        )

        total = records['total'] or 0
        present = (records['present'] or 0) + (records['late'] or 0)
        rate = round((present / total) * 100, 1) if total > 0 else 0

        stats.append({
            'class_subject': cs,
            'subject': cs.subject,
            'teacher': cs.teacher,
            'sessions': session_count,
            'present': records['present'] or 0,
            'absent': records['absent'] or 0,
            'late': records['late'] or 0,
            'excused': records['excused'] or 0,
            'rate': rate,
        })

    return stats
