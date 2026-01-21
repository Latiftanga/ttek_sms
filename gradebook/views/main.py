
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Count

from ..models import (
    GradingSystem, AssessmentCategory,
    Assignment, Score, TermReport
)
from academics.models import Class
from students.models import Student
from core.models import Term
from .base import admin_required, htmx_render
from ..utils import calculate_score_entry_progress, get_classes_needing_scores


@login_required
@admin_required
def index(request):
    """Gradebook dashboard (Admin only)."""
    current_term = Term.get_current()
    classes = Class.objects.filter(is_active=True).order_by('level_number', 'name')

    # Get grading systems
    grading_systems = GradingSystem.objects.filter(is_active=True)
    categories = AssessmentCategory.objects.filter(is_active=True)

    # Enhanced Stats - optimized with single queries
    total_students = Student.objects.filter(status='active').count()
    assignments_this_term = Assignment.objects.filter(term=current_term).count() if current_term else 0
    reports_generated = TermReport.objects.filter(term=current_term).count() if current_term else 0

    scores_entered, _, score_progress = calculate_score_entry_progress(current_term)
    
    # Recent activity - get latest score entries
    recent_scores = Score.objects.filter(
        assignment__term=current_term
    ).select_related(
        'student', 'assignment__subject'
    ).order_by('-updated_at')[:5] if current_term else []

    classes_needing_scores = get_classes_needing_scores(current_term, classes)

    stats = {
        'classes': classes.count(),
        'students': total_students,
        'grading_systems': grading_systems.count(),
        'categories': categories.count(),
        'assignments': assignments_this_term,
        'scores_entered': scores_entered,
        'reports_generated': reports_generated,
        'score_progress': score_progress,
    }

    context = {
        'current_term': current_term,
        'classes': classes,
        'grading_systems': grading_systems,
        'categories': categories,
        'stats': stats,
        'recent_scores': recent_scores,
        'classes_needing_scores': classes_needing_scores,
        # Navigation
        'breadcrumbs': [
            {'label': 'Home', 'url': '/', 'icon': 'fa-solid fa-home'},
            {'label': 'Gradebook'},
        ],
    }

    return htmx_render(
        request,
        'gradebook/index.html',
        'gradebook/partials/index_content.html',
        context
    )
