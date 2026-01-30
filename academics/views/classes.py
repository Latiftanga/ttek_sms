"""Class management views including CRUD, detail, and student enrollment."""
import io
import logging
from datetime import datetime
from io import BytesIO

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, FileResponse
from django.utils import timezone
from django.db import models, transaction
from django.db.models import Count, Q, Sum, Case, When, IntegerField
from django.contrib import messages
from django.core.paginator import Paginator

from students.models import Student

from ..models import (
    Class, ClassSubject, AttendanceSession, AttendanceRecord,
    TimetableEntry, StudentSubjectEnrollment
)
from ..forms import ClassForm, StudentEnrollmentForm, ClassSubjectForm
from .base import admin_required, teacher_or_admin_required, htmx_render


def get_classes_list_context():
    """Get context for classes list."""
    classes = Class.objects.select_related('programme', 'class_teacher').annotate(
        student_count=Count('students', filter=models.Q(students__status='active'))
    ).order_by('level_number', 'section')
    return {'classes': classes}


@admin_required
def classes_list(request):
    """Classes list page with search and filters."""
    # Get filter parameters
    search = request.GET.get('search', '').strip()
    level_filter = request.GET.get('level', '')

    # Get classes with student counts
    classes = Class.objects.select_related('programme', 'class_teacher').annotate(
        student_count=Count('students', filter=models.Q(students__status='active'))
    ).order_by('level_number', 'section')

    # Apply search filter
    if search:
        classes = classes.filter(
            Q(name__icontains=search) |
            Q(class_teacher__first_name__icontains=search) |
            Q(class_teacher__last_name__icontains=search) |
            Q(programme__name__icontains=search)
        )

    # Apply level filter
    if level_filter:
        classes = classes.filter(level_type=level_filter)

    # Pagination
    per_page = request.GET.get('per_page', '25')
    try:
        per_page = int(per_page)
        if per_page not in [25, 50, 100]:
            per_page = 25
    except ValueError:
        per_page = 25

    paginator = Paginator(classes, per_page)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Build subtitle - cache total_students to avoid querying twice
    total_classes = paginator.count
    total_students = Student.objects.filter(status='active').count()
    all_classes_count = Class.objects.count()
    subtitle = f"{total_classes} class{'es' if total_classes != 1 else ''} • {total_students} student{'s' if total_students != 1 else ''}"
    if search or level_filter:
        subtitle += " (filtered)"

    context = {
        'classes': page_obj,
        'page_obj': page_obj,
        'paginator': paginator,
        'per_page': per_page,
        'search': search,
        'level_filter': level_filter,
        'stats': {
            'total_classes': all_classes_count,
            'total_students': total_students,
        },
        'class_form': ClassForm(),
        # Navigation
        'back_url': '/academics/',
        'breadcrumbs': [
            {'label': 'Home', 'url': '/', 'icon': 'fa-solid fa-home'},
            {'label': 'Academics', 'url': '/academics/'},
            {'label': 'Classes'},
        ],
        'subtitle': subtitle,
    }

    return htmx_render(
        request,
        'academics/classes.html',
        'academics/partials/classes_content.html',
        context
    )


@admin_required
def class_create(request):
    """Create a new class."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    form = ClassForm(request.POST)
    if form.is_valid():
        form.save()
        if request.htmx:
            # Return updated classes content and close modal
            context = get_classes_list_context()
            context['stats'] = {
                'total_classes': Class.objects.count(),
                'total_students': Student.objects.filter(status='active').count(),
            }
            context['class_form'] = ClassForm()
            response = render(request, 'academics/partials/classes_content.html', context)
            response['HX-Trigger'] = 'closeModal'
            response['HX-Retarget'] = '#main-content'
            response['HX-Reswap'] = 'innerHTML'
            return response
        return redirect('academics:classes')

    # Validation error (422 keeps modal open)
    if request.htmx:
        response = render(request, 'academics/partials/modal_class_form.html', {
            'form': form,
            'is_create': True,
        })
        response.status_code = 422
        return response
    return redirect('academics:classes')


@admin_required
def class_edit(request, pk):
    """Edit a class."""
    cls = get_object_or_404(Class, pk=pk)

    # Check if editing from class detail page (not from classes list)
    current_url = request.headers.get('HX-Current-URL', '')
    is_detail_page = f'/academics/classes/{pk}/' in current_url and not current_url.endswith('/academics/classes/')

    if request.method == 'GET':
        form = ClassForm(instance=cls)
        return render(request, 'academics/partials/modal_class_form.html', {
            'form': form,
            'class': cls,
            'is_detail_page': is_detail_page,
        })

    if request.method != 'POST':
        return HttpResponse(status=405)

    form = ClassForm(request.POST, instance=cls)
    if form.is_valid():
        cls = form.save()
        if request.htmx:
            if is_detail_page:
                # Return updated class detail content
                context = get_class_detail_base_context(cls)
                context.update(get_register_tab_context(cls))
                context.update(get_teachers_tab_context(cls))
                context.update(get_attendance_tab_context(cls))
                context.update(get_promotion_history_context(cls))

                response = render(request, 'academics/partials/class_detail_content.html', context)
                response['HX-Trigger'] = 'closeModal'
                response['HX-Retarget'] = '#main-content'
                response['HX-Reswap'] = 'innerHTML'
                return response
            else:
                # Return updated classes list content
                context = get_classes_list_context()
                context['stats'] = {
                    'total_classes': Class.objects.count(),
                    'total_students': Student.objects.filter(status='active').count(),
                }
                context['class_form'] = ClassForm()
                response = render(request, 'academics/partials/classes_content.html', context)
                response['HX-Trigger'] = 'closeModal'
                response['HX-Retarget'] = '#main-content'
                response['HX-Reswap'] = 'innerHTML'
                return response
        return redirect('academics:classes')

    # Validation error (422 keeps modal open)
    if request.htmx:
        response = render(request, 'academics/partials/modal_class_form.html', {
            'form': form,
            'class': cls,
            'is_detail_page': is_detail_page,
        })
        response.status_code = 422
        return response
    return redirect('academics:classes')


@admin_required
def class_delete(request, pk):
    """Delete a class."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    cls = get_object_or_404(Class, pk=pk)
    cls.delete()

    if request.htmx:
        response = HttpResponse(status=204)
        response['HX-Refresh'] = 'true'
        return response
    return redirect('academics:classes')


