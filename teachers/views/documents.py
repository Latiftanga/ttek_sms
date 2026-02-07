"""
Teacher Document management views.

Provides CRUD operations for teacher documents, both admin and self-service.
"""
from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse
from django.db.models import Count, Q
from django.utils import timezone
from django.template.loader import render_to_string

from teachers.models import Teacher, TeacherDocument
from teachers.forms import TeacherDocumentForm
from .utils import admin_required, htmx_render


def get_document_stats(teacher):
    """Calculate document statistics for a teacher."""
    documents = TeacherDocument.objects.filter(teacher=teacher)
    today = timezone.now().date()

    total = documents.count()
    verified = documents.filter(is_verified=True).count()
    expiring_soon = documents.filter(
        expiry_date__isnull=False,
        expiry_date__gt=today,
        expiry_date__lte=today + timezone.timedelta(days=30)
    ).count()
    expired = documents.filter(
        expiry_date__isnull=False,
        expiry_date__lt=today
    ).count()

    # Count by type
    by_type = documents.values('document_type').annotate(
        count=Count('id')
    ).order_by('-count')

    return {
        'total': total,
        'verified': verified,
        'unverified': total - verified,
        'expiring_soon': expiring_soon,
        'expired': expired,
        'by_type': list(by_type),
    }


@admin_required
def document_list(request, pk):
    """Admin view: List all documents for a teacher."""
    teacher = get_object_or_404(Teacher, pk=pk)

    documents = TeacherDocument.objects.filter(teacher=teacher).order_by('-created_at')
    stats = get_document_stats(teacher)

    context = {
        'teacher': teacher,
        'documents': documents,
        'stats': stats,
    }

    return htmx_render(
        request,
        'teachers/partials/tab_documents.html',
        'teachers/partials/tab_documents.html',
        context
    )


@admin_required
def document_create(request, pk):
    """Admin view: Upload a new document for a teacher."""
    teacher = get_object_or_404(Teacher, pk=pk)

    if request.method == 'POST':
        form = TeacherDocumentForm(request.POST, request.FILES)
        if form.is_valid():
            document = form.save(commit=False)
            document.teacher = teacher
            document.uploaded_by = request.user
            document.save()
            messages.success(request, f"Uploaded: {document.title}")

            if request.htmx:
                documents = TeacherDocument.objects.filter(teacher=teacher).order_by('-created_at')
                stats = get_document_stats(teacher)
                html = render_to_string(
                    'teachers/partials/tab_documents.html',
                    {'teacher': teacher, 'documents': documents, 'stats': stats},
                    request
                )
                response = HttpResponse(html)
                response['HX-Trigger'] = 'closeModal'
                return response
            return redirect('teachers:teacher_detail', pk=pk)
    else:
        form = TeacherDocumentForm()

    context = {
        'form': form,
        'teacher': teacher,
        'is_edit': False,
    }

    return htmx_render(
        request,
        'teachers/partials/modal_document_form.html',
        'teachers/partials/modal_document_form.html',
        context
    )


@admin_required
def document_edit(request, pk, doc_pk):
    """Admin view: Edit a document."""
    teacher = get_object_or_404(Teacher, pk=pk)
    document = get_object_or_404(TeacherDocument, pk=doc_pk, teacher=teacher)

    if request.method == 'POST':
        form = TeacherDocumentForm(request.POST, request.FILES, instance=document)
        if form.is_valid():
            form.save()
            messages.success(request, f"Updated: {document.title}")

            if request.htmx:
                documents = TeacherDocument.objects.filter(teacher=teacher).order_by('-created_at')
                stats = get_document_stats(teacher)
                html = render_to_string(
                    'teachers/partials/tab_documents.html',
                    {'teacher': teacher, 'documents': documents, 'stats': stats},
                    request
                )
                response = HttpResponse(html)
                response['HX-Trigger'] = 'closeModal'
                return response
            return redirect('teachers:teacher_detail', pk=pk)
    else:
        form = TeacherDocumentForm(instance=document)

    context = {
        'form': form,
        'teacher': teacher,
        'document': document,
        'is_edit': True,
    }

    return htmx_render(
        request,
        'teachers/partials/modal_document_form.html',
        'teachers/partials/modal_document_form.html',
        context
    )


