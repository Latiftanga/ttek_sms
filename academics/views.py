from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.utils import timezone
from django.db import models

from .models import Programme, Class, Subject
from .forms import ProgrammeForm, ClassForm, SubjectForm, StudentEnrollmentForm
from students.models import Student
from .models import ClassSubject, AttendanceSession, AttendanceRecord
from .forms import ClassSubjectForm


def htmx_render(request, full_template, partial_template, context=None):
    """Render full template for regular requests, partial for HTMX requests."""
    context = context or {}
    template = partial_template if request.htmx else full_template
    return render(request, template, context)




def get_academics_context():
    """Get common context for academics page."""
    from django.db.models import Count

    # Get classes with student counts, grouped by level
    classes = Class.objects.select_related('programme', 'class_teacher').annotate(
        student_count=Count('students', filter=models.Q(students__status='active'))
    ).order_by('level_number', 'section')

    # Group classes by level type with stats
    classes_by_level = {
        'kg': {'classes': [], 'student_count': 0},
        'primary': {'classes': [], 'student_count': 0},
        'jhs': {'classes': [], 'student_count': 0},
        'shs': {'classes': [], 'student_count': 0},
    }
    for cls in classes:
        if cls.level_type in classes_by_level:
            classes_by_level[cls.level_type]['classes'].append(cls)
            classes_by_level[cls.level_type]['student_count'] += cls.student_count

    # Stats
    programmes = Programme.objects.all()
    subjects = Subject.objects.prefetch_related('programmes').all()
    total_students = Student.objects.filter(status='active').count()

    return {
        'programmes': programmes,
        'classes': classes,
        'classes_by_level': classes_by_level,
        'subjects': subjects,
        'stats': {
            'total_classes': classes.count(),
            'total_subjects': subjects.count(),
            'total_programmes': programmes.count(),
            'total_students': total_students,
        },
        'programme_form': ProgrammeForm(),
        'class_form': ClassForm(),
        'subject_form': SubjectForm(),
    }


@login_required
def index(request):
    """Academics dashboard page."""
    context = get_academics_context()

    return htmx_render(
        request,
        'academics/index.html',
        'academics/partials/index_content.html',
        context
    )


# ============ PROGRAMME VIEWS ============

def get_programmes_list_context():
    """Get context for programmes list."""
    return {'programmes': Programme.objects.all()}


@login_required
def programme_create(request):
    """Create a new programme."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    form = ProgrammeForm(request.POST)
    if form.is_valid():
        form.save()
        if request.htmx:
            response = render(request, 'academics/partials/programmes_list.html', get_programmes_list_context())
            response['HX-Trigger'] = 'closeModal'
            return response
        return redirect('academics:index')

    # Validation error (422 keeps modal open)
    if request.htmx:
        response = render(request, 'academics/partials/modal_programme_form.html', {
            'form': form,
            'is_create': True,
        })
        response.status_code = 422
        return response
    return redirect('academics:index')


@login_required
def programme_edit(request, pk):
    """Edit a programme."""
    programme = get_object_or_404(Programme, pk=pk)

    if request.method == 'GET':
        form = ProgrammeForm(instance=programme)
        return render(request, 'academics/partials/modal_programme_form.html', {
            'form': form,
            'programme': programme,
        })

    if request.method != 'POST':
        return HttpResponse(status=405)

    form = ProgrammeForm(request.POST, instance=programme)
    if form.is_valid():
        form.save()
        if request.htmx:
            response = render(request, 'academics/partials/programmes_list.html', get_programmes_list_context())
            response['HX-Trigger'] = 'closeModal'
            return response
        return redirect('academics:index')

    # Validation error (422 keeps modal open)
    if request.htmx:
        response = render(request, 'academics/partials/modal_programme_form.html', {
            'form': form,
            'programme': programme,
        })
        response.status_code = 422
        return response
    return redirect('academics:index')


@login_required
def programme_delete(request, pk):
    """Delete a programme."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    programme = get_object_or_404(Programme, pk=pk)
    programme.delete()

    if request.htmx:
        return render(request, 'academics/partials/programmes_list.html', get_programmes_list_context())
    return redirect('academics:index')


# ============ CLASS VIEWS ============

def get_classes_list_context():
    """Get context for classes list."""
    from django.db.models import Count
    classes = Class.objects.select_related('programme', 'class_teacher').annotate(
        student_count=Count('students', filter=models.Q(students__status='active'))
    ).order_by('level_number', 'section')
    return {'classes': classes}


