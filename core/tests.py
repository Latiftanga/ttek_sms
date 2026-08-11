from datetime import date

from django.test import TestCase
from django.urls import reverse
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

    def test_school_days_blank_inherits_global(self):
        cache.clear()
        SchoolSettings.objects.all().delete()
        settings = SchoolSettings.load()
        settings.school_days = '1,2,3,4,5'
        settings.save()

        term = self._create_term()  # school_days left blank
        self.assertEqual(term.school_days_set, {1, 2, 3, 4, 5})
        self.assertTrue(term.is_school_day(1))  # Monday
        self.assertFalse(term.is_school_day(6))  # Saturday

    def test_school_days_custom_overrides_global(self):
        cache.clear()
        SchoolSettings.objects.all().delete()
        settings = SchoolSettings.load()
        settings.school_days = '1,2,3,4,5'
        settings.save()

        term = self._create_term(school_days='1,2,3,4')  # no Friday
        self.assertEqual(term.school_days_set, {1, 2, 3, 4})
        self.assertTrue(term.is_school_day(1))
        self.assertFalse(term.is_school_day(5))  # Friday excluded by override

    def test_school_days_can_include_weekend(self):
        term = self._create_term(school_days='1,2,3,4,5,6')  # adds Saturday
        self.assertTrue(term.is_school_day(6))

    def test_school_days_invalid_value_raises(self):
        with self.assertRaises(ValidationError):
            self._create_term(school_days='not-a-number')

    def test_school_days_out_of_range_raises(self):
        with self.assertRaises(ValidationError):
            self._create_term(school_days='0,8')


class GetValidSchoolDaysTests(TenantTestCase):
    """Tests for core.utils.is_valid_school_day / get_valid_school_days,
    which resolve a per-term school_days override before falling back to
    the school-wide SchoolSettings default."""

    def setUp(self):
        cache.clear()
        SchoolSettings.objects.all().delete()
        settings = SchoolSettings.load()
        settings.school_days = '1,2,3,4,5'  # Mon-Fri
        settings.save()

        self.ay = AcademicYear.objects.create(
            name='2024/2025',
            start_date=date(2024, 9, 1),
            end_date=date(2025, 7, 31),
            is_current=True,
        )

    def test_falls_back_to_global_when_no_term_covers_range(self):
        from core.utils import get_valid_school_days
        # Aug 5-9, 2024 (Mon-Fri) - before any term exists
        days = get_valid_school_days(date(2024, 8, 5), date(2024, 8, 9))
        self.assertEqual(len(days), 5)

    def test_term_override_excludes_a_global_working_day(self):
        from core.utils import get_valid_school_days
        Term.objects.create(
            academic_year=self.ay, name='First Term', term_number=1,
            start_date=date(2024, 9, 1), end_date=date(2024, 12, 20),
            school_days='1,2,3,4',  # no Friday
        )
        # Sept 2-6, 2024: Mon-Fri
        days = get_valid_school_days(date(2024, 9, 2), date(2024, 9, 6))
        weekdays = {d.isoweekday() for d in days}
        self.assertEqual(weekdays, {1, 2, 3, 4})

    def test_term_override_includes_a_global_non_working_day(self):
        from core.utils import get_valid_school_days
        Term.objects.create(
            academic_year=self.ay, name='First Term', term_number=1,
            start_date=date(2024, 9, 1), end_date=date(2024, 12, 20),
            school_days='1,2,3,4,5,6',  # adds Saturday
        )
        # Sept 2 (Mon) - Sept 7 (Sat), 2024
        days = get_valid_school_days(date(2024, 9, 2), date(2024, 9, 7))
        weekdays = {d.isoweekday() for d in days}
        self.assertIn(6, weekdays)

    def test_range_spanning_two_terms_with_different_patterns(self):
        from core.utils import get_valid_school_days
        Term.objects.create(
            academic_year=self.ay, name='First Term', term_number=1,
            start_date=date(2024, 9, 1), end_date=date(2024, 9, 6),
            school_days='1,2,3,4',  # no Friday
        )
        Term.objects.create(
            academic_year=self.ay, name='Second Term', term_number=2,
            start_date=date(2024, 9, 7), end_date=date(2024, 9, 13),
            school_days='1,2,3,4,5,6,7',  # every day
        )
        # Sept 2 (Mon) through Sept 8 (Sun): first term's Friday (Sept 6) and
        # the weekend before the second term starts (Sept 7-8, which IS
        # inside the second term) should differ.
        days = get_valid_school_days(date(2024, 9, 2), date(2024, 9, 8))
        day_set = set(days)
        self.assertNotIn(date(2024, 9, 6), day_set)  # Friday, excluded by term 1
        self.assertIn(date(2024, 9, 7), day_set)  # Saturday, included by term 2
        self.assertIn(date(2024, 9, 8), day_set)  # Sunday, included by term 2

    def test_is_valid_school_day_hint_not_covering_date_is_ignored(self):
        """A `term` hint that doesn't actually cover the date is safely
        ignored in favor of a fresh lookup - e.g. passing `current_term`
        for a date that belongs to a different, earlier term."""
        from core.utils import is_valid_school_day
        covering_term = Term.objects.create(
            academic_year=self.ay, name='First Term', term_number=1,
            start_date=date(2024, 9, 1), end_date=date(2024, 12, 20),
            school_days='1,2,3,4',  # no Friday
        )
        unrelated_term = Term.objects.create(
            academic_year=self.ay, name='Second Term', term_number=2,
            start_date=date(2025, 1, 6), end_date=date(2025, 4, 15),
            school_days='1,2,3,4,5,6',  # includes Saturday
        )
        friday = date(2024, 9, 6)  # excluded by covering_term, would be a
                                    # school day under unrelated_term's own
                                    # pattern if that hint were used verbatim
        monday = date(2024, 9, 2)  # a school day under both terms' patterns

        # `unrelated_term` doesn't cover `friday` at all, so passing it as a
        # hint must be ignored in favor of looking up the term that actually
        # covers this date (covering_term, which excludes Friday) - not
        # silently answered via the wrong term's pattern (which would wrongly
        # say True, since Friday=5 is in unrelated_term's own school_days).
        self.assertFalse(is_valid_school_day(friday, term=unrelated_term))
        # A hint that DOES cover the date is used directly (no extra lookup).
        self.assertTrue(is_valid_school_day(monday, term=covering_term))


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
        cache.clear()
        SchoolSettings.objects.all().delete()
        settings = SchoolSettings.load()
        self.assertEqual(settings.sms_backend, 'console')
        self.assertEqual(settings.email_backend, 'console')
        self.assertFalse(settings.sms_enabled)
        self.assertFalse(settings.email_enabled)
        self.assertFalse(settings.setup_completed)
        self.assertFalse(settings.allow_past_term_attendance)


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


