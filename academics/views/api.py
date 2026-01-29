"""API endpoints for academics app."""
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse

from ..models import Class, ClassSubject
from .base import teacher_or_admin_required


@login_required
@teacher_or_admin_required
def api_class_subjects(request, pk):
    """API endpoint to get subjects for a class.

    For admins: returns all subjects assigned to the class.
    For teachers: returns only subjects they are assigned to teach.
    """
    class_obj = get_object_or_404(Class, pk=pk)
    user = request.user

    # Build base query
    class_subjects = ClassSubject.objects.filter(
        class_assigned=class_obj
    ).select_related('subject', 'teacher')

    # Filter by teacher assignment for non-admins
    if not (user.is_superuser or getattr(user, 'is_school_admin', False)):
        # Check if user has a teacher profile
        if hasattr(user, 'teacher_profile') and user.teacher_profile:
            class_subjects = class_subjects.filter(teacher=user.teacher_profile)
        else:
            class_subjects = class_subjects.none()

    subjects = [
        {
            'id': cs.subject.pk,
            'name': cs.subject.name,
            'is_assigned': cs.teacher_id == getattr(getattr(user, 'teacher_profile', None), 'id', None)
        }
        for cs in class_subjects
    ]

    return JsonResponse({'subjects': subjects})
