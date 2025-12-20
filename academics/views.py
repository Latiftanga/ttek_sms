from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse

from .models import Programme, Class, Subject
from .forms import ProgrammeForm, ClassForm, SubjectForm


def htmx_render(request, full_template, partial_template, context=None):
    """Render full template for regular requests, partial for HTMX requests."""
    context = context or {}
    template = partial_template if request.htmx else full_template
    return render(request, template, context)


def get_academics_context():
    """Get common context for academics page."""
    return {
        'programmes': Programme.objects.all(),
        'classes': Class.objects.select_related('programme').all(),
        'subjects': Subject.objects.prefetch_related('programmes').all(),
        'programme_form': ProgrammeForm(),
        'class_form': ClassForm(),
        'subject_form': SubjectForm(),
    }


@login_required
def index(request):
    """Academics overview page."""
    context = get_academics_context()
    return htmx_render(
        request,
        'academics/index.html',
        'academics/partials/index_content.html',
        context
    )


# ============ PROGRAMME VIEWS ============

@login_required
def programme_create(request):
    """Create a new programme."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    form = ProgrammeForm(request.POST)
    if form.is_valid():
        form.save()
        if request.htmx:
            response = HttpResponse(status=200)
            response['HX-Refresh'] = 'true'
            return response
        return redirect('academics:index')

    context = get_academics_context()
    context['programme_form'] = form
    context['programme_errors'] = form.errors
    return render(request, 'academics/partials/card_programmes.html', context)


@login_required
def programme_edit(request, pk):
    """Edit a programme."""
    programme = get_object_or_404(Programme, pk=pk)

    if request.method == 'GET':
        form = ProgrammeForm(instance=programme)
        return render(request, 'academics/partials/modal_programme_edit.html', {
            'form': form,
            'programme': programme,
        })

    if request.method != 'POST':
        return HttpResponse(status=405)

    form = ProgrammeForm(request.POST, instance=programme)
    if form.is_valid():
        form.save()
        if request.htmx:
            response = HttpResponse(status=200)
            response['HX-Refresh'] = 'true'
            return response
        return redirect('academics:index')

    return render(request, 'academics/partials/modal_programme_edit.html', {
        'form': form,
        'programme': programme,
    })


@login_required
def programme_delete(request, pk):
    """Delete a programme."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    programme = get_object_or_404(Programme, pk=pk)
    programme.delete()

    if request.htmx:
        response = HttpResponse(status=200)
        response['HX-Refresh'] = 'true'
        return response
    return redirect('academics:index')


# ============ CLASS VIEWS ============

@login_required
def class_create(request):
    """Create a new class."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    form = ClassForm(request.POST)
    if form.is_valid():
        form.save()
        if request.htmx:
            response = HttpResponse(status=200)
            response['HX-Refresh'] = 'true'
            return response
        return redirect('academics:index')

    context = get_academics_context()
    context['class_form'] = form
    context['class_errors'] = form.errors
    return render(request, 'academics/partials/card_classes.html', context)


@login_required
def class_edit(request, pk):
    """Edit a class."""
    cls = get_object_or_404(Class, pk=pk)

    if request.method == 'GET':
        form = ClassForm(instance=cls)
        return render(request, 'academics/partials/modal_class_edit.html', {
            'form': form,
            'class': cls,
        })

    if request.method != 'POST':
        return HttpResponse(status=405)

    form = ClassForm(request.POST, instance=cls)
    if form.is_valid():
        form.save()
        if request.htmx:
            response = HttpResponse(status=200)
            response['HX-Refresh'] = 'true'
            return response
        return redirect('academics:index')

    return render(request, 'academics/partials/modal_class_edit.html', {
        'form': form,
        'class': cls,
    })


@login_required
def class_delete(request, pk):
    """Delete a class."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    cls = get_object_or_404(Class, pk=pk)
    cls.delete()

    if request.htmx:
        response = HttpResponse(status=200)
        response['HX-Refresh'] = 'true'
        return response
    return redirect('academics:index')


# ============ SUBJECT VIEWS ============

@login_required
def subject_create(request):
    """Create a new subject."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    form = SubjectForm(request.POST)
    if form.is_valid():
        form.save()
        if request.htmx:
            response = HttpResponse(status=200)
            response['HX-Refresh'] = 'true'
            return response
        return redirect('academics:index')

    context = get_academics_context()
    context['subject_form'] = form
    context['subject_errors'] = form.errors
    return render(request, 'academics/partials/card_subjects.html', context)


@login_required
def subject_edit(request, pk):
    """Edit a subject."""
    subject = get_object_or_404(Subject, pk=pk)

    if request.method == 'GET':
        form = SubjectForm(instance=subject)
        return render(request, 'academics/partials/modal_subject_edit.html', {
            'form': form,
            'subject': subject,
        })

    if request.method != 'POST':
        return HttpResponse(status=405)

    form = SubjectForm(request.POST, instance=subject)
    if form.is_valid():
        form.save()
        if request.htmx:
            response = HttpResponse(status=200)
            response['HX-Refresh'] = 'true'
            return response
        return redirect('academics:index')

    return render(request, 'academics/partials/modal_subject_edit.html', {
        'form': form,
        'subject': subject,
    })


@login_required
def subject_delete(request, pk):
    """Delete a subject."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    subject = get_object_or_404(Subject, pk=pk)
    subject.delete()

    if request.htmx:
        response = HttpResponse(status=200)
        response['HX-Refresh'] = 'true'
        return response
    return redirect('academics:index')
