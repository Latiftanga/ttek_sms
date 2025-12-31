import json

from django.shortcuts import redirect, get_object_or_404, render
from django.http import HttpResponse, JsonResponse
from django.db.models import Q
from django.views.decorators.http import require_POST

from academics.models import Class
from students.models import Student, Guardian, StudentGuardian
from students.forms import StudentForm, GuardianForm, StudentGuardianForm
from .utils import admin_required, htmx_render, create_enrollment_for_student


@admin_required
def index(request):
    """Student list page with search and filter."""
    students = Student.objects.select_related('current_class', 'guardian').all()

    # Search
    search = request.GET.get('search', '').strip()
    if search:
        students = students.filter(
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(other_names__icontains=search) |
            Q(admission_number__icontains=search)
        )

    # Filter by class
    class_filter = request.GET.get('class', '')
    if class_filter:
        students = students.filter(current_class_id=class_filter)

    # Filter by status
    status_filter = request.GET.get('status', '')
    if status_filter:
        students = students.filter(status=status_filter)

    context = {
        'students': students,
        'classes': Class.objects.filter(is_active=True),
        'status_choices': Student.Status.choices,
        'search': search,
        'class_filter': class_filter,
        'status_filter': status_filter,
        'form': StudentForm(),
        'guardian_form': GuardianForm(),
    }

    return htmx_render(
        request,
        'students/index.html',
        'students/partials/index_content.html',
        context
    )


@admin_required
def student_create(request):
    """Create a new student."""
    if request.method == 'GET':
        form = StudentForm()
        return htmx_render(
            request,
            'students/student_form.html',
            'students/partials/student_form_content.html',
            {
                'form': form,
                'guardian_form': GuardianForm(),
                'relationship_choices': Guardian.Relationship.choices,
            }
        )

    if request.method != 'POST':
        return HttpResponse(status=405)

    form = StudentForm(request.POST, request.FILES)
    if form.is_valid():
        student = form.save()
        # Auto-create enrollment for current academic year
        enrollment, created = create_enrollment_for_student(student)
        if created:
            student.current_class = enrollment.class_assigned
            student.save()
        # Redirect to edit page to add guardians
        return redirect('students:student_edit', pk=student.pk)

    return htmx_render(
        request,
        'students/student_form.html',
        'students/partials/student_form_content.html',
        {
            'form': form,
            'guardian_form': GuardianForm(),
            'relationship_choices': Guardian.Relationship.choices,
        }
    )


@admin_required
def student_edit(request, pk):
    """Edit a student."""
    student = get_object_or_404(Student, pk=pk)
    student_guardians = student.get_guardians_with_relationships()

    if request.method == 'GET':
        form = StudentForm(instance=student)
        return htmx_render(
            request,
            'students/student_form.html',
            'students/partials/student_form_content.html',
            {
                'form': form,
                'student': student,
                'student_guardians': student_guardians,
                'guardian_form': GuardianForm(),
                'relationship_choices': Guardian.Relationship.choices,
            }
        )

    if request.method != 'POST':
        return HttpResponse(status=405)

    form = StudentForm(request.POST, request.FILES, instance=student)
    if form.is_valid():
        student = form.save()
        # Ensure current_class is updated if changed in the form
        enrollment, created = create_enrollment_for_student(student)
        if created:
            student.current_class = enrollment.class_assigned
            student.save()
        return redirect('students:student_detail', pk=student.pk)

    return htmx_render(
        request,
        'students/student_form.html',
        'students/partials/student_form_content.html',
        {
            'form': form,
            'student': student,
            'student_guardians': student_guardians,
            'guardian_form': GuardianForm(),
            'relationship_choices': Guardian.Relationship.choices,
        }
    )


