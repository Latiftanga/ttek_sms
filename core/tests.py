from datetime import date

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django_tenants.test.cases import TenantTestCase

from core.models import (
    AcademicYear, Term, SchoolSettings,
    DocumentVerification, generate_verification_code, hex_to_oklch_values,
)

User = get_user_model()


class HexToOklchTests(TestCase):
    """Tests for the hex_to_oklch_values color conversion utility."""

    def test_black(self):
        result = hex_to_oklch_values('#000000')
        self.assertTrue(result.startswith('0%'))

    def test_white(self):
        result = hex_to_oklch_values('#ffffff')
        self.assertTrue(result.startswith('100%'))

    def test_without_hash(self):
        """Hex value without leading # should still work."""
        result = hex_to_oklch_values('ff0000')
        self.assertIn('%', result)

    def test_returns_three_parts(self):
        """Result should be 'L% C H' format."""
        result = hex_to_oklch_values('#3366cc')
        parts = result.split()
        self.assertEqual(len(parts), 3)
        self.assertTrue(parts[0].endswith('%'))

    def test_known_color(self):
        """Pure red should have non-zero chroma and hue."""
        result = hex_to_oklch_values('#ff0000')
        parts = result.split()
        chroma = float(parts[1])
        self.assertGreater(chroma, 0)


class GenerateVerificationCodeTests(TestCase):
    """Tests for verification code generation."""

    def test_length(self):
        code = generate_verification_code()
        self.assertEqual(len(code), 12)

    def test_uppercase(self):
        code = generate_verification_code()
        self.assertEqual(code, code.upper())

    def test_uniqueness(self):
        codes = {generate_verification_code() for _ in range(50)}
        self.assertEqual(len(codes), 50)


class AcademicYearModelTests(TenantTestCase):
    """Tests for the AcademicYear model."""

    def _create_year(self, **kwargs):
        defaults = {
            'name': '2024/2025 Academic Year',
            'start_date': date(2024, 9, 1),
            'end_date': date(2025, 7, 31),
            'is_current': False,
        }
        defaults.update(kwargs)
        return AcademicYear.objects.create(**defaults)

    def test_create_academic_year(self):
        ay = self._create_year()
        self.assertEqual(str(ay), '2024/2025 Academic Year')

    def test_end_date_must_be_after_start_date(self):
        with self.assertRaises(ValidationError):
            self._create_year(
                start_date=date(2025, 7, 31),
                end_date=date(2024, 9, 1),
            )

    def test_max_span_two_years(self):
        with self.assertRaises(ValidationError):
            self._create_year(
                start_date=date(2024, 1, 1),
                end_date=date(2027, 1, 1),
            )

    def test_only_one_current(self):
        ay1 = self._create_year(is_current=True)
        ay2 = self._create_year(
            name='2025/2026',
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 31),
            is_current=True,
        )
        ay1.refresh_from_db()
        self.assertFalse(ay1.is_current)
        self.assertTrue(ay2.is_current)

    def test_get_current(self):
        self._create_year(is_current=True)
        current = AcademicYear.get_current()
        self.assertIsNotNone(current)
        self.assertTrue(current.is_current)

    def test_get_current_none(self):
        cache.clear()
        current = AcademicYear.get_current()
        self.assertIsNone(current)


class TermModelTests(TenantTestCase):
    """Tests for the Term model."""

    def setUp(self):
        self.ay = AcademicYear.objects.create(
            name='2024/2025',
            start_date=date(2024, 9, 1),
            end_date=date(2025, 7, 31),
            is_current=True,
        )

    def _create_term(self, **kwargs):
        defaults = {
            'academic_year': self.ay,
            'name': 'First Term',
            'term_number': 1,
            'start_date': date(2024, 9, 1),
            'end_date': date(2024, 12, 20),
            'is_current': False,
        }
        defaults.update(kwargs)
        return Term.objects.create(**defaults)

    def test_create_term(self):
        term = self._create_term()
        self.assertEqual(str(term), 'First Term - 2024/2025')

    def test_end_date_must_be_after_start_date(self):
        with self.assertRaises(ValidationError):
            self._create_term(
                start_date=date(2024, 12, 20),
                end_date=date(2024, 9, 1),
            )

    def test_term_dates_within_academic_year(self):
        with self.assertRaises(ValidationError):
            self._create_term(
                start_date=date(2024, 8, 1),  # Before AY start
                end_date=date(2024, 12, 20),
            )

    def test_term_end_after_academic_year(self):
        with self.assertRaises(ValidationError):
            self._create_term(
                start_date=date(2025, 4, 1),
                end_date=date(2025, 8, 31),  # After AY end
            )

    def test_only_one_current_term(self):
        t1 = self._create_term(is_current=True)
        t2 = self._create_term(
            name='Second Term',
            term_number=2,
            start_date=date(2025, 1, 6),
            end_date=date(2025, 4, 15),
            is_current=True,
        )
        t1.refresh_from_db()
        self.assertFalse(t1.is_current)
        self.assertTrue(t2.is_current)

    def test_get_current(self):
        self._create_term(is_current=True)
        current = Term.get_current()
        self.assertIsNotNone(current)
        self.assertTrue(current.is_current)

    def test_lock_grades(self):
        term = self._create_term()
        user = User.objects.create_user(email='admin@test.com', password='pass')
        term.lock_grades(user)
        term.refresh_from_db()
        self.assertTrue(term.grades_locked)
        self.assertIsNotNone(term.grades_locked_at)
        self.assertEqual(term.grades_locked_by, user)

    def test_unlock_grades(self):
        term = self._create_term()
        user = User.objects.create_user(email='admin@test.com', password='pass')
        term.lock_grades(user)
        term.unlock_grades()
        term.refresh_from_db()
        self.assertFalse(term.grades_locked)
        self.assertIsNone(term.grades_locked_at)
        self.assertIsNone(term.grades_locked_by)

    def test_unique_together_academic_year_term_number(self):
        self._create_term(term_number=1)
        with self.assertRaises(Exception):
            self._create_term(name='Another First Term', term_number=1)


