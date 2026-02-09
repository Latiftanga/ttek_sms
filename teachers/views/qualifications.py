"""
Qualification views for teachers.

Provides CRUD operations for academic qualification records (admin or teacher's own).
"""
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.http import HttpResponse
from django.template.loader import render_to_string

from teachers.models import Teacher, Qualification
from teachers.forms import QualificationForm
from .utils import admin_or_owner, htmx_render


@admin_or_owner
def qualification_list(request, pk):
    """List all qualifications for a teacher."""
    teacher = get_object_or_404(Teacher, pk=pk)
    qualifications = Qualification.objects.filter(teacher=teacher)

    context = {
        'teacher': teacher,
        'qualifications': qualifications,
    }

    return htmx_render(
        request,
        'teachers/partials/tab_qualifications.html',
        'teachers/partials/tab_qualifications.html',
        context
    )


@admin_or_owner
def qualification_create(request, pk):
    """Create a new qualification for a teacher."""
    teacher = get_object_or_404(Teacher, pk=pk)

    if request.method == 'POST':
        form = QualificationForm(request.POST)
        if form.is_valid():
            qualification = form.save(commit=False)
            qualification.teacher = teacher
            qualification.save()
            messages.success(request, f"Added qualification: {qualification.title}")

            if request.htmx:
                qualifications = Qualification.objects.filter(teacher=teacher)
                html = render_to_string(
                    'teachers/partials/tab_qualifications.html',
                    {'teacher': teacher, 'qualifications': qualifications},
                    request
                )
                response = HttpResponse(html)
                response['HX-Trigger'] = 'closeModal'
                return response
            return redirect('teachers:teacher_detail', pk=pk)
    else:
        form = QualificationForm()

    context = {
        'form': form,
        'teacher': teacher,
        'is_edit': False,
    }

    return htmx_render(
        request,
        'teachers/partials/modal_qualification_form.html',
        'teachers/partials/modal_qualification_form.html',
        context
    )


@admin_or_owner
def qualification_edit(request, pk, qual_pk):
    """Edit a qualification."""
    teacher = get_object_or_404(Teacher, pk=pk)
    qualification = get_object_or_404(Qualification, pk=qual_pk, teacher=teacher)

    if request.method == 'POST':
        form = QualificationForm(request.POST, instance=qualification)
        if form.is_valid():
            form.save()
            messages.success(request, f"Updated qualification: {qualification.title}")

            if request.htmx:
                qualifications = Qualification.objects.filter(teacher=teacher)
                html = render_to_string(
                    'teachers/partials/tab_qualifications.html',
                    {'teacher': teacher, 'qualifications': qualifications},
                    request
                )
                response = HttpResponse(html)
                response['HX-Trigger'] = 'closeModal'
                return response
            return redirect('teachers:teacher_detail', pk=pk)
    else:
        form = QualificationForm(instance=qualification)

    context = {
        'form': form,
        'teacher': teacher,
        'qualification': qualification,
        'is_edit': True,
    }

    return htmx_render(
        request,
        'teachers/partials/modal_qualification_form.html',
        'teachers/partials/modal_qualification_form.html',
        context
    )


@admin_or_owner
def qualification_delete(request, pk, qual_pk):
    """Delete a qualification."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    teacher = get_object_or_404(Teacher, pk=pk)
    qualification = get_object_or_404(Qualification, pk=qual_pk, teacher=teacher)

    title = qualification.title
    qualification.delete()
    messages.success(request, f"Deleted qualification: {title}")

    if request.htmx:
        qualifications = Qualification.objects.filter(teacher=teacher)
        return htmx_render(
            request,
            'teachers/partials/tab_qualifications.html',
            'teachers/partials/tab_qualifications.html',
            {'teacher': teacher, 'qualifications': qualifications}
        )

    return redirect('teachers:teacher_detail', pk=pk)
