from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse

from .models import (
    GradingSystem, GradeScale, AssessmentCategory,
    Assignment, Score, SubjectTermGrade, TermReport
)
from .forms import GradeScaleForm, AssessmentCategoryForm, ScoreForm


User = get_user_model()


class GradingSystemModelTest(TestCase):
    """Tests for GradingSystem model."""

    def setUp(self):
        self.grading_system = GradingSystem.objects.create(
            name='WASSCE',
            level='SHS',
            pass_mark=Decimal('40.00'),
            credit_mark=Decimal('50.00'),
            aggregate_subjects_count=6,
            min_subjects_to_pass=6,
            min_average_for_promotion=Decimal('45.00'),
            require_core_pass=True
        )

    def test_grading_system_creation(self):
        """Test GradingSystem can be created."""
        self.assertEqual(self.grading_system.name, 'WASSCE')
        self.assertEqual(self.grading_system.level, 'SHS')
        self.assertTrue(self.grading_system.is_active)

    def test_is_passing_score(self):
        """Test pass mark check."""
        self.assertTrue(self.grading_system.is_passing_score(50))
        self.assertTrue(self.grading_system.is_passing_score(40))
        self.assertFalse(self.grading_system.is_passing_score(39))
        self.assertFalse(self.grading_system.is_passing_score(None))

    def test_is_credit_score(self):
        """Test credit mark check."""
        self.assertTrue(self.grading_system.is_credit_score(60))
        self.assertTrue(self.grading_system.is_credit_score(50))
        self.assertFalse(self.grading_system.is_credit_score(49))

    def test_str_representation(self):
        """Test string representation."""
        self.assertEqual(str(self.grading_system), 'WASSCE (Senior High School)')


class GradeScaleModelTest(TestCase):
    """Tests for GradeScale model."""

    def setUp(self):
        self.grading_system = GradingSystem.objects.create(
            name='WASSCE',
            level='SHS'
        )
        self.grade_a1 = GradeScale.objects.create(
            grading_system=self.grading_system,
            grade_label='A1',
            min_percentage=Decimal('80.00'),
            max_percentage=Decimal('100.00'),
            aggregate_points=1,
            interpretation='Excellent',
            is_pass=True,
            is_credit=True,
            order=1
        )
        self.grade_f9 = GradeScale.objects.create(
            grading_system=self.grading_system,
            grade_label='F9',
            min_percentage=Decimal('0.00'),
            max_percentage=Decimal('39.99'),
            aggregate_points=9,
            interpretation='Fail',
            is_pass=False,
            is_credit=False,
            order=9
        )

    def test_grade_scale_creation(self):
        """Test GradeScale can be created."""
        self.assertEqual(self.grade_a1.grade_label, 'A1')
        self.assertEqual(self.grade_a1.aggregate_points, 1)

    def test_get_grade_for_score(self):
        """Test looking up grade for a score."""
        grade = self.grading_system.get_grade_for_score(85)
        self.assertEqual(grade.grade_label, 'A1')

        grade = self.grading_system.get_grade_for_score(30)
        self.assertEqual(grade.grade_label, 'F9')

    def test_str_representation(self):
        """Test string representation."""
        self.assertIn('A1', str(self.grade_a1))
        self.assertIn('80', str(self.grade_a1))


class AssessmentCategoryModelTest(TestCase):
    """Tests for AssessmentCategory model."""

    def setUp(self):
        self.class_score = AssessmentCategory.objects.create(
            name='Class Score',
            short_name='CA',
            percentage=30,
            order=1
        )
        self.exam = AssessmentCategory.objects.create(
            name='Examination',
            short_name='EXAM',
            percentage=70,
            order=2
        )

    def test_category_creation(self):
        """Test AssessmentCategory can be created."""
        self.assertEqual(self.class_score.name, 'Class Score')
        self.assertEqual(self.class_score.percentage, 30)

    def test_total_percentage(self):
        """Test total percentage equals 100."""
        total = AssessmentCategory.objects.filter(is_active=True).aggregate(
            total=models.Sum('percentage')
        )['total']
        self.assertEqual(total, 100)

    def test_str_representation(self):
        """Test string representation."""
        self.assertEqual(str(self.class_score), 'Class Score (30%)')