# ============ CLASS DETAIL HELPERS ============

def get_register_tab_context(class_obj, request=None, page=1, search='', gender='', sort='name'):
    """Context for the Students/Register tab with pagination, search, filter and sort."""
    students = Student.objects.filter(
        current_class=class_obj,
        status='active'
    )

    # Gender breakdown (before filtering) - single aggregate query
    gender_stats = students.aggregate(
        total=Count('id'),
        male_count=Count('id', filter=models.Q(gender='M')),
        female_count=Count('id', filter=models.Q(gender='F'))
    )
    total_students = gender_stats['total'] or 0
    male_count = gender_stats['male_count'] or 0
    female_count = gender_stats['female_count'] or 0

    # Apply gender filter if provided
    if gender in ('M', 'F'):
        students = students.filter(gender=gender)

    # Apply search filter if provided
    if search:
        students = students.filter(
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(other_names__icontains=search) |
            Q(admission_number__icontains=search) |
            Q(guardians__full_name__icontains=search)
        ).distinct()

    # Apply sorting
    sort_options = {
        'name': ('first_name', 'last_name'),
        '-name': ('-first_name', '-last_name'),
        'admission': ('admission_number',),
        '-admission': ('-admission_number',),
        'gender': ('gender', 'first_name'),
    }
    order_by = sort_options.get(sort, ('first_name', 'last_name'))
    students = students.order_by(*order_by)

    # Paginate
    paginator = Paginator(students, 20)  # 20 students per page
    students_page = paginator.get_page(page)

    # Get subjects that require manual assignment (auto_enroll=False)
    manual_subjects = ClassSubject.objects.filter(
        class_assigned=class_obj,
        auto_enroll=False
    ).select_related('subject', 'teacher')

    return {
        'class': class_obj,
        'students': students_page,
        'total_students': total_students,
        'search_query': search,
        'gender_filter': gender,
        'sort_by': sort,
        'gender_stats': {
            'male': male_count,
            'female': female_count,
        },
        'manual_subjects': manual_subjects,
    }


def get_teachers_tab_context(class_obj):
    """Context for the Teachers/Subjects tab with periods calculated from timetable."""
    # Get subject allocations with period counts from timetable
    subject_allocations = ClassSubject.objects.filter(
        class_assigned=class_obj
    ).select_related('subject', 'teacher').annotate(
        # Count periods: single = 1, double = 2
        timetable_periods=Sum(
            Case(
                When(timetable_entries__is_double=True, then=2),
                default=1,
                output_field=IntegerField()
            )
        )
    ).order_by('subject__name')

    return {
        'class': class_obj,
        'subject_allocations': subject_allocations
    }


def get_attendance_tab_context(class_obj):
    """Context for the Attendance tab with real data."""
    sessions = AttendanceSession.objects.filter(
        class_assigned=class_obj
    ).annotate(
        present_count=Count('records', filter=Q(records__status__in=['P', 'L'])),
        absent_count=Count('records', filter=Q(records__status='A')),
        total_count=Count('records')
    ).order_by('-date')

    # Calculate overall attendance percentage - single aggregate query
    stats = AttendanceRecord.objects.filter(
        session__class_assigned=class_obj
    ).aggregate(
        total_records=Count('id'),
        present_count=Count('id', filter=Q(status__in=['P', 'L']))
    )
    total_records = stats['total_records'] or 0
    present_count = stats['present_count'] or 0

    if total_records > 0:
        attendance_percentage = int((present_count / total_records) * 100)
    else:
        attendance_percentage = "--"

    return {
        'class': class_obj,
        'attendance_sessions': sessions,
        'attendance_percentage': attendance_percentage,
    }


