import io
import json
from datetime import date, datetime

from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
import pandas as pd

from students.models import Student, Guardian, Enrollment
from students.views.utils import parse_date, clean_value
from students.views.bulk_import import BASE_COLUMNS
from academics.models import Class, ClassSubject, Programme, Subject, StudentSubjectEnrollment
from teachers.models import Teacher
from core.models import AcademicYear

User = get_user_model()


class ParseDateTests(TestCase):
    """Tests for the parse_date utility function."""

    def test_parse_date_none(self):
        """Test parsing None returns None."""
        self.assertIsNone(parse_date(None))

    def test_parse_date_nan(self):
        """Test parsing NaN returns None."""
        self.assertIsNone(parse_date(float('nan')))

    def test_parse_date_empty_string(self):
        """Test parsing empty string returns None."""
        self.assertIsNone(parse_date(''))
        self.assertIsNone(parse_date('   '))

    def test_parse_date_datetime_object(self):
        """Test parsing datetime object returns date."""
        dt = datetime(2024, 5, 15, 10, 30)
        result = parse_date(dt)
        self.assertEqual(result, date(2024, 5, 15))

    def test_parse_date_iso_format(self):
        """Test parsing ISO format (YYYY-MM-DD)."""
        result = parse_date('2024-05-15')
        self.assertEqual(result, date(2024, 5, 15))

    def test_parse_date_uk_format(self):
        """Test parsing UK format (DD/MM/YYYY)."""
        result = parse_date('15/05/2024')
        self.assertEqual(result, date(2024, 5, 15))

    def test_parse_date_us_format(self):
        """Test parsing US format (MM/DD/YYYY)."""
        result = parse_date('05/15/2024')
        self.assertEqual(result, date(2024, 5, 15))

    def test_parse_date_dash_format(self):
        """Test parsing dash format (DD-MM-YYYY)."""
        result = parse_date('15-05-2024')
        self.assertEqual(result, date(2024, 5, 15))

    def test_parse_date_invalid_format(self):
        """Test parsing invalid format returns None."""
        self.assertIsNone(parse_date('May 15, 2024'))
        self.assertIsNone(parse_date('invalid'))

    def test_parse_date_pandas_timestamp(self):
        """Test parsing pandas Timestamp."""
        ts = pd.Timestamp('2024-05-15')
        result = parse_date(ts)
        self.assertEqual(result, date(2024, 5, 15))


class CleanValueTests(TestCase):
    """Tests for the clean_value utility function."""

    def test_clean_value_none(self):
        """Test cleaning None returns empty string."""
        self.assertEqual(clean_value(None), '')

    def test_clean_value_nan(self):
        """Test cleaning NaN returns empty string."""
        self.assertEqual(clean_value(float('nan')), '')

    def test_clean_value_string(self):
        """Test cleaning string strips whitespace."""
        self.assertEqual(clean_value('  hello  '), 'hello')
        self.assertEqual(clean_value('hello'), 'hello')

    def test_clean_value_number(self):
        """Test cleaning number converts to string."""
        self.assertEqual(clean_value(123), '123')
        self.assertEqual(clean_value(45.67), '45.67')


