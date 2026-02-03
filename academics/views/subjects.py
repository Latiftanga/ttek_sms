"""Subject and Subject Template management views."""
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.db.models import Count, Q
from django.contrib import messages

from ..models import Subject, SubjectTemplate, Class
from ..forms import SubjectForm, SubjectTemplateForm, ApplyTemplateForm
from .base import admin_required


def get_subjects_list_context():
    """Get context for subjects list with stats."""
    subjects = Subject.objects.prefetch_related('programmes').annotate(
        class_count=Count(
            'class_allocations',
            filter=Q(class_allocations__class_assigned__is_active=True)
        ),
        student_count=Count(
            'class_allocations__class_assigned__students',
            filter=Q(
                class_allocations__class_assigned__is_active=True,
                class_allocations__class_assigned__students__status='active'
            )
        )
    ).order_by('-is_core', 'name')

    return {'subjects': subjects}


@admin_required
def subject_create(request):
    """Create a new subject."""
    if request.method == 'GET':
        # Return fresh form for modal
        form = SubjectForm()
        return render(request, 'academics/partials/modal_subject_form.html', {
            'form': form,
            'is_create': True,
        })

    if request.method != 'POST':
        return HttpResponse(status=405)

    form = SubjectForm(request.POST)
    if form.is_valid():
        form.save()
        if request.htmx:
            response = render(request, 'academics/partials/subjects_list.html', get_subjects_list_context())
            response['HX-Trigger'] = 'closeModal'
            response['HX-Reswap'] = 'outerHTML'
            response['HX-Retarget'] = '#subjects-container'
            return response
        return redirect('academics:index')

    # Validation error - show form with errors in modal
    if request.htmx:
        response = render(request, 'academics/partials/modal_subject_form.html', {
            'form': form,
            'is_create': True,
        })
        response.status_code = 422
        return response
    return redirect('academics:index')


@admin_required
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
            response['HX-Reswap'] = 'outerHTML'
            response['HX-Retarget'] = '#subjects-container'
            return response
        return redirect('academics:index')

    # Validation error - show form with errors in modal
    if request.htmx:
        response = render(request, 'academics/partials/modal_subject_form.html', {
            'form': form,
            'subject': subject,
        })
        response.status_code = 422
        return response
    return redirect('academics:index')