@admin_required
def document_delete(request, pk, doc_pk):
    """Admin view: Delete a document."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    teacher = get_object_or_404(Teacher, pk=pk)
    document = get_object_or_404(TeacherDocument, pk=doc_pk, teacher=teacher)

    title = document.title
    document.file.delete(save=False)  # Delete file from storage
    document.delete()
    messages.success(request, f"Deleted: {title}")

    if request.htmx:
        documents = TeacherDocument.objects.filter(teacher=teacher).order_by('-created_at')
        stats = get_document_stats(teacher)
        html = render_to_string(
            'teachers/partials/tab_documents.html',
            {'teacher': teacher, 'documents': documents, 'stats': stats},
            request
        )
        return HttpResponse(html)

    return redirect('teachers:teacher_detail', pk=pk)


@admin_required
def document_verify(request, pk, doc_pk):
    """Admin view: Toggle document verification status."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    teacher = get_object_or_404(Teacher, pk=pk)
    document = get_object_or_404(TeacherDocument, pk=doc_pk, teacher=teacher)

    document.is_verified = not document.is_verified
    document.save(update_fields=['is_verified'])

    status = "verified" if document.is_verified else "unverified"
    messages.success(request, f"Document marked as {status}")

    if request.htmx:
        documents = TeacherDocument.objects.filter(teacher=teacher).order_by('-created_at')
        stats = get_document_stats(teacher)
        html = render_to_string(
            'teachers/partials/tab_documents.html',
            {'teacher': teacher, 'documents': documents, 'stats': stats},
            request
        )
        return HttpResponse(html)

    return redirect('teachers:teacher_detail', pk=pk)


# Teacher self-service views

@login_required
def my_documents(request):
    """Teacher self-service: View own documents."""
    teacher = get_object_or_404(Teacher, user=request.user)

    documents = TeacherDocument.objects.filter(teacher=teacher).order_by('-created_at')
    stats = get_document_stats(teacher)

    context = {
        'teacher': teacher,
        'documents': documents,
        'stats': stats,
        'is_self_service': True,
        'breadcrumbs': [
            {'label': 'Home', 'url': '/', 'icon': 'fa-solid fa-home'},
            {'label': 'My Documents'},
        ],
        'back_url': '/',
    }

    return htmx_render(
        request,
        'teachers/my_documents.html',
        'teachers/partials/my_documents_content.html',
        context
    )


@login_required
def my_documents_create(request):
    """Teacher self-service: Upload a new document."""
    teacher = get_object_or_404(Teacher, user=request.user)

    if request.method == 'POST':
        form = TeacherDocumentForm(request.POST, request.FILES)
        if form.is_valid():
            document = form.save(commit=False)
            document.teacher = teacher
            document.uploaded_by = request.user
            document.save()
            messages.success(request, f"Uploaded: {document.title}")

            if request.htmx:
                documents = TeacherDocument.objects.filter(teacher=teacher).order_by('-created_at')
                html = render_to_string(
                    'teachers/partials/my_documents_inner.html',
                    {'documents': documents},
                    request
                )
                response = HttpResponse(html)
                response['HX-Trigger'] = 'closeModal'
                return response
            return redirect('core:my_documents')
    else:
        form = TeacherDocumentForm()

    context = {
        'form': form,
        'teacher': teacher,
        'is_edit': False,
        'is_self_service': True,
    }

    return htmx_render(
        request,
        'teachers/partials/modal_document_form.html',
        'teachers/partials/modal_document_form.html',
        context
    )


@login_required
def my_documents_edit(request, doc_pk):
    """Teacher self-service: Edit own document."""
    teacher = get_object_or_404(Teacher, user=request.user)
    document = get_object_or_404(TeacherDocument, pk=doc_pk, teacher=teacher)

    if request.method == 'POST':
        form = TeacherDocumentForm(request.POST, request.FILES, instance=document)
        if form.is_valid():
            form.save()
            messages.success(request, f"Updated: {document.title}")

            if request.htmx:
                documents = TeacherDocument.objects.filter(teacher=teacher).order_by('-created_at')
                html = render_to_string(
                    'teachers/partials/my_documents_inner.html',
                    {'documents': documents},
                    request
                )
                response = HttpResponse(html)
                response['HX-Trigger'] = 'closeModal'
                return response
            return redirect('core:my_documents')
    else:
        form = TeacherDocumentForm(instance=document)

    context = {
        'form': form,
        'teacher': teacher,
        'document': document,
        'is_edit': True,
        'is_self_service': True,
    }

    return htmx_render(
        request,
        'teachers/partials/modal_document_form.html',
        'teachers/partials/modal_document_form.html',
        context
    )


@login_required
def my_documents_delete(request, doc_pk):
    """Teacher self-service: Delete own document."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    teacher = get_object_or_404(Teacher, user=request.user)
    document = get_object_or_404(TeacherDocument, pk=doc_pk, teacher=teacher)

    title = document.title
    document.file.delete(save=False)
    document.delete()
    messages.success(request, f"Deleted: {title}")

    if request.htmx:
        documents = TeacherDocument.objects.filter(teacher=teacher).order_by('-created_at')
        html = render_to_string(
            'teachers/partials/my_documents_inner.html',
            {'documents': documents},
            request
        )
        return HttpResponse(html)

    return redirect('core:my_documents')