class SchoolSettingsModelTests(TenantTestCase):
    """Tests for the SchoolSettings singleton model."""

    def test_load_creates_if_not_exists(self):
        cache.clear()
        SchoolSettings.objects.all().delete()
        settings = SchoolSettings.load()
        self.assertIsNotNone(settings)
        self.assertEqual(SchoolSettings.objects.count(), 1)

    def test_load_returns_existing(self):
        cache.clear()
        SchoolSettings.objects.all().delete()
        s1 = SchoolSettings.load()
        s2 = SchoolSettings.load()
        self.assertEqual(s1.pk, s2.pk)

    def test_singleton_pk_is_always_1(self):
        cache.clear()
        SchoolSettings.objects.all().delete()
        settings = SchoolSettings.load()
        self.assertEqual(settings.pk, 1)

    def test_period_label_term(self):
        settings = SchoolSettings.load()
        settings.academic_period_type = 'term'
        self.assertEqual(settings.period_label, 'Term')
        self.assertEqual(settings.period_label_plural, 'Terms')

    def test_period_label_semester(self):
        settings = SchoolSettings.load()
        settings.academic_period_type = 'semester'
        self.assertEqual(settings.period_label, 'Semester')
        self.assertEqual(settings.period_label_plural, 'Semesters')

    def test_default_values(self):
        settings = SchoolSettings.load()
        self.assertEqual(settings.sms_backend, 'console')
        self.assertEqual(settings.email_backend, 'console')
        self.assertFalse(settings.sms_enabled)
        self.assertFalse(settings.email_enabled)
        self.assertFalse(settings.setup_completed)


class DocumentVerificationModelTests(TenantTestCase):
    """Tests for the DocumentVerification model."""

    def test_create_verification(self):
        doc = DocumentVerification.objects.create(
            document_type=DocumentVerification.DocumentType.REPORT_CARD,
            student_name='John Doe',
            student_admission_number='STU-2024-001',
            document_title='Report Card - Term 1 2024/2025',
        )
        self.assertEqual(len(doc.verification_code), 12)
        self.assertEqual(doc.verification_count, 0)

    def test_record_verification(self):
        doc = DocumentVerification.objects.create(
            document_type=DocumentVerification.DocumentType.TRANSCRIPT,
            student_name='Jane Doe',
            student_admission_number='STU-2024-002',
            document_title='Transcript',
        )
        doc.record_verification()
        doc.refresh_from_db()
        self.assertEqual(doc.verification_count, 1)
        self.assertIsNotNone(doc.last_verified_at)

    def test_record_verification_increments(self):
        doc = DocumentVerification.objects.create(
            document_type=DocumentVerification.DocumentType.STUDENT_PROFILE,
            student_name='Test Student',
            student_admission_number='STU-001',
            document_title='Student Profile',
        )
        doc.record_verification()
        doc.record_verification()
        doc.refresh_from_db()
        self.assertEqual(doc.verification_count, 2)

    def test_str(self):
        doc = DocumentVerification.objects.create(
            document_type=DocumentVerification.DocumentType.REPORT_CARD,
            student_name='Test',
            student_admission_number='STU-001',
            document_title='Report Card',
        )
        self.assertIn(doc.verification_code, str(doc))
        self.assertIn('Report Card', str(doc))
