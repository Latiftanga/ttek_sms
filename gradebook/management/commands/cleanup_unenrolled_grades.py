"""
Purge orphaned SubjectTermGrade rows, then recalculate report aggregates and
re-rank class positions.

A grade is treated as orphaned when EITHER:
  - its subject is no longer allocated to the student's current class
    (a subject removed from the whole class) — detected via ClassSubject, so
    it works even for classes that don't track per-student enrollments; or
  - the class tracks per-student enrollments and the student is no longer
    actively enrolled in that subject (a single student unregistered).

This cleans up data created BEFORE the unenroll / subject-removal cleanup fix:
the computed SubjectTermGrade was left behind, so it kept showing on report
cards and skewed positions.

Scope: the current term by default (pass --term-id to target another term).
Past terms are left untouched so historical report cards keep their data.

Usage:
    # Dry run (preview only) — current term, all classes
    python manage.py tenant_command cleanup_unenrolled_grades --schema=<tenant>

    # Actually delete + re-rank
    python manage.py tenant_command cleanup_unenrolled_grades --schema=<tenant> --apply

    # Limit to one class
    python manage.py tenant_command cleanup_unenrolled_grades --schema=<tenant> --class-name B1 --apply

    # Target a specific term (UUID) instead of the current term
    python manage.py tenant_command cleanup_unenrolled_grades --schema=<tenant> --term-id <uuid> --apply
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django_tenants.utils import schema_context


class Command(BaseCommand):
    help = 'Remove orphaned grades for unenrolled students and re-rank positions'

    def add_arguments(self, parser):
        parser.add_argument('--schema', type=str, help='Tenant schema name')
        parser.add_argument('--class-name', help='Limit to a single class (e.g. B1)')
        parser.add_argument('--term-id', help='Term UUID (defaults to current term)')
        parser.add_argument(
            '--apply', action='store_true',
            help='Actually delete and re-rank (default is a dry run)'
        )

    def handle(self, *args, **options):
        schema = options.get('schema')
        if schema:
            with schema_context(schema):
                self._run(options)
        else:
            self._run(options)

    def _run(self, options):
        from academics.models import Class, ClassSubject, StudentSubjectEnrollment
        from gradebook.models import SubjectTermGrade
        from gradebook.utils import recalc_and_rerank_term_reports
        from students.models import Student
        from core.models import Term

        apply = options['apply']

        # Resolve the term to clean.
        if options.get('term_id'):
            term = Term.objects.filter(pk=options['term_id']).first()
            if not term:
                self.stderr.write(f"Term {options['term_id']} not found.")
                return
        else:
            term = Term.get_current()
            if not term:
                self.stderr.write('No current term set.')
                return

        self.stdout.write(f'Term: {term.name}')

        classes = Class.objects.filter(is_active=True)
        if options.get('class_name'):
            classes = classes.filter(name=options['class_name'])
            if not classes.exists():
                self.stderr.write(f"Class \"{options['class_name']}\" not found.")
                return

        total_deleted = 0
        total_reranked = 0
        classes_touched = 0

        for class_obj in classes.order_by('level_number', 'name'):
            # Subjects currently allocated to the class. A grade for a subject
            # NOT in this set is orphaned regardless of enrollment tracking —
            # this catches a subject removed from the whole class.
            allocated_subject_ids = set(ClassSubject.objects.filter(
                class_assigned=class_obj
            ).values_list('subject_id', flat=True))
            # Only trust allocation as the source of truth when the class
            # actually has subjects configured. A class with zero allocations
            # is likely misconfigured — skip allocation-based detection so we
            # don't wipe its grades.
            has_allocations = bool(allocated_subject_ids)

            # Map of student_id -> {actively enrolled subject_ids} for this class.
            # Some classes don't track per-student enrollments at all; for those
            # we fall back to allocation-only detection above.
            enrollments = StudentSubjectEnrollment.objects.filter(
                class_subject__class_assigned=class_obj,
                is_active=True,
            ).values_list('student_id', 'class_subject__subject_id')
            tracks_enrollment = bool(enrollments)

            enrolled_map = {}
            for sid, subj_id in enrollments:
                enrolled_map.setdefault(sid, set()).add(subj_id)

            student_ids = list(Student.objects.filter(
                current_class=class_obj
            ).values_list('id', flat=True))
            if not student_ids:
                continue

            grades = SubjectTermGrade.objects.filter(
                student_id__in=student_ids, term=term
            ).select_related('student', 'subject')

            orphan_ids = []
            for g in grades:
                # Orphan if the subject is no longer allocated to the class, or
                # (for classes that track it) the student isn't actively
                # enrolled in that subject.
                unallocated = has_allocations and (
                    g.subject_id not in allocated_subject_ids
                )
                unenrolled = tracks_enrollment and (
                    g.subject_id not in enrolled_map.get(g.student_id, set())
                )
                if unallocated or unenrolled:
                    orphan_ids.append(g.id)
                    reason = 'not allocated' if unallocated else 'not enrolled'
                    self.stdout.write(
                        f'  [{class_obj.name}] {g.student.full_name} — '
                        f'{g.subject.name} ({g.total_score}) [{reason}]'
                    )

            if not orphan_ids:
                continue

            total_deleted += len(orphan_ids)
            classes_touched += 1

            if not apply:
                continue

            with transaction.atomic():
                SubjectTermGrade.objects.filter(id__in=orphan_ids).delete()
                total_reranked += recalc_and_rerank_term_reports(student_ids, term)

        if total_deleted == 0:
            self.stdout.write(self.style.SUCCESS('No orphaned grades found. Nothing to do.'))
            return

        if not apply:
            self.stdout.write(self.style.WARNING(
                f'Dry run — {total_deleted} orphaned grade(s) across '
                f'{classes_touched} class(es) would be deleted. '
                f'Re-run with --apply to delete and re-rank.'
            ))
            return

        self.stdout.write(self.style.SUCCESS(
            f'Deleted {total_deleted} orphaned grade(s) across {classes_touched} '
            f'class(es); re-ranked {total_reranked} report(s).'
        ))