@login_required
def class_create(request):
    """Create a new class."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    form = ClassForm(request.POST)
    if form.is_valid():
        form.save()
        if request.htmx:
            response = render(request, 'academics/partials/classes_list.html', get_classes_list_context())
            response['HX-Trigger'] = 'closeModal'
            return response
        return redirect('academics:index')

    # Validation error (422 keeps modal open)
    if request.htmx:
        response = render(request, 'academics/partials/modal_class_form.html', {
            'form': form,
            'is_create': True,
        })
        response.status_code = 422
        return response
    return redirect('academics:index')


@login_required
def class_edit(request, pk):
    """Edit a class."""
    cls = get_object_or_404(Class, pk=pk)

    # Check if editing from class detail page
    current_url = request.headers.get('HX-Current-URL', '')
    is_detail_page = f'/academics/classes/{pk}/' in current_url

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
        form.save()
        if request.htmx:
            if is_detail_page:
                # On detail page, refresh to show updated data
                response = HttpResponse(status=204)
                response['HX-Refresh'] = 'true'
                return response
            else:
                # On index page, update the classes list
                response = render(request, 'academics/partials/classes_list.html', get_classes_list_context())
                response['HX-Trigger'] = 'closeModal'
                return response
        return redirect('academics:index')

    # Validation error (422 keeps modal open)
    if request.htmx:
        response = render(request, 'academics/partials/modal_class_form.html', {
            'form': form,
            'class': cls,
            'is_detail_page': is_detail_page,
        })
        response.status_code = 422
        return response
    return redirect('academics:index')


@login_required
def class_delete(request, pk):
    """Delete a class."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    cls = get_object_or_404(Class, pk=pk)
    cls.delete()

    if request.htmx:
        return render(request, 'academics/partials/classes_list.html', get_classes_list_context())
    return redirect('academics:index')


# ============ SUBJECT VIEWS ============

def get_subjects_list_context():
    """Get context for subjects list."""
    return {'subjects': Subject.objects.prefetch_related('programmes').all()}


@login_required
def subject_create(request):
    """Create a new subject."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    form = SubjectForm(request.POST)
    if form.is_valid():
        form.save()
        if request.htmx:
            response = render(request, 'academics/partials/subjects_list.html', get_subjects_list_context())
            response['HX-Trigger'] = 'closeModal'
            return response
        return redirect('academics:index')

    # Validation error (422 keeps modal open)
    if request.htmx:
        response = render(request, 'academics/partials/modal_subject_form.html', {
            'form': form,
            'is_create': True,
        })
        response.status_code = 422
        return response
    return redirect('academics:index')


@login_required
def subject_edit(request, pk):
    """Edit a subject."""
    subject = get_object_or_404(Subject, pk=pk)

    if request.method == 'GET':
        form = SubjectForm(instance=subject)
        return render(request, 'academics/partials/modal_subject_form.html', {
            'form': form,
            'subject': subject,
        })

    if request.method != 'POST':
        return HttpResponse(status=405)

    form = SubjectForm(request.POST, instance=subject)
    if form.is_valid():
        form.save()
        if request.htmx:
            response = render(request, 'academics/partials/subjects_list.html', get_subjects_list_context())
            response['HX-Trigger'] = 'closeModal'
            return response
        return redirect('academics:index')

    # Validation error (422 keeps modal open)
    if request.htmx:
        response = render(request, 'academics/partials/modal_subject_form.html', {
            'form': form,
            'subject': subject,
        })
        response.status_code = 422
        return response
    return redirect('academics:index')


@login_required
def subject_delete(request, pk):
    """Delete a subject."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    subject = get_object_or_404(Subject, pk=pk)
    subject.delete()

    if request.htmx:
        return render(request, 'academics/partials/subjects_list.html', get_subjects_list_context())
    return redirect('academics:index')



def get_register_tab_context(class_obj):
    """Context for the Students/Register tab."""
    students = Student.objects.filter(
        current_class=class_obj, 
        status='active'
    ).order_by('first_name')
    return {
        'class': class_obj,
        'students': students
    }

def get_teachers_tab_context(class_obj):
    """Context for the Teachers/Subjects tab."""
    subject_allocations = ClassSubject.objects.filter(
        class_assigned=class_obj
    ).select_related('subject', 'teacher').order_by('subject__name')
    return {
        'class': class_obj,
        'subject_allocations': subject_allocations
    }

