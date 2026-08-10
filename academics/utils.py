"""
Utility functions for academics module, especially for per-lesson attendance.
"""
import json
import logging
from datetime import timedelta

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.shortcuts import redirect
from django.utils import timezone

logger = logging.getLogger(__name__)


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


# ============================================================
# Attendance-taking helpers
#
# Shared by the academics-app class/lesson attendance views and the
# core-app teacher-portal attendance views, since both save and validate
# attendance for the same session/student/status shape. Living here (rather
# than in academics/views/attendance.py, where they used to be private
# module-level helpers) means core/views.py can depend on a proper shared
# module instead of reaching into another app's view-module internals.
# ============================================================

def validate_status(raw_status):
    """Validate and return a safe attendance status value."""
    from .models import AttendanceRecord
    valid_statuses = {s.value for s in AttendanceRecord.Status}
    if raw_status in valid_statuses:
        return raw_status
    return AttendanceRecord.Status.PRESENT


def term_date_error(target_date, current_term):
    """
    Returns an error message if `target_date` isn't allowed for attendance
    marking/editing, or None if it's fine. Dates within the current term are
    always allowed. A date before the current term only passes when
    SchoolSettings has opted in to past-term marking AND the date actually
    falls within some previously defined term - otherwise a school could end
    up with attendance sessions dangling on dates with no real academic
    period behind them.
    """
    if not current_term:
        return None
    if target_date > current_term.end_date:
        return (
            f'Cannot mark attendance after the current term ended '
            f'({current_term.end_date.strftime("%B %d, %Y")}).'
        )
    if target_date < current_term.start_date:
        from core.models import SchoolSettings, Term
        if not SchoolSettings.load().allow_past_term_attendance:
            return (
                f'Cannot mark attendance before the current term started '
                f'({current_term.start_date.strftime("%B %d, %Y")}).'
            )
        if not Term.objects.filter(start_date__lte=target_date, end_date__gte=target_date).exists():
            return f'{target_date.strftime("%b %d, %Y")} does not fall within any defined term.'
    return None


def nearest_valid_attendance_date(target_date, current_term, max_lookback=14):
    """
    Walk backward from `target_date` (inclusive, clamped to the current
    term's end date if `target_date` has run past it) to find the most
    recent date that's a school day (honoring a term-specific school_days
    override when `current_term` has one) and not a holiday. Used only when
    the caller didn't explicitly choose a date (e.g. clicking straight into
    a class defaults to today) - neither a weekend/holiday landing on
    "today" nor a term that has already ended should be a dead end, since
    a teacher who fell behind on marking still needs a way in to catch up
    on unmarked past days within the term; the in-page date picker is the
    only other way to reach a different date, and it's unreachable if the
    page never renders. Returns None if nothing valid turns up within
    `max_lookback` days or before the current term's start.
    """
    from core.models import SchoolHoliday
    from core.utils import is_valid_school_day

    earliest = current_term.start_date if current_term else target_date - timedelta(days=max_lookback)
    if current_term and target_date > current_term.end_date:
        candidate = current_term.end_date
    else:
        candidate = target_date
    tries = 0
    while candidate >= earliest and tries <= max_lookback:
        if (is_valid_school_day(candidate, term=current_term)
                and not SchoolHoliday.get_holiday_name(candidate)):
            return candidate
        candidate -= timedelta(days=1)
        tries += 1
    return None


def nearest_valid_lesson_date(target_date, entry_weekday, current_term, max_weeks_back=8):
    """
    Same catch-up idea as nearest_valid_attendance_date, but for a specific
    timetable entry: a lesson only runs on one fixed weekday, so walking
    back day by day could land on a date the entry doesn't even meet on.
    Walks backward in 7-day steps (clamped to the term's end date first, so
    a lapsed term still lands within it) to find the most recent occurrence
    of `entry_weekday` that isn't a holiday. Returns None if nothing valid
    turns up within `max_weeks_back` weeks or before the term's start.
    """
    from core.models import SchoolHoliday

    if not current_term:
        return None
    candidate = min(target_date, current_term.end_date)
    # Align to the entry's weekday first - normally already a match, since
    # callers only reach this from a same-weekday-filtered lesson list.
    candidate -= timedelta(days=(candidate.isoweekday() - entry_weekday) % 7)
    weeks = 0
    while candidate >= current_term.start_date and weeks <= max_weeks_back:
        if not SchoolHoliday.get_holiday_name(candidate):
            return candidate
        candidate -= timedelta(days=7)
        weeks += 1
    return None


def pickable_attendance_dates(class_obj, current_term, today, session_type, selected_date=None):
    """
    Valid days a teacher can pick from the attendance date dropdown, most
    recent first, each flagged with whether that day already has real
    (non-empty) attendance saved for `class_obj`. Bounded to the current
    term's start through today (or the term's own end date if it has
    already lapsed) - the same range term_date_error actually allows
    marking within, so nothing reachable via the old min/max-bounded date
    input becomes unreachable here.

    `session_type` should be AttendanceSession.SessionType.DAILY for the
    daily flow, or .LESSON for the per-lesson flow - for LESSON, "marked"
    means at least one lesson session that day has records, aggregated
    across the whole class (not scoped to a single timetable entry), since
    that's what both lesson-flow dropdowns (the hub list and a single
    lesson's own date picker, which routes back to that same hub) actually
    let a teacher jump to.
    """
    from core.utils import get_valid_school_days
    from .models import AttendanceSession

    if not current_term:
        return []
    end = min(today, current_term.end_date)
    valid_days = get_valid_school_days(current_term.start_date, end, term=current_term)
    if not valid_days:
        return []

    marked_dates = set(
        AttendanceSession.objects.filter(
            class_assigned=class_obj,
            session_type=session_type,
            date__in=valid_days,
            records__isnull=False,
        ).values_list('date', flat=True).distinct()
    )

    return [
        {
            'value': d.isoformat(),
            'label': d.strftime('%a, %d %b'),
            'marked': d in marked_dates,
            'selected': d == selected_date,
        }
        for d in reversed(valid_days)
    ]