def get_timetable_stats(class_obj):
    """Get timetable statistics for a class."""
    timetable_entries = TimetableEntry.objects.filter(
        class_subject__class_assigned=class_obj
    )
    return {
        'total_entries': timetable_entries.count(),
        'subjects_count': timetable_entries.values('class_subject__subject').distinct().count(),
        'teachers_count': timetable_entries.exclude(
            class_subject__teacher__isnull=True
        ).values('class_subject__teacher').distinct().count(),
    }


def get_class_detail_base_context(class_obj):
    """Get common context for class detail page."""
    # Check if class has any timetable entries (for per-lesson attendance warning)
    has_timetable = TimetableEntry.objects.filter(
        class_subject__class_assigned=class_obj
    ).exists()

    return {
        'class': class_obj,
        'timetable_stats': get_timetable_stats(class_obj),
        'has_timetable': has_timetable,
        'back_url': '/academics/classes/',
        'breadcrumbs': [
            {'label': 'Home', 'url': '/', 'icon': 'fa-solid fa-home'},
            {'label': 'Academics', 'url': '/academics/'},
            {'label': 'Classes', 'url': '/academics/classes/'},
            {'label': class_obj.name},
        ],
    }


def get_promotion_history_context(class_obj):
    """Context for showing recent enrollment/promotion activity for this class."""
    from students.models import Enrollment
    from core.models import AcademicYear

    current_year = AcademicYear.get_current()

    # Get recent enrollments for this class (incoming students)
    incoming_enrollments = Enrollment.objects.filter(
        class_assigned=class_obj
    ).select_related('student', 'academic_year', 'promoted_from').order_by(
        '-created_at'
    )[:5]

    # Get promotions/graduations out of this class
    outgoing_enrollments = Enrollment.objects.filter(
        promoted_from__class_assigned=class_obj
    ).select_related('student', 'academic_year', 'class_assigned').order_by(
        '-created_at'
    )[:5]

    # Summary stats
    if current_year:
        active_in_current_year = Enrollment.objects.filter(
            class_assigned=class_obj,
            academic_year=current_year,
            status=Enrollment.Status.ACTIVE
        ).count()

        promoted_count = Enrollment.objects.filter(
            promoted_from__class_assigned=class_obj,
            promoted_from__academic_year=current_year
        ).count()

        graduated_count = Enrollment.objects.filter(
            class_assigned=class_obj,
            academic_year=current_year,
            status=Enrollment.Status.GRADUATED
        ).count()
    else:
        active_in_current_year = 0
        promoted_count = 0
        graduated_count = 0

    return {
        'incoming_enrollments': incoming_enrollments,
        'outgoing_enrollments': outgoing_enrollments,
        'promotion_stats': {
            'active': active_in_current_year,
            'promoted': promoted_count,
            'graduated': graduated_count,
        },
        'current_year': current_year,
    }


# ============ CLASS DETAIL VIEW ============

@login_required
@teacher_or_admin_required
def class_detail(request, pk):
    """Detailed view of a specific class."""
    class_obj = get_object_or_404(Class, pk=pk)

    # Base context with timetable stats and navigation
    context = get_class_detail_base_context(class_obj)

    # Combine all tab contexts for the initial page load
    page = request.GET.get('page', 1)
    search = request.GET.get('q', '')
    gender = request.GET.get('gender', '')
    sort = request.GET.get('sort', 'name')
    context.update(get_register_tab_context(class_obj, request=request, page=page, search=search, gender=gender, sort=sort))
    context.update(get_teachers_tab_context(class_obj))
    context.update(get_attendance_tab_context(class_obj))
    context.update(get_promotion_history_context(class_obj))

    return htmx_render(
        request,
        'academics/class_detail.html',
        'academics/partials/class_detail_content.html',
        context
    )


@login_required
@teacher_or_admin_required
def class_register(request, pk):
    """Paginated student register for a class (HTMX endpoint)."""
    class_obj = get_object_or_404(Class, pk=pk)
    page = request.GET.get('page', 1)
    search = request.GET.get('q', '')
    gender = request.GET.get('gender', '')
    sort = request.GET.get('sort', 'name')

    context = get_register_tab_context(class_obj, request=request, page=page, search=search, gender=gender, sort=sort)

    return render(request, 'academics/includes/tab_register_content.html', context)


# ============ CLASS SUBJECT MANAGEMENT ============

def _get_class_subjects_queryset(class_obj):
    """Helper to get annotated class subjects queryset."""
    return ClassSubject.objects.filter(
        class_assigned=class_obj
    ).select_related('subject', 'teacher').annotate(
        timetable_periods=Sum(
            Case(
                When(timetable_entries__is_double=True, then=2),
                default=1,
                output_field=IntegerField()
            )
        )
    ).order_by('subject__name')


@admin_required
def class_subjects(request, pk):
    """View and manage subjects for a specific class."""
    class_obj = get_object_or_404(Class, pk=pk)
    subject_allocations = _get_class_subjects_queryset(class_obj)

    # Calculate stats
    teachers_assigned = subject_allocations.filter(teacher__isnull=False).count()
    total_periods = sum(alloc.timetable_periods or 0 for alloc in subject_allocations)

    context = {
        'class': class_obj,
        'subject_allocations': subject_allocations,
        'teachers_assigned': teachers_assigned,
        'total_periods': total_periods,
    }

    if request.htmx:
        return render(request, 'academics/partials/class_subjects_content.html', context)
    return render(request, 'academics/class_subjects.html', context)