@admin_required
def subject_delete(request, pk):
    """Delete a subject."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    subject = get_object_or_404(Subject, pk=pk)
    subject.delete()

    if request.htmx:
        return render(request, 'academics/partials/subjects_list.html', get_subjects_list_context())
    return redirect('academics:index')


# --- Subject Template Views ---

def get_templates_list_context():
    """Get context for templates list."""
    templates = SubjectTemplate.objects.prefetch_related('subjects').filter(is_active=True).order_by('name')
    return {'templates': templates}


@admin_required
def template_create(request):
    """Create a new subject template."""
    # Detect if called from class detail context (apply template modal)
    from_class = request.GET.get('from_class')
    modal_target = '#modal-container' if from_class else '#modal-content'

    if request.method == 'GET':
        form = SubjectTemplateForm()
        return render(request, 'academics/partials/modal_template_form.html', {
            'form': form,
            'is_create': True,
            'selected_subject_ids': [],
            'modal_target': modal_target,
            'from_class': from_class,
        })

    if request.method != 'POST':
        return HttpResponse(status=405)

    form = SubjectTemplateForm(request.POST)
    if form.is_valid():
        template = form.save()
        if request.htmx:
            # If created from class detail, return to apply template modal
            if from_class:
                class_obj = get_object_or_404(Class, pk=from_class)
                apply_form = ApplyTemplateForm(class_obj=class_obj)
                response = render(request, 'academics/partials/modal_apply_template.html', {
                    'form': apply_form,
                    'class': class_obj,
                    'has_templates': True,
                    'template_created': template.name,
                })
                return response
            # Otherwise update templates list on index page
            response = render(request, 'academics/partials/templates_list.html', get_templates_list_context())
            response['HX-Trigger'] = 'closeModal'
            response['HX-Reswap'] = 'outerHTML'
            response['HX-Retarget'] = '#templates-container'
            return response
        return redirect('academics:index')

    # Validation error - show form with errors
    selected_subject_ids = request.POST.getlist('subjects')
    context = {
        'form': form,
        'is_create': True,
        'selected_subject_ids': selected_subject_ids,
        'modal_target': modal_target,
        'from_class': from_class,
    }
    if request.htmx:
        response = render(request, 'academics/partials/modal_template_form.html', context)
        response.status_code = 422
        return response

    return render(request, 'academics/partials/modal_template_form.html', context)


@admin_required
def template_edit(request, pk):
    """Edit an existing subject template."""
    template = get_object_or_404(SubjectTemplate, pk=pk)
    from_class = request.GET.get('from_class') or request.POST.get('from_class')
    modal_target = '#modal-container' if from_class else '#modal-content'

    if request.method == 'GET':
        form = SubjectTemplateForm(instance=template)
        selected_subject_ids = [str(s.pk) for s in template.subjects.all()]
        return render(request, 'academics/partials/modal_template_form.html', {
            'form': form,
            'template': template,
            'is_create': False,
            'selected_subject_ids': selected_subject_ids,
            'modal_target': modal_target,
            'from_class': from_class,
        })

    if request.method != 'POST':
        return HttpResponse(status=405)

    form = SubjectTemplateForm(request.POST, instance=template)
    if form.is_valid():
        form.save()
        if request.htmx:
            # If edited from class detail, return to apply template modal
            if from_class:
                class_obj = get_object_or_404(Class, pk=from_class)
                apply_form = ApplyTemplateForm(class_obj=class_obj)
                return render(request, 'academics/partials/modal_apply_template.html', {
                    'form': apply_form,
                    'class': class_obj,
                    'has_templates': True,
                    'template_updated': template.name,
                })
            # Otherwise update templates list on index page
            response = render(request, 'academics/partials/templates_list.html', get_templates_list_context())
            response['HX-Trigger'] = 'closeModal'
            response['HX-Reswap'] = 'outerHTML'
            response['HX-Retarget'] = '#templates-container'
            return response
        return redirect('academics:index')

    # Validation error - show form with errors
    selected_subject_ids = request.POST.getlist('subjects')
    context = {
        'form': form,
        'template': template,
        'is_create': False,
        'selected_subject_ids': selected_subject_ids,
        'modal_target': modal_target,
        'from_class': from_class,
    }
    if request.htmx:
        response = render(request, 'academics/partials/modal_template_form.html', context)
        response.status_code = 422
        return response

    return render(request, 'academics/partials/modal_template_form.html', context)


@admin_required
def template_delete(request, pk):
    """Delete a subject template."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    template = get_object_or_404(SubjectTemplate, pk=pk)
    template.delete()

    if request.htmx:
        return render(request, 'academics/partials/templates_list.html', get_templates_list_context())
    return redirect('academics:index')


@admin_required
def apply_template(request, pk):
    """Apply a subject template to a class."""
    class_obj = get_object_or_404(Class, pk=pk)

    if request.method == 'POST':
        form = ApplyTemplateForm(request.POST, class_obj=class_obj)
        if form.is_valid():
            template = form.cleaned_data['template']
            created, skipped = template.apply_to_class(class_obj)

            if request.htmx:
                # Close modal and trigger page refresh
                response = HttpResponse(status=204)
                response['HX-Trigger'] = 'closeModal, refreshSubjects'
                return response
            messages.success(request, f'Template applied: {created} subjects added, {skipped} already existed.')
            return redirect('academics:class_subjects', pk=pk)
    else:
        form = ApplyTemplateForm(class_obj=class_obj)

    # Check if any templates are available
    available_templates = form.fields['template'].queryset.exists()

    return render(request, 'academics/partials/modal_apply_template.html', {
        'form': form,
        'class': class_obj,
        'has_templates': available_templates,
    })