def get_attendance_tab_context(class_obj):
    """Context for the Attendance tab with real data."""
    from django.db.models import Count, Q

    sessions = AttendanceSession.objects.filter(
        class_assigned=class_obj
    ).annotate(
        present_count=Count('records', filter=Q(records__status__in=['P', 'L'])),
        absent_count=Count('records', filter=Q(records__status='A')),
        total_count=Count('records')
    ).order_by('-date')

    # Calculate overall attendance percentage
    total_records = AttendanceRecord.objects.filter(
        session__class_assigned=class_obj
    ).count()
    present_count = AttendanceRecord.objects.filter(
        session__class_assigned=class_obj,
        status__in=['P', 'L']  # Present or Late counts as present
    ).count()

    if total_records > 0:
        attendance_percentage = int((present_count / total_records) * 100)
    else:
        attendance_percentage = "--"

    return {
        'class': class_obj,
        'attendance_sessions': sessions,
        'attendance_percentage': attendance_percentage,
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

# --- Main Detail View ---

@login_required
def class_detail(request, pk):
    """Detailed view of a specific class."""
    class_obj = get_object_or_404(Class, pk=pk)

    # Base context
    context = {
        'class': class_obj,
    }

    # Combine all tab contexts for the initial page load
    context.update(get_register_tab_context(class_obj))
    context.update(get_teachers_tab_context(class_obj))
    context.update(get_attendance_tab_context(class_obj))
    context.update(get_promotion_history_context(class_obj))

    return htmx_render(
        request,
        'academics/class_detail.html',
        'academics/partials/class_detail_content.html',
        context
    )

# --- Action Views (Using Helpers) ---
@login_required
def class_subject_create(request, pk):
    class_obj = get_object_or_404(Class, pk=pk)
    
    if request.method == 'POST':
        form = ClassSubjectForm(request.POST, class_instance=class_obj)
        if form.is_valid():
            allocation = form.save(commit=False)
            allocation.class_assigned = class_obj
            allocation.save()
            
            # HTMX Success: Update sidebar card + modal content
            if request.htmx:
                context = {'class': class_obj}
                context.update(get_teachers_tab_context(class_obj))

                # 1. Sidebar Card (OOB)
                sidebar_html = render(request, 'academics/partials/card_subjects_sidebar.html', context).content.decode('utf-8')
                sidebar_html = sidebar_html.replace('id="card-subjects"', 'id="card-subjects" hx-swap-oob="true"')

                # 2. Modal Content (OOB) - for "View All" modal
                modal_html = render(request, 'academics/includes/tab_teachers_content.html', context).content.decode('utf-8')
                modal_oob = f'<div id="tab-teachers" hx-swap-oob="true">{modal_html}</div>'

                script = '<script>modal_edit.close()</script>'

                return HttpResponse(sidebar_html + modal_oob + script)
                
            return redirect('academics:class_detail', pk=pk)
    else:
        form = ClassSubjectForm(class_instance=class_obj)
        
    return render(request, 'academics/partials/modal_subject_allocation.html', {
        'form': form, 'class': class_obj
    })

@login_required
def class_subject_delete(request, class_pk, pk):
    allocation = get_object_or_404(ClassSubject, pk=pk, class_assigned_id=class_pk)
    allocation.delete()

    if request.htmx:
        class_obj = get_object_or_404(Class, pk=class_pk)
        context = {'class': class_obj}
        context.update(get_teachers_tab_context(class_obj))

        # 1. Sidebar Card (OOB)
        sidebar_html = render(request, 'academics/partials/card_subjects_sidebar.html', context).content.decode('utf-8')
        sidebar_html = sidebar_html.replace('id="card-subjects"', 'id="card-subjects" hx-swap-oob="true"')

        # 2. Modal Content (direct response to #tab-teachers)
        modal_html = render(request, 'academics/includes/tab_teachers_content.html', context).content.decode('utf-8')

        return HttpResponse(modal_html + sidebar_html)
        
    return redirect('academics:class_detail', pk=class_pk)


@login_required
def class_student_enroll(request, pk):
    """Enroll existing students into a class."""
    class_obj = get_object_or_404(Class, pk=pk)
    
    if request.method == 'POST':
        form = StudentEnrollmentForm(request.POST, class_instance=class_obj)
        if form.is_valid():
            students_to_add = form.cleaned_data['students']
            # Bulk enrollment
            for student in students_to_add:
                student.current_class = class_obj
                student.save()
            
            # HTMX Success Response
            if request.htmx:
                # 1. Get fresh context (merge register + attendance for stats card)
                context = get_register_tab_context(class_obj)
                context.update(get_attendance_tab_context(class_obj))

                # 2. Render the Student List (OOB swap)
                tab_html = render(request, 'academics/includes/tab_register_content.html', context).content.decode('utf-8')
                tab_oob = f'<div id="tab-register" class="p-4" hx-swap-oob="true">{tab_html}</div>'

                # 3. Render the Stats Card (OOB Swap)
                stats_html = render(request, 'academics/partials/card_class_stats.html', context).content.decode('utf-8')
                stats_html = stats_html.replace('id="class-stats"', 'id="class-stats" hx-swap-oob="true"')

                # 4. Close Modal Script
                script = "<script>modal_edit.close()</script>"

                return HttpResponse(tab_oob + stats_html + script)
                
            return redirect('academics:class_detail', pk=pk)
    else:
        form = StudentEnrollmentForm(class_instance=class_obj)
        
    return render(request, 'academics/partials/modal_student_enroll.html', {
        'form': form, 'class': class_obj
    })


@login_required
def class_student_remove(request, class_pk, student_pk):
    """Remove a student from a class."""
    if request.method != 'POST':
        return HttpResponse(status=405)
        
    student = get_object_or_404(Student, pk=student_pk, current_class_id=class_pk)
    student.current_class = None
    student.save()
    
    if request.htmx:
        class_obj = get_object_or_404(Class, pk=class_pk)
        context = get_register_tab_context(class_obj)
        context.update(get_attendance_tab_context(class_obj))

        # 1. Render Updated List (direct to target)
        tab_html = render(request, 'academics/includes/tab_register_content.html', context).content.decode('utf-8')

        # 2. Render Updated Stats (OOB Swap)
        stats_html = render(request, 'academics/partials/card_class_stats.html', context).content.decode('utf-8')
        stats_html = stats_html.replace('id="class-stats"', 'id="class-stats" hx-swap-oob="true"')

        return HttpResponse(tab_html + stats_html)

    return redirect('academics:class_detail', pk=class_pk)


# --- 2. Take Attendance Action ---
@login_required
def class_attendance_take(request, pk):
    """
    Opens the attendance sheet for a specific date (defaults to today).
    Handles saving the records.
    """
    class_obj = get_object_or_404(Class, pk=pk)
    target_date = timezone.now().date() # For now, default to today
    
    # Check if session exists
    session, created = AttendanceSession.objects.get_or_create(
        class_assigned=class_obj,
        date=target_date
    )

    if request.method == 'POST':
        # Process the form submission manually for grid data
        # Data format: "status_STUDENTID" : "STATUS_CODE"
        
        students = Student.objects.filter(current_class=class_obj, status='active')
        
        for student in students:
            status_key = f"status_{student.id}"
            new_status = request.POST.get(status_key, AttendanceRecord.Status.PRESENT)
            
            AttendanceRecord.objects.update_or_create(
                session=session,
                student=student,
                defaults={'status': new_status}
            )
            
        # HTMX Success: Update Sidebar + Stats
        if request.htmx:
            context = get_register_tab_context(class_obj)
            context.update(get_attendance_tab_context(class_obj))

            # 1. Attendance Sidebar Card (OOB)
            attendance_html = render(request, 'academics/partials/card_attendance_sidebar.html', context).content.decode('utf-8')
            attendance_html = attendance_html.replace('id="card-attendance"', 'id="card-attendance" hx-swap-oob="true"')

            # 2. Stats Card (OOB)
            stats_html = render(request, 'academics/partials/card_class_stats.html', context).content.decode('utf-8')
            stats_html = stats_html.replace('id="class-stats"', 'id="class-stats" hx-swap-oob="true"')

            script = "<script>modal_edit.close()</script>"
            return HttpResponse(attendance_html + stats_html + script)
            
        return redirect('academics:class_detail', pk=pk)

    # GET Request: Prepare data for the form
    students = Student.objects.filter(current_class=class_obj, status='active').order_by('first_name')
    records = {r.student_id: r.status for r in session.records.all()}
    
    # Combine student + their status
    student_list = []
    for student in students:
        student_list.append({
            'obj': student,
            'status': records.get(student.id, 'P') # Default to Present if new
        })

    return render(request, 'academics/partials/modal_attendance_take.html', {
        'class': class_obj,
        'session': session,
        'student_list': student_list,
        'date': target_date
    })


@login_required
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
        from django.contrib import messages

        promoted_count = 0
        repeated_count = 0
        graduated_count = 0
        errors = []

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

                        student.current_class = target_class
                        student.save()
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

                        student.status = Student.Status.GRADUATED
                        student.current_class = None
                        student.save()
                        graduated_count += 1

                except Student.DoesNotExist:
                    errors.append(f'Student ID {student_id}: Not found')
                except Exception as e:
                    errors.append(f'Error: {str(e)}')

        # HTMX Response with OOB updates
        if request.htmx:
            context = get_register_tab_context(class_obj)
            context.update(get_attendance_tab_context(class_obj))
            context.update(get_promotion_history_context(class_obj))

            # 1. Student Register (OOB)
            tab_html = render(request, 'academics/includes/tab_register_content.html', context).content.decode('utf-8')
            tab_oob = f'<div id="tab-register" class="p-4" hx-swap-oob="true">{tab_html}</div>'

            # 2. Stats Card (OOB)
            stats_html = render(request, 'academics/partials/card_class_stats.html', context).content.decode('utf-8')
            stats_html = stats_html.replace('id="class-stats"', 'id="class-stats" hx-swap-oob="true"')

            # 3. Promotion History Card (OOB)
            promo_html = render(request, 'academics/partials/card_promotion_history.html', context).content.decode('utf-8')
            promo_html = promo_html.replace('id="card-promotion"', 'id="card-promotion" hx-swap-oob="true"')

            # Build result message
            results = []
            if promoted_count:
                results.append(f'{promoted_count} promoted')
            if repeated_count:
                results.append(f'{repeated_count} repeating')
            if graduated_count:
                results.append(f'{graduated_count} graduated')

            result_msg = ', '.join(results) if results else 'No changes made'

            # Success modal content
            success_html = f'''
            <div class="text-center py-6">
                <div class="text-5xl text-success mb-4"><i class="fa-solid fa-check-circle"></i></div>
                <h3 class="text-lg font-bold mb-2">Promotion Complete</h3>
                <p class="text-base-content/70">{result_msg}</p>
                <button type="button" class="btn btn-primary mt-4" onclick="modal_edit.close()">Close</button>
            </div>
            '''

            return HttpResponse(success_html + tab_oob + stats_html + promo_html)

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


@login_required
def class_attendance_edit(request, pk, session_pk):
    """Edit an existing attendance session."""
    class_obj = get_object_or_404(Class, pk=pk)
    session = get_object_or_404(AttendanceSession, pk=session_pk, class_assigned=class_obj)

    if request.method == 'POST':
        students = Student.objects.filter(current_class=class_obj, status='active')

        for student in students:
            status_key = f"status_{student.id}"
            new_status = request.POST.get(status_key, AttendanceRecord.Status.PRESENT)

            AttendanceRecord.objects.update_or_create(
                session=session,
                student=student,
                defaults={'status': new_status}
            )

        if request.htmx:
            context = get_register_tab_context(class_obj)
            context.update(get_attendance_tab_context(class_obj))

            # 1. Attendance Sidebar Card (OOB)
            attendance_html = render(request, 'academics/partials/card_attendance_sidebar.html', context).content.decode('utf-8')
            attendance_html = attendance_html.replace('id="card-attendance"', 'id="card-attendance" hx-swap-oob="true"')

            # 2. Stats Card (OOB)
            stats_html = render(request, 'academics/partials/card_class_stats.html', context).content.decode('utf-8')
            stats_html = stats_html.replace('id="class-stats"', 'id="class-stats" hx-swap-oob="true"')

            script = "<script>modal_edit.close()</script>"
            return HttpResponse(attendance_html + stats_html + script)

        return redirect('academics:class_detail', pk=pk)

    # GET Request: Load existing records
    students = Student.objects.filter(current_class=class_obj, status='active').order_by('first_name')
    records = {r.student_id: r.status for r in session.records.all()}

    student_list = []
    for student in students:
        student_list.append({
            'obj': student,
            'status': records.get(student.id, 'P')
        })

    return render(request, 'academics/partials/modal_attendance_take.html', {
        'class': class_obj,
        'session': session,
        'student_list': student_list,
        'date': session.date,
        'is_edit': True
    })