@admin_required
def class_subjects_modal(request, pk):
    """Show class subjects in a modal (legacy, used by timetable page)."""
    class_obj = get_object_or_404(Class, pk=pk)
    subject_allocations = _get_class_subjects_queryset(class_obj)

    context = {
        'class': class_obj,
        'subject_allocations': subject_allocations,
    }

    return render(request, 'academics/includes/modal_subjects_content.html', context)


@admin_required
def class_subject_create(request, pk):
    """Add a subject allocation to a class."""
    class_obj = get_object_or_404(Class, pk=pk)

    # Check if editing existing allocation
    subject_id = request.GET.get('subject_id') or request.POST.get('subject_id')
    allocation = None
    if subject_id:
        allocation = get_object_or_404(ClassSubject, pk=subject_id, class_assigned=class_obj)

    if request.method == 'POST':
        form = ClassSubjectForm(request.POST, instance=allocation, class_instance=class_obj)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.class_assigned = class_obj
            obj.save()

            if request.htmx:
                # Close modal and trigger page refresh
                response = HttpResponse(status=204)
                response['HX-Trigger'] = 'closeModal, refreshSubjects'
                return response

            return redirect('academics:class_subjects', pk=pk)
    else:
        form = ClassSubjectForm(instance=allocation, class_instance=class_obj)

    return render(request, 'academics/partials/modal_subject_allocation.html', {
        'form': form,
        'class': class_obj,
        'allocation': allocation,
        'subject_id': subject_id,
    })


@admin_required
def class_subject_delete(request, class_pk, pk):
    """Delete a subject allocation from a class."""
    allocation = get_object_or_404(ClassSubject, pk=pk, class_assigned_id=class_pk)
    allocation.delete()

    if request.htmx:
        # Trigger page refresh
        response = HttpResponse(status=204)
        response['HX-Trigger'] = 'refreshSubjects'
        return response

    return redirect('academics:class_subjects', pk=class_pk)


# ============ STUDENT ENROLLMENT & ELECTIVES ============

@admin_required
def class_student_enroll(request, pk):
    """Enroll existing students into a class."""
    class_obj = get_object_or_404(Class, pk=pk)

    if request.method == 'POST':
        form = StudentEnrollmentForm(request.POST, class_instance=class_obj)
        if form.is_valid():
            students_to_add = form.cleaned_data['students']
            for student in students_to_add:
                student.current_class = class_obj
                student.save()

                # Auto-enroll in class subjects
                # SHS: core subjects only | Other levels: all subjects
                StudentSubjectEnrollment.enroll_student_in_class_subjects(
                    student, class_obj
                )

            if request.htmx:
                from django.urls import reverse
                url = reverse('academics:class_detail', args=[pk])
                # Close modal and refresh main content
                script = '''<script>
                    var dialog = document.querySelector('dialog[open]');
                    if (dialog) {
                        dialog.close();
                        htmx.ajax('GET', '%s', {target: '#main-content', swap: 'innerHTML'});
                    } else {
                        window.location.href = '%s';
                    }
                </script>''' % (url, url)
                return HttpResponse(script)

            return redirect('academics:class_detail', pk=pk)
    else:
        form = StudentEnrollmentForm(class_instance=class_obj)

    return render(request, 'academics/partials/modal_student_enroll.html', {
        'form': form, 'class': class_obj
    })


