"""
Academics views package.

This package splits the views into logical modules:
- base: Common utilities, decorators, and helper functions
- dashboard: Index/dashboard view
- programmes: Programme CRUD
- classes: Class CRUD, detail, student enrollment, exports
- subjects: Subject and Subject Template CRUD
- attendance: Attendance taking, reports, exports
- timetable: Timetable management
- periods: Period management
- classrooms: Classroom management
- api: API endpoints
"""

# Base utilities (exported for use by other modules if needed)
from .base import (
    is_school_admin,
    admin_required,
    is_teacher_or_admin,
    teacher_or_admin_required,
    htmx_render,
)

# Dashboard
from .dashboard import index

# Programmes
from .programmes import (
    programme_create,
    programme_edit,
    programme_delete,
)

# Classes
from .classes import (
    classes_list,
    class_create,
    class_edit,
    class_delete,
    class_detail,
    class_register,
    class_subjects,
    class_subjects_modal,
    class_subject_create,
    class_subject_delete,
    class_student_enroll,
    class_student_remove,
    class_student_electives,
    class_bulk_electives,
    class_promote,
    class_sync_subjects,
    class_export,
    classes_bulk_export,
    class_detail_pdf,
)

# Subjects
from .subjects import (
    subject_create,
    subject_edit,
    subject_delete,
    template_create,
    template_edit,
    template_delete,
    apply_template,
)

# Attendance
from .attendance import (
    class_attendance_take,
    class_attendance_edit,
    class_attendance_history,
    lesson_attendance_list,
    take_lesson_attendance,
    class_weekly_attendance_report,
    attendance_reports,
    attendance_export,
    student_attendance_detail,
    notify_absent_parents,
)

# Timetable
from .timetable import (
    timetable_index,
    class_timetable,
    timetable_entry_create,
    bulk_timetable_entry,
    copy_timetable,
    timetable_entry_edit,
    timetable_entry_delete,
    teacher_schedule_preview,
)

# Periods
from .periods import (
    periods,
    period_create,
    period_edit,
    period_delete,
)

# Classrooms
from .classrooms import (
    classrooms,
    classroom_create,
    classroom_edit,
    classroom_delete,
)

# API
from .api import api_class_subjects


__all__ = [
    # Base
    'is_school_admin',
    'admin_required',
    'is_teacher_or_admin',
    'teacher_or_admin_required',
    'htmx_render',
    # Dashboard
    'index',
    # Programmes
    'programme_create',
    'programme_edit',
    'programme_delete',
    # Classes
    'classes_list',
    'class_create',
    'class_edit',
    'class_delete',
    'class_detail',
    'class_register',
    'class_subjects',
    'class_subjects_modal',
    'class_subject_create',
    'class_subject_delete',
    'class_student_enroll',
    'class_student_remove',
    'class_student_electives',
    'class_bulk_electives',
    'class_promote',
    'class_sync_subjects',
    'class_export',
    'classes_bulk_export',
    'class_detail_pdf',
    # Subjects
    'subject_create',
    'subject_edit',
    'subject_delete',
    'template_create',
    'template_edit',
    'template_delete',
    'apply_template',
    # Attendance
    'class_attendance_take',
    'class_attendance_edit',
    'class_attendance_history',
    'lesson_attendance_list',
    'take_lesson_attendance',
    'class_weekly_attendance_report',
    'attendance_reports',
    'attendance_export',
    'student_attendance_detail',
    'notify_absent_parents',
    # Timetable
    'timetable_index',
    'class_timetable',
    'timetable_entry_create',
    'bulk_timetable_entry',
    'copy_timetable',
    'timetable_entry_edit',
    'timetable_entry_delete',
    'teacher_schedule_preview',
    # Periods
    'periods',
    'period_create',
    'period_edit',
    'period_delete',
    # Classrooms
    'classrooms',
    'classroom_create',
    'classroom_edit',
    'classroom_delete',
    # API
    'api_class_subjects',
]