class BulkImportTestCase(TenantTestCase):
    """Base test case with common setup for bulk import tests."""

    @classmethod
    def setup_tenant(cls, tenant):
        """Called when tenant is created."""
        tenant.name = 'Test School'
        tenant.short_name = 'TEST'

    def setUp(self):
        """Set up test data."""
        super().setUp()
        self.client = TenantClient(self.tenant)

        # Create admin user
        self.admin_user = User.objects.create_user(
            email='admin@school.com',
            password='testpass123',
            is_school_admin=True
        )
        self.client.login(email='admin@school.com', password='testpass123')

        # Create a programme and class
        self.programme = Programme.objects.create(
            name='General Arts',
            code='ART'
        )
        self.test_class = Class.objects.create(
            level_type=Class.LevelType.BASIC,
            level_number=1,
            section='A',
            name='B1-A',
            is_active=True
        )

        # Create academic year
        self.academic_year = AcademicYear.objects.create(
            name='2024/2025',
            start_date=date(2024, 9, 1),
            end_date=date(2025, 7, 31),
            is_current=True
        )

    def create_csv_file(self, data):
        """Create a CSV file from data dictionary."""
        df = pd.DataFrame(data)
        csv_buffer = io.BytesIO()
        df.to_csv(csv_buffer, index=False)
        csv_buffer.seek(0)
        return SimpleUploadedFile(
            'students.csv',
            csv_buffer.read(),
            content_type='text/csv'
        )

    def create_excel_file(self, data):
        """Create an Excel file from data dictionary."""
        df = pd.DataFrame(data)
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        excel_buffer.seek(0)
        return SimpleUploadedFile(
            'students.xlsx',
            excel_buffer.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    def get_valid_student_data(self):
        """Get valid student data for import."""
        return {
            'first_name': ['John', 'Jane'],
            'middle_name': ['', 'Marie'],
            'last_name': ['Doe', 'Smith'],
            'date_of_birth': ['2010-05-15', '2011-08-22'],
            'gender': ['M', 'F'],
            'guardian_name': ['James Doe', 'Mary Smith'],
            # Use phone numbers without leading zeros to avoid pandas type conversion issues
            'guardian_phone': ['233241234567', '233551234567'],
            'guardian_email': ['james@email.com', ''],
            'admission_number': ['STU-2024-001', 'STU-2024-002'],
            'admission_date': ['2024-09-01', '2024-09-01'],
            'class_name': ['B1-A', 'B1-A'],
        }


class BulkImportViewTests(BulkImportTestCase):
    """Tests for the bulk_import view."""

    def test_bulk_import_get_returns_form(self):
        """Test GET request returns the import form."""
        response = self.client.get(reverse('students:bulk_import'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('expected_columns', response.context)
        # Check that all base columns are present (SHS schools may have additional columns)
        for col in BASE_COLUMNS:
            self.assertIn(col, response.context['expected_columns'])

    def test_bulk_import_requires_authentication(self):
        """Test view requires authentication."""
        self.client.logout()
        response = self.client.get(reverse('students:bulk_import'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)

    def test_bulk_import_requires_admin(self):
        """Test view requires admin permission."""
        # Create non-admin user
        User.objects.create_user(
            email='user@school.com',
            password='testpass123'
        )
        self.client.login(email='user@school.com', password='testpass123')
        response = self.client.get(reverse('students:bulk_import'))
        self.assertEqual(response.status_code, 302)

    def test_bulk_import_post_without_file(self):
        """Test POST without file returns error."""
        response = self.client.post(reverse('students:bulk_import'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('error', response.context)
        self.assertIn('select a file', response.context['error'])

    def test_bulk_import_post_invalid_file_type(self):
        """Test POST with invalid file type returns error."""
        file = SimpleUploadedFile('students.txt', b'content', content_type='text/plain')
        response = self.client.post(
            reverse('students:bulk_import'),
            {'file': file}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('error', response.context)
        self.assertIn('.xlsx and .csv', response.context['error'])

    def test_bulk_import_post_empty_file(self):
        """Test POST with empty file returns error."""
        df = pd.DataFrame()
        csv_buffer = io.BytesIO()
        df.to_csv(csv_buffer, index=False)
        csv_buffer.seek(0)
        file = SimpleUploadedFile('empty.csv', csv_buffer.read(), content_type='text/csv')

        response = self.client.post(
            reverse('students:bulk_import'),
            {'file': file}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('error', response.context)
        # Error can be "empty" or "No columns to parse"
        self.assertTrue(
            'empty' in response.context['error'].lower() or
            'no columns' in response.context['error'].lower()
        )

    def test_bulk_import_valid_csv(self):
        """Test POST with valid CSV returns preview."""
        file = self.create_csv_file(self.get_valid_student_data())
        response = self.client.post(
            reverse('students:bulk_import'),
            {'file': file}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('valid_rows', response.context)
        self.assertEqual(len(response.context['valid_rows']), 2)
        self.assertEqual(response.context['valid_count'], 2)
        self.assertEqual(response.context['error_count'], 0)

    def test_bulk_import_valid_excel(self):
        """Test POST with valid Excel file returns preview."""
        file = self.create_excel_file(self.get_valid_student_data())
        response = self.client.post(
            reverse('students:bulk_import'),
            {'file': file}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('valid_rows', response.context)
        self.assertEqual(len(response.context['valid_rows']), 2)

    def test_bulk_import_missing_required_fields(self):
        """Test POST with missing required fields returns errors."""
        data = {
            'first_name': ['John', ''],  # Second row missing first_name
            'last_name': ['Doe', 'Smith'],
            'date_of_birth': ['2010-05-15', '2011-08-22'],
            'gender': ['M', 'F'],
            'guardian_name': ['James Doe', 'Mary Smith'],
            # Use phone numbers without leading zeros to avoid pandas type conversion issues
            'guardian_phone': ['233241234567', '233551234567'],
            'admission_number': ['STU-2024-001', 'STU-2024-002'],
            'admission_date': ['2024-09-01', '2024-09-01'],
        }
        file = self.create_csv_file(data)
        response = self.client.post(
            reverse('students:bulk_import'),
            {'file': file}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['valid_count'], 1)
        self.assertEqual(response.context['error_count'], 1)
        self.assertIn('First name is required', response.context['all_errors'][0]['errors'])

    def test_bulk_import_duplicate_admission_number(self):
        """Test POST with duplicate admission number returns error."""
        # Create existing student
        guardian = Guardian.objects.create(
            full_name='Existing Guardian',
            phone_number='0201234567'
        )
        student = Student.objects.create(
            first_name='Existing',
            last_name='Student',
            date_of_birth=date(2010, 1, 1),
            gender='M',
            admission_number='STU-2024-001',
            admission_date=date(2024, 1, 1),
        )
        student.add_guardian(guardian, Guardian.Relationship.GUARDIAN, is_primary=True)

        data = self.get_valid_student_data()
        file = self.create_csv_file(data)
        response = self.client.post(
            reverse('students:bulk_import'),
            {'file': file}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['error_count'], 1)
        error_messages = response.context['all_errors'][0]['errors']
        self.assertTrue(any('already exists' in e for e in error_messages))

    def test_bulk_import_invalid_class(self):
        """Test POST with non-existent class returns error."""
        data = self.get_valid_student_data()
        data['class_name'] = ['INVALID-CLASS', 'B1-A']
        file = self.create_csv_file(data)
        response = self.client.post(
            reverse('students:bulk_import'),
            {'file': file}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['error_count'], 1)
        error_messages = response.context['all_errors'][0]['errors']
        self.assertTrue(any('not found' in e for e in error_messages))

    def test_bulk_import_invalid_gender(self):
        """Test POST with invalid gender returns error."""
        data = self.get_valid_student_data()
        data['gender'] = ['X', 'F']  # Invalid gender
        file = self.create_csv_file(data)
        response = self.client.post(
            reverse('students:bulk_import'),
            {'file': file}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['error_count'], 1)

    def test_bulk_import_creates_guardian(self):
        """Test bulk import creates guardian during confirm step."""
        data = self.get_valid_student_data()
        file = self.create_csv_file(data)

        self.assertEqual(Guardian.objects.count(), 0)

        # Step 1: Preview (parses file, validates, stores in session)
        response = self.client.post(
            reverse('students:bulk_import'),
            {'file': file}
        )
        self.assertEqual(response.status_code, 200)
        # Guardians are deferred to confirm step
        self.assertEqual(Guardian.objects.count(), 0)

        # Step 2: Confirm (creates students and guardians)
        response = self.client.post(
            reverse('students:bulk_import_confirm')
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Guardian.objects.count(), 2)

    def test_bulk_import_reuses_existing_guardian(self):
        """Test bulk import reuses guardian with same phone."""
        # Create guardian with normalized phone (233551234567 becomes 0551234567 after validation)
        existing_guardian = Guardian.objects.create(
            full_name='Pre-existing Guardian',
            phone_number='0551234567'  # Normalized form of 233551234567
        )

        data = self.get_valid_student_data()
        file = self.create_csv_file(data)
        response = self.client.post(
            reverse('students:bulk_import'),
            {'file': file}
        )
        self.assertEqual(response.status_code, 200)

        # Verify the existing guardian is referenced in valid_rows for Jane
        valid_rows = response.context['valid_rows']
        jane_row = next(r for r in valid_rows if r['first_name'] == 'Jane')
        self.assertEqual(jane_row['guardian_pk'], existing_guardian.pk)
        self.assertEqual(jane_row['guardian_name'], 'Mary Smith')  # Name from CSV, not from DB

    def test_bulk_import_stores_session_data(self):
        """Test bulk import stores valid data in session."""
        data = self.get_valid_student_data()
        file = self.create_csv_file(data)
        response = self.client.post(
            reverse('students:bulk_import'),
            {'file': file}
        )
        self.assertEqual(response.status_code, 200)
        session = self.client.session
        self.assertIn('bulk_import_data', session)
        stored_data = json.loads(session['bulk_import_data'])
        self.assertEqual(len(stored_data), 2)

    def test_bulk_import_gender_normalization(self):
        """Test gender is normalized (MALE -> M, FEMALE -> F)."""
        data = self.get_valid_student_data()
        data['gender'] = ['MALE', 'FEMALE']
        file = self.create_csv_file(data)
        response = self.client.post(
            reverse('students:bulk_import'),
            {'file': file}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['valid_count'], 2)
        valid_rows = response.context['valid_rows']
        self.assertEqual(valid_rows[0]['gender'], 'M')
        self.assertEqual(valid_rows[1]['gender'], 'F')


class BulkImportConfirmViewTests(BulkImportTestCase):
    """Tests for the bulk_import_confirm view."""

    def test_bulk_import_confirm_get_not_allowed(self):
        """Test GET request is not allowed."""
        response = self.client.get(reverse('students:bulk_import_confirm'))
        self.assertEqual(response.status_code, 405)

    def test_bulk_import_confirm_no_session_data(self):
        """Test POST without session data returns error."""
        response = self.client.post(reverse('students:bulk_import_confirm'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('error', response.context)
        self.assertIn('Session expired', response.context['error'])

    def test_bulk_import_confirm_invalid_session_data(self):
        """Test POST with invalid session data returns error."""
        session = self.client.session
        session['bulk_import_data'] = 'invalid json {'
        session.save()

        response = self.client.post(reverse('students:bulk_import_confirm'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('error', response.context)
        self.assertIn('Invalid session data', response.context['error'])

    def test_bulk_import_confirm_creates_students(self):
        """Test POST with valid session data creates students."""
        # First, upload file to create session data
        data = self.get_valid_student_data()
        file = self.create_csv_file(data)
        self.client.post(reverse('students:bulk_import'), {'file': file})

        # Confirm import
        self.assertEqual(Student.objects.count(), 0)
        response = self.client.post(reverse('students:bulk_import_confirm'))

        self.assertEqual(response.status_code, 302)  # Redirects on success
        self.assertEqual(Student.objects.count(), 2)

        # Verify student data
        john = Student.objects.get(admission_number='STU-2024-001')
        self.assertEqual(john.first_name, 'John')
        self.assertEqual(john.last_name, 'Doe')
        self.assertEqual(john.gender, 'M')
        self.assertTrue(john.guardians.exists())
        self.assertEqual(john.current_class, self.test_class)

    def test_bulk_import_confirm_creates_enrollments(self):
        """Test POST creates enrollments when academic year exists."""
        data = self.get_valid_student_data()
        file = self.create_csv_file(data)
        self.client.post(reverse('students:bulk_import'), {'file': file})

        self.assertEqual(Enrollment.objects.count(), 0)
        self.client.post(reverse('students:bulk_import_confirm'))

        # Both students should have enrollments
        self.assertEqual(Enrollment.objects.count(), 2)
        enrollment = Enrollment.objects.first()
        self.assertEqual(enrollment.academic_year, self.academic_year)
        self.assertEqual(enrollment.status, Enrollment.Status.ACTIVE)

    def test_bulk_import_confirm_no_enrollment_without_class(self):
        """Test no enrollment created for students without class."""
        data = self.get_valid_student_data()
        data['class_name'] = ['', '']  # No class assigned
        file = self.create_csv_file(data)
        self.client.post(reverse('students:bulk_import'), {'file': file})

        self.client.post(reverse('students:bulk_import_confirm'))

        self.assertEqual(Student.objects.count(), 2)
        self.assertEqual(Enrollment.objects.count(), 0)

    def test_bulk_import_confirm_clears_session(self):
        """Test session data is cleared after confirm."""
        data = self.get_valid_student_data()
        file = self.create_csv_file(data)
        self.client.post(reverse('students:bulk_import'), {'file': file})

        self.assertIn('bulk_import_data', self.client.session)
        self.client.post(reverse('students:bulk_import_confirm'))

        # Session should be cleared
        session = self.client.session
        self.assertNotIn('bulk_import_data', session)

    def test_bulk_import_confirm_htmx_response(self):
        """Test HTMX request returns refresh header."""
        data = self.get_valid_student_data()
        file = self.create_csv_file(data)
        self.client.post(reverse('students:bulk_import'), {'file': file})

        response = self.client.post(
            reverse('students:bulk_import_confirm'),
            HTTP_HX_REQUEST='true'
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['HX-Refresh'], 'true')


class BulkImportTemplateViewTests(BulkImportTestCase):
    """Tests for the bulk_import_template view."""

    def test_bulk_import_template_returns_excel(self):
        """Test GET returns Excel file."""
        response = self.client.get(reverse('students:bulk_import_template'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertIn('student_import_template.xlsx', response['Content-Disposition'])

    def test_bulk_import_template_has_correct_columns(self):
        """Test template has expected columns."""
        response = self.client.get(reverse('students:bulk_import_template'))

        # Read the Excel content
        content = b''.join(response.streaming_content)
        df = pd.read_excel(io.BytesIO(content))

        expected = [
            'first_name', 'middle_name', 'last_name', 'date_of_birth', 'gender',
            'guardian_name', 'guardian_phone', 'guardian_email', 'guardian_relationship',
            'admission_number', 'admission_date', 'class_name'
        ]
        for col in expected:
            self.assertIn(col, df.columns)

    def test_bulk_import_template_has_sample_data(self):
        """Test template has sample data rows."""
        response = self.client.get(reverse('students:bulk_import_template'))

        content = b''.join(response.streaming_content)
        df = pd.read_excel(io.BytesIO(content))

        # Template has at least 2 sample rows (3 for schools with both Basic and SHS)
        self.assertGreaterEqual(len(df), 2)
        self.assertEqual(df.iloc[0]['first_name'], 'John')
        self.assertEqual(df.iloc[1]['first_name'], 'Jane')


class BulkImportIntegrationTests(BulkImportTestCase):
    """Integration tests for the complete bulk import workflow."""

    def test_full_import_workflow(self):
        """Test complete workflow: upload -> preview -> confirm."""
        # Step 1: Upload file
        data = self.get_valid_student_data()
        file = self.create_csv_file(data)
        response = self.client.post(reverse('students:bulk_import'), {'file': file})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['valid_count'], 2)

        # Step 2: Confirm import
        response = self.client.post(reverse('students:bulk_import_confirm'))

        self.assertEqual(response.status_code, 302)

        # Step 3: Verify data
        self.assertEqual(Student.objects.count(), 2)
        self.assertEqual(Guardian.objects.count(), 2)
        self.assertEqual(Enrollment.objects.count(), 2)

        # Verify relationships
        john = Student.objects.get(first_name='John')
        primary_guardian = john.get_primary_guardian()
        self.assertIsNotNone(primary_guardian)
        self.assertEqual(primary_guardian.full_name, 'James Doe')
        self.assertEqual(john.current_class.name, 'B1-A')

        enrollment = john.enrollments.first()
        self.assertEqual(enrollment.class_assigned, self.test_class)
        self.assertEqual(enrollment.academic_year, self.academic_year)

    def test_import_with_mixed_valid_invalid_rows(self):
        """Test import with some valid and some invalid rows."""
        data = {
            'first_name': ['John', '', 'Alice'],  # Second row invalid
            'last_name': ['Doe', 'Smith', 'Wonder'],
            'date_of_birth': ['2010-05-15', '2011-08-22', '2012-01-01'],
            'gender': ['M', 'F', 'F'],
            'guardian_name': ['James', 'Mary', 'Bob'],
            # Use phone numbers without leading zeros to avoid pandas type conversion issues
            'guardian_phone': ['233241234567', '233551234567', '233551234568'],
            'admission_number': ['STU-001', 'STU-002', 'STU-003'],
            'admission_date': ['2024-09-01', '2024-09-01', '2024-09-01'],
        }
        file = self.create_csv_file(data)
        response = self.client.post(reverse('students:bulk_import'), {'file': file})

        # 2 valid, 1 invalid
        self.assertEqual(response.context['valid_count'], 2)
        self.assertEqual(response.context['error_count'], 1)

        # Confirm import (only valid rows)
        self.client.post(reverse('students:bulk_import_confirm'))
        self.assertEqual(Student.objects.count(), 2)

    def test_import_without_current_academic_year(self):
        """Test import works without current academic year (no enrollments)."""
        # Remove current academic year
        self.academic_year.is_current = False
        self.academic_year.save()

        data = self.get_valid_student_data()
        file = self.create_csv_file(data)
        self.client.post(reverse('students:bulk_import'), {'file': file})
        self.client.post(reverse('students:bulk_import_confirm'))

        # Students created but no enrollments
        self.assertEqual(Student.objects.count(), 2)
        self.assertEqual(Enrollment.objects.count(), 0)


# =============================================================================
# PROMOTION TESTS (Static Bucket Model)
# =============================================================================

class PromotionTestCase(TenantTestCase):
    """Base test case for promotion tests."""

    @classmethod
    def setup_tenant(cls, tenant):
        """Called when tenant is created."""
        tenant.name = 'Test School'
        tenant.short_name = 'TEST'

    def setUp(self):
        """Set up test data."""
        super().setUp()
        self.client = TenantClient(self.tenant)

        # Create admin user
        self.admin_user = User.objects.create_user(
            email='admin@school.com',
            password='testpass123',
            is_school_admin=True
        )
        self.client.login(email='admin@school.com', password='testpass123')

        # Create programmes
        self.programme = Programme.objects.create(
            name='General Arts',
            code='ART'
        )

        # Create classes (both source and target must exist)
        self.class_b1 = Class.objects.create(
            level_type=Class.LevelType.BASIC,
            level_number=1,
            section='A',
            is_active=True
        )
        self.class_b2 = Class.objects.create(
            level_type=Class.LevelType.BASIC,
            level_number=2,
            section='A',
            is_active=True
        )
        self.class_shs3 = Class.objects.create(
            level_type=Class.LevelType.SHS,
            level_number=3,
            section='A',
            programme=self.programme,
            is_active=True
        )

        # Create a teacher for subject assignments
        self.teacher = Teacher.objects.create(
            first_name='Test',
            last_name='Teacher',
            email='teacher@school.com',
            phone_number='233201111111',
            date_of_birth=date(1985, 1, 1),
            gender='M',
        )

        # Create current academic year
        self.current_year = AcademicYear.objects.create(
            name='2024/2025',
            start_date=date(2024, 9, 1),
            end_date=date(2025, 7, 31),
            is_current=True
        )

        # Create next academic year
        self.next_year = AcademicYear.objects.create(
            name='2025/2026',
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 31),
            is_current=False
        )

        # Create guardian
        self.guardian = Guardian.objects.create(
            full_name='Test Guardian',
            phone_number='233201234567'
        )

    def create_student_with_enrollment(self, first_name, admission_number, class_assigned):
        """Helper to create a student with an active enrollment."""
        student = Student.objects.create(
            first_name=first_name,
            last_name='Test',
            date_of_birth=date(2010, 1, 1),
            gender='M',
            admission_number=admission_number,
            admission_date=date(2024, 1, 1),
            current_class=class_assigned,
            status=Student.Status.ACTIVE
        )
        student.add_guardian(self.guardian, Guardian.Relationship.GUARDIAN, is_primary=True)
        enrollment = Enrollment.objects.create(
            student=student,
            academic_year=self.current_year,
            class_assigned=class_assigned,
            status=Enrollment.Status.ACTIVE
        )
        return student, enrollment


class PromotionViewTests(PromotionTestCase):
    """Tests for the promotion view."""

    def _find_option_label(self, class_options, class_obj):
        """Helper to find a class label in the flat class_options list."""
        target_url = reverse('students:promotion_detail', args=[class_obj.pk])
        for url, label in class_options:
            if url == target_url:
                return label
        return None

    def test_promotion_requires_authentication(self):
        """Test view requires authentication."""
        self.client.logout()
        response = self.client.get(reverse('students:promotion'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)

    def test_promotion_requires_admin(self):
        """Test view requires admin permission."""
        User.objects.create_user(
            email='user@school.com',
            password='testpass123'
        )
        self.client.login(email='user@school.com', password='testpass123')
        response = self.client.get(reverse('students:promotion'))
        self.assertEqual(response.status_code, 302)

    def test_promotion_no_current_year(self):
        """Test promotion page shows error when no current academic year."""
        self.current_year.is_current = False
        self.current_year.save()

        response = self.client.get(reverse('students:promotion'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('error', response.context)
        self.assertIn('No current academic year', response.context['error'])

    def test_promotion_shows_classes_with_counts(self):
        """Test promotion page shows classes with enrolled counts in options."""
        self.create_student_with_enrollment('John', 'STU-001', self.class_b1)
        self.create_student_with_enrollment('Jane', 'STU-002', self.class_b1)
        self.create_student_with_enrollment('Bob', 'STU-003', self.class_b2)

        response = self.client.get(reverse('students:promotion'))
        self.assertEqual(response.status_code, 200)

        class_options = response.context['class_options']
        b1_label = self._find_option_label(class_options, self.class_b1)
        b2_label = self._find_option_label(class_options, self.class_b2)

        self.assertIsNotNone(b1_label)
        self.assertIn('2 students', b1_label)
        self.assertIsNotNone(b2_label)
        self.assertIn('1 student', b2_label)

    def test_promotion_identifies_final_level(self):
        """Test promotion page identifies SHS3 as final level in label."""
        self.create_student_with_enrollment('Senior', 'STU-001', self.class_shs3)

        response = self.client.get(reverse('students:promotion'))
        self.assertEqual(response.status_code, 200)

        class_options = response.context['class_options']
        shs3_label = self._find_option_label(class_options, self.class_shs3)
        self.assertIsNotNone(shs3_label)
        self.assertIn('Final year', shs3_label)

    def test_promotion_shows_next_academic_year(self):
        """Test promotion page shows next academic year."""
        response = self.client.get(reverse('students:promotion'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['next_year'], self.next_year)
        self.assertEqual(response.context['current_year'], self.current_year)

    def test_promotion_detects_has_target(self):
        """Test promotion_detail detects when a natural target class exists."""
        self.create_student_with_enrollment('John', 'STU-001', self.class_b1)

        response = self.client.get(
            reverse('students:promotion_detail', args=[self.class_b1.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['has_target'])
        self.assertEqual(response.context['natural_target_pk'], str(self.class_b2.pk))

    def test_promotion_no_target_when_missing(self):
        """Test promotion_detail shows no target when next-level class doesn't exist."""
        # Delete B2 so B1 has no target
        self.class_b2.delete()
        self.create_student_with_enrollment('John', 'STU-001', self.class_b1)

        response = self.client.get(
            reverse('students:promotion_detail', args=[self.class_b1.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['has_target'])

    def test_promotion_excludes_inactive_students_from_count(self):
        """Test promotion excludes students with non-active status from counts."""
        self.create_student_with_enrollment('Active', 'STU-001', self.class_b1)

        # Create inactive student with enrollment
        inactive_student = Student.objects.create(
            first_name='Inactive',
            last_name='Test',
            date_of_birth=date(2010, 1, 1),
            gender='M',
            admission_number='STU-002',
            admission_date=date(2024, 1, 1),
            current_class=self.class_b1,
            status=Student.Status.WITHDRAWN
        )
        inactive_student.add_guardian(self.guardian, Guardian.Relationship.GUARDIAN, is_primary=True)
        Enrollment.objects.create(
            student=inactive_student,
            academic_year=self.current_year,
            class_assigned=self.class_b1,
            status=Enrollment.Status.ACTIVE
        )

        response = self.client.get(reverse('students:promotion'))
        class_options = response.context['class_options']

        b1_label = self._find_option_label(class_options, self.class_b1)
        self.assertIn('1 student', b1_label)  # Only active student counted


class PromotionProcessViewTests(PromotionTestCase):
    """Tests for the class-level promotion_process view."""

    def test_promotion_process_get_not_allowed(self):
        """Test GET request is not allowed."""
        response = self.client.get(reverse('students:promotion_process'))
        self.assertEqual(response.status_code, 405)

    def test_promotion_process_requires_params(self):
        """Test POST without required params returns error."""
        response = self.client.post(reverse('students:promotion_process'), {})
        self.assertEqual(response.status_code, 302)

    def test_promote_students_to_target_class(self):
        """Test promoting students moves them to the target class (static bucket)."""
        student, enrollment = self.create_student_with_enrollment('John', 'STU-001', self.class_b1)

        response = self.client.post(reverse('students:promotion_process'), {
            'class_id': str(self.class_b1.pk),
            'next_year': str(self.next_year.pk),
            'target_class_id': str(self.class_b2.pk),
            f'action_{student.pk}': 'promote',
        })
        self.assertEqual(response.status_code, 302)

        # Source class should be UNCHANGED
        self.class_b1.refresh_from_db()
        self.assertEqual(self.class_b1.level_number, 1)
        self.assertEqual(self.class_b1.name, 'B1-A')

        # Old enrollment should be PROMOTED
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.status, Enrollment.Status.PROMOTED)

        # New enrollment created in the TARGET class (B2-A)
        new_enrollment = Enrollment.objects.get(
            student=student, academic_year=self.next_year
        )
        self.assertEqual(new_enrollment.class_assigned, self.class_b2)
        self.assertEqual(new_enrollment.status, Enrollment.Status.ACTIVE)

        # Student's current_class should be the target
        student.refresh_from_db()
        self.assertEqual(student.current_class, self.class_b2)

    def test_promote_fails_without_target_class(self):
        """Test promotion fails when no target_class_id is provided."""
        student, enrollment = self.create_student_with_enrollment('John', 'STU-001', self.class_b1)

        response = self.client.post(reverse('students:promotion_process'), {
            'class_id': str(self.class_b1.pk),
            'next_year': str(self.next_year.pk),
            f'action_{student.pk}': 'promote',
        })
        self.assertEqual(response.status_code, 302)

        # Enrollment should be unchanged
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.status, Enrollment.Status.ACTIVE)

        # Class should be unchanged
        self.class_b1.refresh_from_db()
        self.assertEqual(self.class_b1.level_number, 1)

    def test_promote_subject_enrollments_transferred(self):
        """Test that subject enrollments are deactivated in source and created in target."""
        # Create subjects for B1
        math = Subject.objects.create(name='Math', code='MATH', short_name='Math', is_core=True)
        eng = Subject.objects.create(name='English', code='ENG', short_name='Eng', is_core=True)
        cs_b1_math = ClassSubject.objects.create(class_assigned=self.class_b1, subject=math, teacher=self.teacher)
        cs_b1_eng = ClassSubject.objects.create(class_assigned=self.class_b1, subject=eng, teacher=self.teacher)

        # Create subjects for B2 (target)
        ClassSubject.objects.create(class_assigned=self.class_b2, subject=math, teacher=self.teacher)
        ClassSubject.objects.create(class_assigned=self.class_b2, subject=eng, teacher=self.teacher)

        student, enrollment = self.create_student_with_enrollment('John', 'STU-001', self.class_b1)

        # Enroll student in B1 subjects
        StudentSubjectEnrollment.objects.create(student=student, class_subject=cs_b1_math)
        StudentSubjectEnrollment.objects.create(student=student, class_subject=cs_b1_eng)

        response = self.client.post(reverse('students:promotion_process'), {
            'class_id': str(self.class_b1.pk),
            'next_year': str(self.next_year.pk),
            'target_class_id': str(self.class_b2.pk),
            f'action_{student.pk}': 'promote',
        })
        self.assertEqual(response.status_code, 302)

        # Old subject enrollments should be deactivated
        old_subj = StudentSubjectEnrollment.objects.filter(
            student=student, class_subject__class_assigned=self.class_b1
        )
        self.assertTrue(all(not s.is_active for s in old_subj))

        # New subject enrollments should exist in target class
        new_subj = StudentSubjectEnrollment.objects.filter(
            student=student, class_subject__class_assigned=self.class_b2, is_active=True
        )
        self.assertEqual(new_subj.count(), 2)

    def test_promote_already_processed_guard(self):
        """Test that double-processing is blocked."""
        student, enrollment = self.create_student_with_enrollment('John', 'STU-001', self.class_b1)

        # First promotion
        self.client.post(reverse('students:promotion_process'), {
            'class_id': str(self.class_b1.pk),
            'next_year': str(self.next_year.pk),
            'target_class_id': str(self.class_b2.pk),
            f'action_{student.pk}': 'promote',
        })

        # Second attempt should be blocked
        response = self.client.post(reverse('students:promotion_process'), {
            'class_id': str(self.class_b1.pk),
            'next_year': str(self.next_year.pk),
            'target_class_id': str(self.class_b2.pk),
            f'action_{student.pk}': 'promote',
        })
        self.assertEqual(response.status_code, 302)

        # Should still only have one next-year enrollment
        next_enrollments = Enrollment.objects.filter(
            student=student, academic_year=self.next_year
        )
        self.assertEqual(next_enrollments.count(), 1)

    def test_repeat_student_moved_to_target(self):
        """Test repeater is moved to a target class at the same level."""
        # Create another B1 class for the repeater
        class_b1b = Class.objects.create(
            level_type=Class.LevelType.BASIC,
            level_number=1, section='B', is_active=True,
        )

        student1, enrollment1 = self.create_student_with_enrollment('Promote', 'STU-001', self.class_b1)
        student2, enrollment2 = self.create_student_with_enrollment('Repeat', 'STU-002', self.class_b1)

        response = self.client.post(reverse('students:promotion_process'), {
            'class_id': str(self.class_b1.pk),
            'next_year': str(self.next_year.pk),
            'target_class_id': str(self.class_b2.pk),
            f'action_{student1.pk}': 'promote',
            f'action_{student2.pk}': 'repeat',
            f'repeat_target_{student2.pk}': str(class_b1b.pk),
        })
        self.assertEqual(response.status_code, 302)

        # Repeater should be moved to B1-B
        student2.refresh_from_db()
        enrollment2.refresh_from_db()
        self.assertEqual(student2.current_class, class_b1b)
        self.assertEqual(enrollment2.status, Enrollment.Status.REPEATED)

        # New enrollment for repeater in B1-B
        new_enrollment = Enrollment.objects.get(
            student=student2, academic_year=self.next_year
        )
        self.assertEqual(new_enrollment.class_assigned, class_b1b)

    def test_repeat_student_in_same_class(self):
        """Test repeater can stay in the same class."""
        student, enrollment = self.create_student_with_enrollment('Repeat', 'STU-001', self.class_b1)

        response = self.client.post(reverse('students:promotion_process'), {
            'class_id': str(self.class_b1.pk),
            'next_year': str(self.next_year.pk),
            'target_class_id': str(self.class_b2.pk),
            f'action_{student.pk}': 'repeat',
            f'repeat_target_{student.pk}': str(self.class_b1.pk),
        })
        self.assertEqual(response.status_code, 302)

        student.refresh_from_db()
        enrollment.refresh_from_db()
        self.assertEqual(student.current_class, self.class_b1)
        self.assertEqual(enrollment.status, Enrollment.Status.REPEATED)

        new_enrollment = Enrollment.objects.get(
            student=student, academic_year=self.next_year
        )
        self.assertEqual(new_enrollment.class_assigned, self.class_b1)

    def test_graduate_student_from_final_class(self):
        """Test graduating students from a final-year class."""
        student, enrollment = self.create_student_with_enrollment('Senior', 'STU-003', self.class_shs3)

        response = self.client.post(reverse('students:promotion_process'), {
            'class_id': str(self.class_shs3.pk),
            'next_year': str(self.next_year.pk),
            f'action_{student.pk}': 'graduate',
        })
        self.assertEqual(response.status_code, 302)

        student.refresh_from_db()
        enrollment.refresh_from_db()

        self.assertEqual(enrollment.status, Enrollment.Status.GRADUATED)
        self.assertEqual(student.status, Student.Status.GRADUATED)
        self.assertIsNone(student.current_class)

        # No new enrollment created for graduates
        self.assertFalse(
            Enrollment.objects.filter(
                student=student, academic_year=self.next_year
            ).exists()
        )

    def test_skip_student_unchanged(self):
        """Test skipping a student leaves enrollment unchanged."""
        student, enrollment = self.create_student_with_enrollment('Skip', 'STU-004', self.class_b1)

        response = self.client.post(reverse('students:promotion_process'), {
            'class_id': str(self.class_b1.pk),
            'next_year': str(self.next_year.pk),
            'target_class_id': str(self.class_b2.pk),
            f'action_{student.pk}': 'skip',
        })
        self.assertEqual(response.status_code, 302)

        enrollment.refresh_from_db()
        self.assertEqual(enrollment.status, Enrollment.Status.ACTIVE)

    def test_class_name_snapshot_saved(self):
        """Test that enrollment class_name snapshot is saved."""
        student, enrollment = self.create_student_with_enrollment('John', 'STU-001', self.class_b1)

        response = self.client.post(reverse('students:promotion_process'), {
            'class_id': str(self.class_b1.pk),
            'next_year': str(self.next_year.pk),
            'target_class_id': str(self.class_b2.pk),
            f'action_{student.pk}': 'promote',
        })
        self.assertEqual(response.status_code, 302)

        # New enrollment should have the target class name snapshot
        new_enrollment = Enrollment.objects.get(
            student=student, academic_year=self.next_year
        )
        self.assertEqual(new_enrollment.class_name, 'B2-A')


class PromotionIntegrationTests(PromotionTestCase):
    """Integration tests for the complete promotion workflow (static bucket model)."""

    def test_full_class_promotion_workflow(self):
        """Test complete workflow: view -> promote -> verify students in target class."""
        student1, _ = self.create_student_with_enrollment('John', 'STU-001', self.class_b1)
        student2, _ = self.create_student_with_enrollment('Jane', 'STU-002', self.class_b1)

        # Step 1: View promotion page
        response = self.client.get(reverse('students:promotion'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('class_options', response.context)

        # Step 2: Process promotion with target_class_id
        response = self.client.post(reverse('students:promotion_process'), {
            'class_id': str(self.class_b1.pk),
            'next_year': str(self.next_year.pk),
            'target_class_id': str(self.class_b2.pk),
            f'action_{student1.pk}': 'promote',
            f'action_{student2.pk}': 'promote',
        })
        self.assertEqual(response.status_code, 302)

        # Step 3: Verify results
        old_enrollments = Enrollment.objects.filter(
            academic_year=self.current_year,
            status=Enrollment.Status.PROMOTED
        )
        self.assertEqual(old_enrollments.count(), 2)

        new_enrollments = Enrollment.objects.filter(
            academic_year=self.next_year,
            status=Enrollment.Status.ACTIVE
        )
        self.assertEqual(new_enrollments.count(), 2)

        # Source class is UNCHANGED
        self.class_b1.refresh_from_db()
        self.assertEqual(self.class_b1.level_number, 1)
        self.assertEqual(self.class_b1.name, 'B1-A')

        # Students are now in B2-A
        student1.refresh_from_db()
        student2.refresh_from_db()
        self.assertEqual(student1.current_class, self.class_b2)
        self.assertEqual(student2.current_class, self.class_b2)

    def test_enrollment_history_tracking(self):
        """Test that promotion creates proper enrollment history with separate classes."""
        student, original_enrollment = self.create_student_with_enrollment('John', 'STU-001', self.class_b1)

        self.client.post(reverse('students:promotion_process'), {
            'class_id': str(self.class_b1.pk),
            'next_year': str(self.next_year.pk),
            'target_class_id': str(self.class_b2.pk),
            f'action_{student.pk}': 'promote',
        })

        enrollments = student.enrollments.order_by('academic_year__start_date')
        self.assertEqual(enrollments.count(), 2)

        first = enrollments[0]
        self.assertEqual(first.academic_year, self.current_year)
        self.assertEqual(first.status, Enrollment.Status.PROMOTED)
        self.assertEqual(first.class_assigned, self.class_b1)
        self.assertEqual(first.class_name, 'B1-A')

        second = enrollments[1]
        self.assertEqual(second.academic_year, self.next_year)
        # New enrollment points to the TARGET class
        self.assertEqual(second.class_assigned, self.class_b2)
        self.assertEqual(second.class_name, 'B2-A')
        self.assertEqual(second.status, Enrollment.Status.ACTIVE)
        self.assertEqual(second.promoted_from, first)

    def test_mixed_actions_in_same_class(self):
        """Test different actions for students in the same class."""
        # Create another B1 class for repeaters
        class_b1b = Class.objects.create(
            level_type=Class.LevelType.BASIC,
            level_number=1, section='B', is_active=True,
        )

        student1, _ = self.create_student_with_enrollment('Promote', 'STU-001', self.class_b1)
        student2, _ = self.create_student_with_enrollment('Repeat', 'STU-002', self.class_b1)
        student3, _ = self.create_student_with_enrollment('Skip', 'STU-003', self.class_b1)

        self.client.post(reverse('students:promotion_process'), {
            'class_id': str(self.class_b1.pk),
            'next_year': str(self.next_year.pk),
            'target_class_id': str(self.class_b2.pk),
            f'action_{student1.pk}': 'promote',
            f'action_{student2.pk}': 'repeat',
            f'repeat_target_{student2.pk}': str(class_b1b.pk),
            f'action_{student3.pk}': 'skip',
        })

        # Student1: moved to B2-A (target class)
        student1.refresh_from_db()
        self.assertEqual(student1.current_class, self.class_b2)

        # Source class unchanged
        self.class_b1.refresh_from_db()
        self.assertEqual(self.class_b1.name, 'B1-A')

        # Student2: moved to B1-B (repeated)
        student2.refresh_from_db()
        self.assertEqual(student2.current_class, class_b1b)

        # Student3: no new enrollment
        self.assertFalse(
            Enrollment.objects.filter(student=student3, academic_year=self.next_year).exists()
        )