@admin_required
def class_student_remove(request, class_pk, student_pk):
    """Remove a student from a class."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    class_obj = get_object_or_404(Class, pk=class_pk)
    student = get_object_or_404(Student, pk=student_pk, current_class_id=class_pk)
    student.current_class = None
    student.save()

    if request.htmx:
        # Return updated register tab content
        context = get_register_tab_context(class_obj)
        return render(request, 'academics/includes/tab_register_content.html', context)

    return redirect('academics:class_detail', pk=class_pk)


@admin_required
def class_student_electives(request, class_pk, student_pk):
    """Manage manual subject assignments for a student (subjects with auto_enroll=False)."""
    class_obj = get_object_or_404(Class, pk=class_pk)
    student = get_object_or_404(Student, pk=student_pk, current_class=class_obj)

    # Get subjects that require manual assignment (auto_enroll=False)
    manual_subjects = ClassSubject.objects.filter(
        class_assigned=class_obj,
        auto_enroll=False
    ).select_related('subject', 'teacher')

    # Get current enrollments for manual subjects
    enrolled_ids = list(StudentSubjectEnrollment.objects.filter(
        student=student,
        class_subject__class_assigned=class_obj,
        class_subject__auto_enroll=False,
        is_active=True
    ).values_list('class_subject_id', flat=True))

    context = {
        'class': class_obj,
        'student': student,
        'manual_subjects': manual_subjects,
        'enrolled_ids': enrolled_ids,
    }

    if request.method == 'POST':
        # Get selected subject IDs
        selected_ids = request.POST.getlist('subjects')

        # Update enrollments for manual subjects only
        for class_subject in manual_subjects:
            should_be_enrolled = str(class_subject.id) in selected_ids

            if should_be_enrolled:
                enrollment, created = StudentSubjectEnrollment.objects.get_or_create(
                    student=student,
                    class_subject=class_subject,
                    defaults={'is_active': True}
                )
                if not created and not enrollment.is_active:
                    enrollment.is_active = True
                    enrollment.save()
            else:
                StudentSubjectEnrollment.objects.filter(
                    student=student,
                    class_subject=class_subject
                ).update(is_active=False)

        # Return success message with OOB swap for tab content
        tab_context = get_register_tab_context(class_obj)
        tab_context['student'] = student
        tab_context['success'] = True
        return render(request, 'academics/includes/modal_student_subjects_success.html', tab_context)

    return render(request, 'academics/includes/modal_student_subjects.html', context)


@login_required
@teacher_or_admin_required
def class_bulk_subject_assign(request, pk):
    """Bulk assign manual subjects to multiple students."""
    class_obj = get_object_or_404(Class, pk=pk)

    # Get subjects that require manual assignment (auto_enroll=False)
    manual_subjects = ClassSubject.objects.filter(
        class_assigned=class_obj,
        auto_enroll=False
    ).select_related('subject', 'teacher')

    # Get all active students in the class
    students = Student.objects.filter(
        current_class=class_obj,
        status='active'
    ).order_by('first_name', 'last_name')

    context = {
        'class': class_obj,
        'manual_subjects': manual_subjects,
        'students': students,
    }

    if request.method == 'POST':
        selected_subject_ids = request.POST.getlist('subjects')
        selected_student_ids = request.POST.getlist('students')

        if not selected_subject_ids:
            context['error'] = 'Please select at least one subject.'
            return render(request, 'academics/includes/modal_bulk_subject_assign.html', context)

        if not selected_student_ids:
            context['error'] = 'Please select at least one student.'
            return render(request, 'academics/includes/modal_bulk_subject_assign.html', context)

        # Get the selected class subjects and students
        class_subjects = manual_subjects.filter(id__in=selected_subject_ids)
        students_to_update = students.filter(id__in=selected_student_ids)

        # Create enrollments
        enrolled_count = 0
        for student in students_to_update:
            for class_subject in class_subjects:
                enrollment, created = StudentSubjectEnrollment.objects.get_or_create(
                    student=student,
                    class_subject=class_subject,
                    defaults={'is_active': True}
                )
                if created:
                    enrolled_count += 1
                elif not enrollment.is_active:
                    enrollment.is_active = True
                    enrollment.save()
                    enrolled_count += 1

        context['success'] = True
        context['enrolled_count'] = enrolled_count
        context['student_count'] = students_to_update.count()
        context['subject_count'] = class_subjects.count()
        return render(request, 'academics/includes/modal_bulk_subject_assign_success.html', context)

    return render(request, 'academics/includes/modal_bulk_subject_assign.html', context)


@admin_required
def class_bulk_electives(request, pk):
    """Bulk assign elective subjects to students (Admin only)."""
    class_obj = get_object_or_404(Class, pk=pk)

    # Get elective subjects filtered by programme
    if class_obj.programme:
        programme_subject_ids = set(
            class_obj.programme.subjects.values_list('id', flat=True)
        )
        elective_subjects = ClassSubject.objects.filter(
            class_assigned=class_obj,
            subject__is_core=False
        ).filter(
            models.Q(subject_id__in=programme_subject_ids) |
            models.Q(subject__programmes__isnull=True)
        ).select_related('subject', 'teacher').distinct()
        required_electives = class_obj.programme.required_electives
    else:
        elective_subjects = ClassSubject.objects.filter(
            class_assigned=class_obj,
            subject__is_core=False
        ).select_related('subject', 'teacher')
        required_electives = 3

    # Find students needing electives - use annotation instead of N+1 queries
    students = Student.objects.filter(
        current_class=class_obj,
        status='active'
    ).annotate(
        elective_count=Count(
            'subject_enrollments',
            filter=Q(
                subject_enrollments__class_subject__class_assigned=class_obj,
                subject_enrollments__class_subject__subject__is_core=False,
                subject_enrollments__is_active=True
            )
        )
    )

    students_needing_electives = [
        {
            'student': student,
            'current_count': student.elective_count,
            'needed': required_electives - student.elective_count
        }
        for student in students
        if student.elective_count < required_electives
    ]

    context = {
        'class': class_obj,
        'elective_subjects': elective_subjects,
        'students_needing_electives': students_needing_electives,
        'required_electives': required_electives,
    }

    if request.method == 'POST':
        # Get selected electives and students
        selected_ids = request.POST.getlist('electives')
        student_ids = request.POST.getlist('students')

        if not selected_ids:
            context['error'] = 'Please select at least one elective subject.'
            return render(request, 'academics/includes/modal_bulk_electives.html', context)

        if not student_ids:
            context['error'] = 'Please select at least one student.'
            return render(request, 'academics/includes/modal_bulk_electives.html', context)

        # Get students
        students_to_update = Student.objects.filter(pk__in=student_ids, current_class=class_obj)

        # Get class subjects
        class_subjects = ClassSubject.objects.filter(
            id__in=selected_ids,
            class_assigned=class_obj,
            subject__is_core=False
        )

        # Apply enrollments
        enrolled_count = 0
        for student in students_to_update:
            for class_subject in class_subjects:
                enrollment, created = StudentSubjectEnrollment.objects.get_or_create(
                    student=student,
                    class_subject=class_subject,
                    defaults={'is_active': True}
                )
                if created:
                    enrolled_count += 1
                elif not enrollment.is_active:
                    enrollment.is_active = True
                    enrollment.save()
                    enrolled_count += 1

        # Return success message in modal + OOB swap for tab content
        tab_context = get_register_tab_context(class_obj)
        tab_context['enrolled_count'] = enrolled_count
        tab_context['bulk_success'] = True
        # Don't auto-close modal - let user see success message and click Close
        return render(request, 'academics/includes/modal_bulk_electives_success.html', tab_context)

    return render(request, 'academics/includes/modal_bulk_electives.html', context)


# ============ SYNC SUBJECTS ============

@admin_required
def class_sync_subjects(request, pk):
    """
    Sync all students in a class with their subject enrollments.

    For SHS: Enrolls students in core subjects only.
    For other levels: Enrolls students in all class subjects.

    Useful to fix existing data or after adding new subjects to a class.
    """
    if request.method != 'POST':
        return HttpResponse(status=405)

    class_obj = get_object_or_404(Class, pk=pk)

    # Get all active students in this class
    students = Student.objects.filter(
        current_class=class_obj,
        status='active'
    )

    enrolled_count = 0
    for student in students:
        enrollments = StudentSubjectEnrollment.enroll_student_in_class_subjects(
            student, class_obj
        )
        enrolled_count += len(enrollments)

    if request.htmx:
        if enrolled_count > 0:
            messages.success(
                request,
                f'Synced subjects: {enrolled_count} enrollment(s) created for {students.count()} student(s).'
            )
        else:
            messages.info(request, 'All students already enrolled in required subjects.')

        # Return a redirect trigger
        response = HttpResponse(status=204)
        response['HX-Refresh'] = 'true'
        return response

    return redirect('academics:class_detail', pk=pk)


# ============ PROMOTION ============

@admin_required
def class_promote(request, pk):
    """Promote students from a specific class (modal-based)."""
    from students.models import Enrollment
    from core.models import AcademicYear

    class_obj = get_object_or_404(Class, pk=pk)
    current_year = AcademicYear.get_current()

    if not current_year:
        return render(request, 'academics/partials/modal_class_promote.html', {
            'class': class_obj,
            'error': 'No current academic year set.',
        })

    # Get next academic year
    next_year = AcademicYear.objects.filter(
        start_date__gt=current_year.end_date
    ).order_by('start_date').first()

    if not next_year:
        return render(request, 'academics/partials/modal_class_promote.html', {
            'class': class_obj,
            'error': 'No next academic year configured. Please create one first.',
        })

    # Determine if this is a final-year class
    is_final_year = (
        class_obj.level_type == Class.LevelType.SHS and class_obj.level_number == 3
    )

    # Get students with active enrollments in this class for current year
    students = Student.objects.filter(
        enrollments__class_assigned=class_obj,
        enrollments__academic_year=current_year,
        enrollments__status=Enrollment.Status.ACTIVE,
        status=Student.Status.ACTIVE
    ).select_related('current_class').order_by('last_name', 'first_name')

    if request.method == 'POST':
        promoted_count = 0
        repeated_count = 0
        graduated_count = 0
        errors = []

        # Wrap all promotion operations in a transaction for atomicity
        with transaction.atomic():
            for key, value in request.POST.items():
                if key.startswith('action_'):
                    student_id = key.replace('action_', '')
                    action = value

                    if action == 'skip':
                        continue

                    try:
                        student = Student.objects.get(pk=student_id)
                        current_enrollment = student.enrollments.filter(
                            academic_year=current_year,
                            class_assigned=class_obj,
                            status=Enrollment.Status.ACTIVE
                        ).first()

                        if not current_enrollment:
                            continue

                        if action == 'promote':
                            target_class_id = request.POST.get(f'target_class_{student_id}')
                            if not target_class_id:
                                errors.append(f'{student.full_name}: No target class selected')
                                continue

                            try:
                                target_class = Class.objects.get(pk=target_class_id)
                            except Class.DoesNotExist:
                                errors.append(f'{student.full_name}: Invalid target class')
                                continue

                            current_enrollment.status = Enrollment.Status.PROMOTED
                            current_enrollment.save()

                            Enrollment.objects.create(
                                student=student,
                                academic_year=next_year,
                                class_assigned=target_class,
                                status=Enrollment.Status.ACTIVE,
                                promoted_from=current_enrollment,
                            )

                            # Deactivate old class subject enrollments
                            StudentSubjectEnrollment.objects.filter(
                                student=student,
                                class_subject__class_assigned=class_obj
                            ).update(is_active=False)

                            student.current_class = target_class
                            student.save()

                            # Enroll in new class subjects
                            StudentSubjectEnrollment.enroll_student_in_class_subjects(
                                student, target_class
                            )
                            promoted_count += 1

                        elif action == 'repeat':
                            current_enrollment.status = Enrollment.Status.REPEATED
                            current_enrollment.save()

                            Enrollment.objects.create(
                                student=student,
                                academic_year=next_year,
                                class_assigned=class_obj,
                                status=Enrollment.Status.ACTIVE,
                                promoted_from=current_enrollment,
                                remarks='Repeated year',
                            )
                            repeated_count += 1

                        elif action == 'graduate':
                            current_enrollment.status = Enrollment.Status.GRADUATED
                            current_enrollment.save()

                            # Deactivate subject enrollments
                            StudentSubjectEnrollment.objects.filter(
                                student=student,
                                class_subject__class_assigned=class_obj
                            ).update(is_active=False)

                            student.status = Student.Status.GRADUATED
                            student.current_class = None
                            student.save()
                            graduated_count += 1

                    except Student.DoesNotExist:
                        errors.append(f'Student ID {student_id}: Not found')
                    except Exception as e:
                        errors.append(f'Error: {str(e)}')

        # HTMX Response: Close modal and refresh content
        if request.htmx:
            from django.urls import reverse
            url = reverse('academics:class_detail', args=[pk])
            script = '''<script>
                var dialog = document.querySelector('dialog[open]');
                if (dialog) {
                    dialog.close();
                    htmx.ajax('GET', '%s', {target: '#main-content', swap: 'innerHTML'});
                } else {
                    window.location.href = '%s';
                }
            </script>''' % (url, url)
            return HttpResponse(script)

        return redirect('academics:class_detail', pk=pk)

    # GET: Prepare form data
    all_target_classes = Class.objects.filter(is_active=True).order_by(
        'programme__name', 'level_number', 'name'
    )

    return render(request, 'academics/partials/modal_class_promote.html', {
        'class': class_obj,
        'students': students,
        'is_final_year': is_final_year,
        'current_year': current_year,
        'next_year': next_year,
        'all_classes': all_target_classes,
    })


# ============ EXPORT ============

@login_required
@teacher_or_admin_required
def class_export(request, pk):
    """Export class register to Excel."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
    from openpyxl.utils import get_column_letter
    from django.http import HttpResponse as DjangoHttpResponse
    from core.models import SchoolSettings

    class_obj = get_object_or_404(Class, pk=pk)
    students_qs = Student.objects.filter(
        current_class=class_obj,
        status='active'
    ).order_by('last_name', 'first_name')

    # Get stats upfront with single aggregate query
    student_stats = students_qs.aggregate(
        total=Count('id'),
        male_count=Count('id', filter=models.Q(gender='M')),
        female_count=Count('id', filter=models.Q(gender='F'))
    )
    students = list(students_qs)  # Convert to list since we need both iteration and count

    school = SchoolSettings.load()

    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = f"{class_obj.name} Register"

    # Styles
    header_font = Font(bold=True, size=14)
    subheader_font = Font(bold=True, size=11)
    table_header_font = Font(bold=True, size=10, color="FFFFFF")
    table_header_fill = PatternFill(start_color="4F46E5", end_color="4F46E5", fill_type="solid")
    border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )

    # School Header
    ws.merge_cells('A1:F1')
    ws['A1'] = school.display_name or request.tenant.name
    ws['A1'].font = header_font
    ws['A1'].alignment = Alignment(horizontal='center')

    # Class Info
    ws.merge_cells('A2:F2')
    ws['A2'] = f"{class_obj.name} - {class_obj.level_display}"
    ws['A2'].font = subheader_font
    ws['A2'].alignment = Alignment(horizontal='center')

    # Date
    ws.merge_cells('A3:F3')
    ws['A3'] = f"Generated: {timezone.now().strftime('%B %d, %Y')}"
    ws['A3'].alignment = Alignment(horizontal='center')

    # Empty row
    ws.append([])

    # Table Headers
    headers = ['#', 'Admission No.', 'Full Name', 'Gender', 'Guardian', 'Phone']
    ws.append(headers)
    header_row = 5

    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=header_row, column=col_num)
        cell.font = table_header_font
        cell.fill = table_header_fill
        cell.alignment = Alignment(horizontal='center')
        cell.border = border

    # Student Data
    for idx, student in enumerate(students, 1):
        row_data = [
            idx,
            student.admission_number,
            student.full_name,
            student.get_gender_display(),
            student.guardian_name or '-',
            student.guardian_phone or '-',
        ]
        ws.append(row_data)

        # Apply borders
        for col_num in range(1, len(row_data) + 1):
            cell = ws.cell(row=header_row + idx, column=col_num)
            cell.border = border
            if col_num == 1:
                cell.alignment = Alignment(horizontal='center')

    # Set column widths
    column_widths = [5, 15, 30, 10, 25, 15]
    for i, width in enumerate(column_widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = width

    # Summary row - use pre-computed stats
    summary_row = header_row + len(students) + 2
    ws.cell(row=summary_row, column=1, value=f"Total Students: {student_stats['total'] or 0}")
    ws.cell(row=summary_row, column=1).font = Font(bold=True)

    ws.cell(row=summary_row + 1, column=1, value=f"Male: {student_stats['male_count'] or 0} | Female: {student_stats['female_count'] or 0}")

    # Create response
    response = DjangoHttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f"{class_obj.name.replace(' ', '_')}_Register.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    wb.save(response)
    return response


@admin_required
def classes_bulk_export(request):
    """Export all classes to Excel with current filters applied."""
    import pandas as pd

    # Get filter parameters (same as classes_list view)
    search = request.GET.get('search', '').strip()
    level_filter = request.GET.get('level', '')

    # Get classes with student counts
    classes = Class.objects.select_related('programme', 'class_teacher').annotate(
        student_count=Count('students', filter=models.Q(students__status='active'))
    ).order_by('level_number', 'section')

    # Apply search filter
    if search:
        classes = classes.filter(
            Q(name__icontains=search) |
            Q(class_teacher__first_name__icontains=search) |
            Q(class_teacher__last_name__icontains=search) |
            Q(programme__name__icontains=search)
        )

    # Apply level filter
    if level_filter:
        classes = classes.filter(level_type=level_filter)

    # Build export data
    export_data = []
    for cls in classes:
        export_data.append({
            'Class Name': cls.name,
            'Level Type': cls.get_level_type_display(),
            'Level Number': cls.level_number,
            'Section': cls.section or '',
            'Programme': cls.programme.name if cls.programme else '',
            'Class Teacher': f"{cls.class_teacher.get_title_display()} {cls.class_teacher.full_name}" if cls.class_teacher else '',
            'Capacity': cls.capacity,
            'Current Students': cls.student_count,
            'Available Seats': cls.capacity - cls.student_count,
            'Status': 'Active' if cls.is_active else 'Inactive',
        })

    # Create Excel file
    df = pd.DataFrame(export_data)
    output = io.BytesIO()

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Classes')

        # Auto-adjust column widths
        worksheet = writer.sheets['Classes']
        for idx, col in enumerate(df.columns):
            max_length = max(
                df[col].astype(str).map(len).max() if len(df) > 0 else 0,
                len(col)
            ) + 2
            worksheet.column_dimensions[chr(65 + idx) if idx < 26 else 'A' + chr(65 + idx - 26)].width = min(max_length, 50)

    output.seek(0)

    # Generate filename with date
    filename = f"classes_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    return FileResponse(
        output,
        as_attachment=True,
        filename=filename,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


# ============ PDF GENERATION ============

@login_required
@teacher_or_admin_required
def class_detail_pdf(request, pk):
    """Generate a branded PDF class register."""
    logger = logging.getLogger(__name__)

    class_obj = get_object_or_404(Class, pk=pk)

    # Get students (ordered)
    students = Student.objects.filter(
        current_class=class_obj,
        status='active'
    ).order_by('last_name', 'first_name')

    # Get subjects
    subjects = ClassSubject.objects.filter(
        class_assigned=class_obj
    ).select_related('subject', 'teacher').order_by('subject__name')

    # Get school context with logo
    try:
        from gradebook.utils import get_school_context
        school_ctx = get_school_context(include_logo_base64=True)
    except ImportError:
        # Fallback if utils not found
        from core.models import SchoolSettings
        school_ctx = {
            'school_settings': SchoolSettings.load(),
            'logo_base64': None
        }

    # Generate PDF using WeasyPrint
    try:
        from weasyprint import HTML
        from django.template.loader import render_to_string
        from django.conf import settings as django_settings

        # Use tenant (School) for branding/contact info, SchoolSettings for operational settings
        school = school_ctx.get('school') or request.tenant
        context = {
            'class': class_obj,
            'students': students,
            'subjects': subjects,
            'school': school,
            'school_settings': school,  # Use School model which has branding fields
            'logo_base64': school_ctx.get('logo_base64'),
            'generated_at': timezone.now(),
            'generated_by': request.user,
        }

        html_string = render_to_string('academics/class_detail_pdf.html', context)
        html = HTML(string=html_string, base_url=str(django_settings.BASE_DIR))
        pdf_buffer = BytesIO()
        html.write_pdf(pdf_buffer)
        pdf_buffer.seek(0)

        response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
        filename = f"{class_obj.name.replace(' ', '_')}_Register.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    except ImportError:
        logger.error("WeasyPrint not installed")
        messages.error(request, 'PDF generation is not available. WeasyPrint is not installed.')
        return redirect('academics:class_detail', pk=pk)
    except Exception as e:
        logger.error(f"Failed to generate class PDF: {str(e)}")
        messages.error(request, f'Failed to generate PDF: {str(e)}')
        return redirect('academics:class_detail', pk=pk)