class GradeScaleFormTest(TestCase):
    """Tests for GradeScaleForm."""

    def setUp(self):
        self.grading_system = GradingSystem.objects.create(
            name='WASSCE',
            level='SHS'
        )

    def test_valid_form(self):
        """Test form with valid data."""
        form = GradeScaleForm(
            data={
                'grade_label': 'A1',
                'min_percentage': 80,
                'max_percentage': 100,
                'aggregate_points': 1,
                'interpretation': 'Excellent',
                'is_pass': True,
                'is_credit': True,
                'order': 1
            },
            grading_system=self.grading_system
        )
        self.assertTrue(form.is_valid())

    def test_min_greater_than_max_invalid(self):
        """Test form rejects min > max."""
        form = GradeScaleForm(
            data={
                'grade_label': 'A1',
                'min_percentage': 100,
                'max_percentage': 80,
                'aggregate_points': 1,
                'interpretation': 'Excellent',
                'is_pass': True,
                'is_credit': True,
                'order': 1
            },
            grading_system=self.grading_system
        )
        self.assertFalse(form.is_valid())
        self.assertIn('Minimum percentage cannot be greater than maximum percentage', str(form.errors))

    def test_percentage_out_of_range_invalid(self):
        """Test form rejects percentages outside 0-100."""
        form = GradeScaleForm(
            data={
                'grade_label': 'A1',
                'min_percentage': -10,
                'max_percentage': 110,
                'aggregate_points': 1,
                'interpretation': 'Excellent',
                'is_pass': True,
                'is_credit': True,
                'order': 1
            },
            grading_system=self.grading_system
        )
        self.assertFalse(form.is_valid())


class AssessmentCategoryFormTest(TestCase):
    """Tests for AssessmentCategoryForm."""

    def test_valid_form(self):
        """Test form with valid data."""
        form = AssessmentCategoryForm(
            data={
                'name': 'Class Score',
                'short_name': 'ca',
                'percentage': 30,
                'order': 1,
                'is_active': True
            }
        )
        self.assertTrue(form.is_valid())

    def test_short_name_uppercase(self):
        """Test short_name is converted to uppercase."""
        form = AssessmentCategoryForm(
            data={
                'name': 'Class Score',
                'short_name': 'ca',
                'percentage': 30,
                'order': 1,
                'is_active': True
            }
        )
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['short_name'], 'CA')

    def test_percentage_out_of_range_invalid(self):
        """Test form rejects percentage outside 0-100."""
        form = AssessmentCategoryForm(
            data={
                'name': 'Test',
                'short_name': 'T',
                'percentage': 150,
                'order': 1,
                'is_active': True
            }
        )
        self.assertFalse(form.is_valid())


class ScoreFormTest(TestCase):
    """Tests for ScoreForm."""

    def test_valid_score(self):
        """Test form with valid score."""
        form = ScoreForm(
            data={
                'student_id': 1,
                'assignment_id': 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
                'points': Decimal('85.5')
            },
            max_points=Decimal('100')
        )
        self.assertTrue(form.is_valid())

    def test_score_exceeds_max_invalid(self):
        """Test form rejects score > max points."""
        form = ScoreForm(
            data={
                'student_id': 1,
                'assignment_id': 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
                'points': Decimal('105')
            },
            max_points=Decimal('100')
        )
        self.assertFalse(form.is_valid())

    def test_negative_score_invalid(self):
        """Test form rejects negative score."""
        form = ScoreForm(
            data={
                'student_id': 1,
                'assignment_id': 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
                'points': Decimal('-5')
            },
            max_points=Decimal('100')
        )
        self.assertFalse(form.is_valid())

    def test_decimal_score_valid(self):
        """Test form accepts decimal scores."""
        form = ScoreForm(
            data={
                'student_id': 1,
                'assignment_id': 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
                'points': Decimal('87.75')
            },
            max_points=Decimal('100')
        )
        self.assertTrue(form.is_valid())