@admin_required
def student_delete(request, pk):
    """Delete a student."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    student = get_object_or_404(Student, pk=pk)
    student.delete()

    if request.htmx:
        response = HttpResponse(status=200)
        response['HX-Refresh'] = 'true'
        return response
    return redirect('students:index')


@admin_required
def student_detail(request, pk):
    """View student details."""
    student = get_object_or_404(
        Student.objects.select_related('current_class', 'user').prefetch_related(
            'student_guardians__guardian'
        ),
        pk=pk
    )
    enrollments = student.get_enrollment_history()
    student_guardians = student.get_guardians_with_relationships()
    return htmx_render(
        request,
        'students/student_detail.html',
        'students/partials/student_detail_content.html',
        {
            'student': student,
            'enrollments': enrollments,
            'student_guardians': student_guardians,
        }
    )


# ============ Student Guardian Management ============

@admin_required
@require_POST
def student_add_guardian(request, pk):
    """Add a guardian to a student."""
    student = get_object_or_404(Student, pk=pk)

    guardian_id = request.POST.get('guardian_id')
    relationship = request.POST.get('relationship', Guardian.Relationship.GUARDIAN)
    is_primary = request.POST.get('is_primary') == 'true'

    if not guardian_id:
        if request.htmx:
            return HttpResponse(
                '<div class="alert alert-error">Please select a guardian</div>',
                status=400
            )
        return redirect('students:student_edit', pk=pk)

    guardian = get_object_or_404(Guardian, pk=guardian_id)

    # Check if already linked
    if StudentGuardian.objects.filter(student=student, guardian=guardian).exists():
        if request.htmx:
            return HttpResponse(
                '<div class="alert alert-warning">This guardian is already linked to this student</div>',
                status=400
            )
        return redirect('students:student_edit', pk=pk)

    # Add guardian
    student.add_guardian(guardian, relationship, is_primary=is_primary)

    if request.htmx:
        # Return updated guardian list
        student_guardians = student.get_guardians_with_relationships()
        return render(request, 'students/partials/student_guardians_list.html', {
            'student': student,
            'student_guardians': student_guardians,
            'relationship_choices': Guardian.Relationship.choices,
        })

    return redirect('students:student_edit', pk=pk)


@admin_required
@require_POST
def student_remove_guardian(request, pk, guardian_pk):
    """Remove a guardian from a student."""
    student = get_object_or_404(Student, pk=pk)
    guardian = get_object_or_404(Guardian, pk=guardian_pk)

    student.remove_guardian(guardian)

    if request.htmx:
        # Return updated guardian list
        student_guardians = student.get_guardians_with_relationships()
        return render(request, 'students/partials/student_guardians_list.html', {
            'student': student,
            'student_guardians': student_guardians,
            'relationship_choices': Guardian.Relationship.choices,
        })

    return redirect('students:student_edit', pk=pk)


@admin_required
@require_POST
def student_set_primary_guardian(request, pk, guardian_pk):
    """Set a guardian as primary for a student."""
    student = get_object_or_404(Student, pk=pk)

    try:
        sg = StudentGuardian.objects.get(student=student, guardian_id=guardian_pk)
        sg.is_primary = True
        sg.save()  # This will unset other primary guardians
    except StudentGuardian.DoesNotExist:
        pass

    if request.htmx:
        student_guardians = student.get_guardians_with_relationships()
        return render(request, 'students/partials/student_guardians_list.html', {
            'student': student,
            'student_guardians': student_guardians,
            'relationship_choices': Guardian.Relationship.choices,
        })

    return redirect('students:student_edit', pk=pk)


@admin_required
@require_POST
def student_update_guardian_relationship(request, pk, guardian_pk):
    """Update the relationship type for a student-guardian link."""
    student = get_object_or_404(Student, pk=pk)
    relationship = request.POST.get('relationship', Guardian.Relationship.GUARDIAN)

    try:
        sg = StudentGuardian.objects.get(student=student, guardian_id=guardian_pk)
        sg.relationship = relationship
        sg.save()
    except StudentGuardian.DoesNotExist:
        pass

    if request.htmx:
        student_guardians = student.get_guardians_with_relationships()
        return render(request, 'students/partials/student_guardians_list.html', {
            'student': student,
            'student_guardians': student_guardians,
            'relationship_choices': Guardian.Relationship.choices,
        })

    return redirect('students:student_edit', pk=pk)