class AcademicSettingsUpdateViewTests(TenantTestCase):
    """Tests for the settings_update_academic view (Academic Calendar card)."""

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.name = 'Test School'
        tenant.short_name = 'TEST'

    def setUp(self):
        super().setUp()
        from django_tenants.test.client import TenantClient
        cache.clear()  # SchoolSettings.load() caches per-tenant for 24h
        self.addCleanup(cache.clear)
        self.client = TenantClient(self.tenant)
        self.admin_user = User.objects.create_user(
            email='admin@school.com', password='testpass123', is_school_admin=True
        )
        self.client.login(email='admin@school.com', password='testpass123')

    def test_get_not_allowed(self):
        response = self.client.get(reverse('core:settings_update_academic'))
        self.assertEqual(response.status_code, 405)

    def test_enables_past_term_attendance(self):
        response = self.client.post(
            reverse('core:settings_update_academic'),
            {'academic_period_type': 'term', 'allow_past_term_attendance': 'true'},
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(response.status_code, 200)
        settings = SchoolSettings.load()
        self.assertTrue(settings.allow_past_term_attendance)

    def test_disables_past_term_attendance_when_unchecked(self):
        settings = SchoolSettings.load()
        settings.allow_past_term_attendance = True
        settings.save()

        # Unchecked checkboxes aren't sent in the POST body at all.
        response = self.client.post(
            reverse('core:settings_update_academic'),
            {'academic_period_type': 'term'},
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(response.status_code, 200)
        settings.refresh_from_db()
        self.assertFalse(settings.allow_past_term_attendance)


class TermFormSchoolDaysTests(TenantTestCase):
    """Tests for TermForm's custom school_days field/toggle."""

    def setUp(self):
        self.ay = AcademicYear.objects.create(
            name='2024/2025',
            start_date=date(2024, 9, 1),
            end_date=date(2025, 7, 31),
            is_current=True,
        )

    def _base_data(self, **overrides):
        data = {
            'academic_year': self.ay.pk,
            'name': 'First Term',
            'term_number': 1,
            'start_date': '2024-09-01',
            'end_date': '2024-12-20',
        }
        data.update(overrides)
        return data

    def test_toggle_off_saves_blank_school_days(self):
        from core.forms import TermForm
        form = TermForm(data=self._base_data(school_days=['1', '2', '3']))
        self.assertTrue(form.is_valid(), form.errors)
        term = form.save()
        self.assertEqual(term.school_days, '')

    def test_toggle_on_saves_selected_days(self):
        from core.forms import TermForm
        form = TermForm(data=self._base_data(
            use_custom_school_days='on', school_days=['1', '2', '3', '4'],
        ))
        self.assertTrue(form.is_valid(), form.errors)
        term = form.save()
        self.assertEqual(term.school_days, '1,2,3,4')

    def test_toggle_on_with_no_days_is_invalid_not_a_crash(self):
        from core.forms import TermForm
        form = TermForm(data=self._base_data(use_custom_school_days='on'))
        self.assertFalse(form.is_valid())
        self.assertIn('school_days', form.errors)

    def test_editing_existing_override_prefills_form(self):
        from core.forms import TermForm
        term = Term.objects.create(
            academic_year=self.ay, name='First Term', term_number=1,
            start_date=date(2024, 9, 1), end_date=date(2024, 12, 20),
            school_days='1,3,5',
        )
        form = TermForm(instance=term)
        self.assertTrue(form.fields['use_custom_school_days'].initial)
        self.assertEqual(set(form.fields['school_days'].initial), {'1', '3', '5'})