def blocked_redirect(request, message, redirect_url, toast_type='warning'):
    """
    Redirect after blocking an action, showing `message` via a toast for
    HTMX requests (the actual working notification mechanism in this app -
    the destination pages here don't render Django's messages framework
    output, so a plain messages.warning() + redirect is invisible for the
    HTMX flow that's how this view is actually reached in the UI).
    """
    if request.htmx:
        response = HttpResponse(status=204)
        response['HX-Trigger'] = json.dumps({
            'showToast': {'message': message, 'type': toast_type},
        })
        return response
    messages.warning(request, message)
    return redirect(redirect_url)


def save_attendance_records(request, session, students, redirect_url,
                             success_msg='Attendance saved'):
    """
    Process POST data and bulk save attendance records for a session.
    redirect_url should be a resolved URL path (from reverse()).
    Returns an HttpResponse.
    """
    from .models import AttendanceRecord

    student_ids = [s.id for s in students]

    existing_records = {
        r.student_id: r
        for r in AttendanceRecord.objects.filter(
            session=session, student_id__in=student_ids
        ).select_related('student')
    }

    records_to_create = []
    records_to_update = []

    for student in students:
        status_key = f"status_{student.id}"
        raw = request.POST.get(status_key, 'P')
        new_status = validate_status(raw)

        if student.id in existing_records:
            record = existing_records[student.id]
            if record.status != new_status:
                record.status = new_status
                record.marked_by = request.user
                records_to_update.append(record)
        else:
            records_to_create.append(AttendanceRecord(
                session=session,
                student=student,
                status=new_status,
                marked_by=request.user,
            ))

    def _write(create_list, update_list):
        with transaction.atomic():
            if create_list:
                AttendanceRecord.objects.bulk_create(create_list)
            if update_list:
                AttendanceRecord.objects.bulk_update(
                    update_list, ['status', 'marked_by']
                )

    try:
        try:
            _write(records_to_create, records_to_update)
        except IntegrityError:
            # A concurrent request for this same session/student won the
            # race and inserted one of these records first (e.g. a
            # double-tap on Save under a slow mobile connection, or two
            # tabs open on the same session) - the unique_together
            # constraint tripped and rolled back the whole batch above.
            # Re-resolve create-vs-update against the now-current DB state
            # and retry once, so this still lands on whatever THIS
            # submission asked for instead of surfacing a scary "failed to
            # save" for a save that actually mostly succeeded.
            existing_now = {
                r.student_id: r
                for r in AttendanceRecord.objects.filter(
                    session=session, student_id__in=student_ids
                ).select_related('student')
            }
            retry_create = []
            retry_update = list(records_to_update)
            already_synced = 0
            for rec in records_to_create:
                existing = existing_now.get(rec.student_id)
                if existing is None:
                    retry_create.append(rec)
                elif existing.status != rec.status:
                    existing.status = rec.status
                    existing.marked_by = rec.marked_by
                    retry_update.append(existing)
                else:
                    # The concurrent request already wrote the same status
                    # this submission wanted - nothing left to save, but it
                    # still counts toward what this submission asked for.
                    already_synced += 1
            _write(retry_create, retry_update)
            records_to_create, records_to_update = retry_create, retry_update
            total = len(records_to_create) + len(records_to_update) + already_synced
        else:
            total = len(records_to_create) + len(records_to_update)

        # Notify guardians and students of absences
        absent_students = []
        for rec in records_to_create:
            if rec.status == 'A':
                absent_students.append(rec.student)
        for rec in records_to_update:
            if rec.status == 'A':
                absent_students.append(rec.student)

        if absent_students:
            from core.notifications import notify_guardian, notify_student
            session_date = session.date
            today = timezone.localdate()
            date_label = 'today' if session_date == today else session_date.strftime('%b %d')
            for s in absent_students:
                notify_guardian(
                    s,
                    title='Absence Recorded',
                    message=f'{s.full_name} was marked absent {date_label}.',
                    category='attendance',
                    notification_type='warning',
                    icon='fa-solid fa-user-xmark',
                )
                notify_student(
                    s,
                    title='Absence Recorded',
                    message=f'You were marked absent {date_label}.',
                    category='attendance',
                    notification_type='warning',
                    icon='fa-solid fa-user-xmark',
                )

        messages.success(request, f'{success_msg} ({total} records).')
    except Exception as e:
        logger.error("Failed to save attendance: %s", e)
        messages.error(request, 'Failed to save attendance.')
        if request.htmx:
            response = HttpResponse(status=500)
            response['HX-Reswap'] = 'none'
            return response
        return redirect(redirect_url)

    if request.htmx:
        response = HttpResponse(status=204)
        response['HX-Trigger'] = 'closeModal'
        response['HX-Redirect'] = redirect_url
        return response

    return redirect(redirect_url)