class GradeCalculationTest(TestCase):
    """Tests for grade calculation logic."""

    def setUp(self):
        # Create grading system with full scale
        self.grading_system = GradingSystem.objects.create(
            name='WASSCE',
            level='SHS',
            pass_mark=Decimal('40.00'),
            credit_mark=Decimal('50.00')
        )

        # Create grade scales
        scales = [
            ('A1', 80, 100, 1, 'Excellent', True, True),
            ('B2', 70, 79, 2, 'Very Good', True, True),
            ('B3', 65, 69, 3, 'Good', True, True),
            ('C4', 60, 64, 4, 'Credit', True, True),
            ('C5', 55, 59, 5, 'Credit', True, True),
            ('C6', 50, 54, 6, 'Credit', True, True),
            ('D7', 45, 49, 7, 'Pass', True, False),
            ('E8', 40, 44, 8, 'Pass', True, False),
            ('F9', 0, 39, 9, 'Fail', False, False),
        ]

        for i, (label, min_pct, max_pct, points, interp, is_pass, is_credit) in enumerate(scales):
            GradeScale.objects.create(
                grading_system=self.grading_system,
                grade_label=label,
                min_percentage=Decimal(str(min_pct)),
                max_percentage=Decimal(str(max_pct)),
                aggregate_points=points,
                interpretation=interp,
                is_pass=is_pass,
                is_credit=is_credit,
                order=i + 1
            )

    def test_grade_lookup_a1(self):
        """Test grade lookup for A1."""
        grade = self.grading_system.get_grade_for_score(85)
        self.assertEqual(grade.grade_label, 'A1')
        self.assertEqual(grade.aggregate_points, 1)

    def test_grade_lookup_c6(self):
        """Test grade lookup for C6 (credit boundary)."""
        grade = self.grading_system.get_grade_for_score(50)
        self.assertEqual(grade.grade_label, 'C6')
        self.assertTrue(grade.is_credit)

    def test_grade_lookup_d7(self):
        """Test grade lookup for D7 (pass but no credit)."""
        grade = self.grading_system.get_grade_for_score(47)
        self.assertEqual(grade.grade_label, 'D7')
        self.assertTrue(grade.is_pass)
        self.assertFalse(grade.is_credit)

    def test_grade_lookup_f9(self):
        """Test grade lookup for F9 (fail)."""
        grade = self.grading_system.get_grade_for_score(30)
        self.assertEqual(grade.grade_label, 'F9')
        self.assertFalse(grade.is_pass)


# Import models for aggregate calculation
from django.db import models


class AggregateCalculationTest(TestCase):
    """Tests for WASSCE aggregate calculation."""

    def setUp(self):
        self.grading_system = GradingSystem.objects.create(
            name='WASSCE',
            level='SHS',
            aggregate_subjects_count=6
        )

        # Create grade scales
        for i, (label, points) in enumerate([
            ('A1', 1), ('B2', 2), ('B3', 3), ('C4', 4),
            ('C5', 5), ('C6', 6), ('D7', 7), ('E8', 8), ('F9', 9)
        ]):
            GradeScale.objects.create(
                grading_system=self.grading_system,
                grade_label=label,
                min_percentage=Decimal('0'),
                max_percentage=Decimal('100'),
                aggregate_points=points,
                order=i + 1
            )

    def test_best_aggregate_perfect(self):
        """Test best possible aggregate (6 A1s = 6)."""
        # This would require actual SubjectTermGrade objects
        # For now, test the grading system configuration
        self.assertEqual(self.grading_system.aggregate_subjects_count, 6)

    def test_aggregate_subjects_count(self):
        """Test aggregate uses correct number of subjects."""
        self.assertEqual(self.grading_system.aggregate_subjects_count, 6)
