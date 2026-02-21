from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django_tenants.test.cases import TenantTestCase

from finance.models import (
    FeeStructure, Scholarship, StudentScholarship,
    Invoice, InvoiceItem, Payment,
)
from students.models import Student
from core.models import AcademicYear, Term

User = get_user_model()


class FinanceTestBase(TenantTestCase):
    """Base class with common setup for finance tests."""

    def setUp(self):
        self.ay = AcademicYear.objects.create(
            name='2024/2025',
            start_date=date(2024, 9, 1),
            end_date=date(2025, 7, 31),
            is_current=True,
        )
        self.term = Term.objects.create(
            academic_year=self.ay,
            name='First Term',
            term_number=1,
            start_date=date(2024, 9, 1),
            end_date=date(2024, 12, 20),
            is_current=True,
        )
        self.student = Student.objects.create(
            first_name='Kwame',
            last_name='Mensah',
            date_of_birth=date(2010, 5, 15),
            gender='M',
            admission_number='STU-2024-001',
            admission_date=date(2024, 9, 1),
        )
        self.admin = User.objects.create_school_admin(
            email='admin@school.com', password='pass123'
        )


class FeeStructureModelTests(FinanceTestBase):
    """Tests for the FeeStructure model."""

    def test_create_fee_structure(self):
        fee = FeeStructure.objects.create(
            category='TUITION',
            academic_year=self.ay,
            term=self.term,
            amount=Decimal('500.00'),
        )
        self.assertIn('Tuition', str(fee))
        self.assertIn('500', str(fee))

    def test_get_description_with_term(self):
        fee = FeeStructure.objects.create(
            category='TUITION',
            academic_year=self.ay,
            term=self.term,
            amount=Decimal('500.00'),
        )
        self.assertIn('First Term', fee.get_description())

    def test_get_description_full_year(self):
        fee = FeeStructure.objects.create(
            category='PTA',
            academic_year=self.ay,
            amount=Decimal('100.00'),
        )
        self.assertIn('Full Year', fee.get_description())

    def test_get_applies_to_all_classes(self):
        fee = FeeStructure.objects.create(
            category='TUITION',
            academic_year=self.ay,
            amount=Decimal('500.00'),
        )
        self.assertEqual(fee.get_applies_to_display(), 'All Classes')

    def test_get_applies_to_level_type(self):
        fee = FeeStructure.objects.create(
            category='BOARDING',
            academic_year=self.ay,
            level_type='shs',
            amount=Decimal('1000.00'),
        )
        self.assertEqual(fee.get_applies_to_display(), 'SHS')

    def test_boarding_and_day_defaults(self):
        fee = FeeStructure.objects.create(
            category='TUITION',
            academic_year=self.ay,
            amount=Decimal('500.00'),
        )
        self.assertTrue(fee.applies_to_boarding)
        self.assertTrue(fee.applies_to_day)


class ScholarshipModelTests(FinanceTestBase):
    """Tests for the Scholarship model."""

    def test_create_percentage_scholarship(self):
        s = Scholarship.objects.create(
            name='Merit Award',
            discount_type='PERCENTAGE',
            discount_value=Decimal('25.00'),
        )
        self.assertIn('25', str(s))
        self.assertIn('%', str(s))

    def test_create_fixed_scholarship(self):
        s = Scholarship.objects.create(
            name='Needs-based',
            discount_type='FIXED',
            discount_value=Decimal('200.00'),
        )
        self.assertIn('GHS', str(s))

    def test_create_full_scholarship(self):
        s = Scholarship.objects.create(
            name='Full Scholarship',
            discount_type='FULL',
        )
        self.assertIn('Full', str(s))

    def test_applies_to_category_all(self):
        s = Scholarship.objects.create(
            name='General',
            discount_type='FULL',
            applies_to_categories=[],
        )
        self.assertTrue(s.applies_to_category('TUITION'))
        self.assertTrue(s.applies_to_category('BOARDING'))

    def test_applies_to_category_specific(self):
        s = Scholarship.objects.create(
            name='Tuition Only',
            discount_type='PERCENTAGE',
            discount_value=Decimal('50.00'),
            applies_to_categories=['TUITION', 'EXAM'],
        )
        self.assertTrue(s.applies_to_category('TUITION'))
        self.assertTrue(s.applies_to_category('EXAM'))
        self.assertFalse(s.applies_to_category('BOARDING'))

    def test_get_applies_to_display_all(self):
        s = Scholarship.objects.create(
            name='All Fees',
            discount_type='FULL',
        )
        self.assertEqual(s.get_applies_to_display(), 'All Fees')

    def test_get_applies_to_display_specific(self):
        s = Scholarship.objects.create(
            name='Specific',
            discount_type='FIXED',
            discount_value=Decimal('100.00'),
            applies_to_categories=['TUITION'],
        )
        self.assertIn('Tuition', s.get_applies_to_display())


class StudentScholarshipModelTests(FinanceTestBase):
    """Tests for the StudentScholarship model."""

    def test_assign_scholarship(self):
        scholarship = Scholarship.objects.create(
            name='Merit',
            discount_type='PERCENTAGE',
            discount_value=Decimal('10.00'),
        )
        ss = StudentScholarship.objects.create(
            student=self.student,
            scholarship=scholarship,
            academic_year=self.ay,
            approved_by=self.admin,
        )
        self.assertIn('Kwame', str(ss))
        self.assertIn('Merit', str(ss))

    def test_unique_together(self):
        scholarship = Scholarship.objects.create(
            name='Award',
            discount_type='FULL',
        )
        StudentScholarship.objects.create(
            student=self.student,
            scholarship=scholarship,
            academic_year=self.ay,
        )
        with self.assertRaises(Exception):
            StudentScholarship.objects.create(
                student=self.student,
                scholarship=scholarship,
                academic_year=self.ay,
            )


class InvoiceModelTests(FinanceTestBase):
    """Tests for the Invoice model."""

    def _create_invoice(self, **kwargs):
        defaults = {
            'student': self.student,
            'academic_year': self.ay,
            'term': self.term,
            'due_date': date(2024, 10, 15),
            'total_amount': Decimal('1000.00'),
        }
        defaults.update(kwargs)
        return Invoice.objects.create(**defaults)

    def test_auto_generate_invoice_number(self):
        inv = self._create_invoice()
        self.assertTrue(inv.invoice_number.startswith('INV-'))
        self.assertIn('-00001', inv.invoice_number)

    def test_sequential_invoice_numbers(self):
        inv1 = self._create_invoice()
        inv2 = self._create_invoice()
        num1 = int(inv1.invoice_number.split('-')[-1])
        num2 = int(inv2.invoice_number.split('-')[-1])
        self.assertEqual(num2, num1 + 1)

    def test_balance_calculation(self):
        inv = self._create_invoice(
            total_amount=Decimal('1000.00'),
            amount_paid=Decimal('400.00'),
        )
        self.assertEqual(inv.balance, Decimal('600.00'))

    def test_status_paid(self):
        inv = self._create_invoice(
            total_amount=Decimal('1000.00'),
            amount_paid=Decimal('1000.00'),
            status='ISSUED',
        )
        self.assertEqual(inv.status, 'PAID')

    def test_status_partially_paid(self):
        inv = self._create_invoice(
            total_amount=Decimal('1000.00'),
            amount_paid=Decimal('500.00'),
            status='ISSUED',
        )
        self.assertEqual(inv.status, 'PARTIALLY_PAID')

    def test_status_cancelled_not_overridden(self):
        inv = self._create_invoice(
            total_amount=Decimal('1000.00'),
            amount_paid=Decimal('1000.00'),
            status='CANCELLED',
        )
        self.assertEqual(inv.status, 'CANCELLED')

    def test_str(self):
        inv = self._create_invoice()
        self.assertIn(inv.invoice_number, str(inv))
        self.assertIn('Kwame', str(inv))

    def test_update_totals(self):
        inv = self._create_invoice(total_amount=Decimal('0.00'))
        InvoiceItem.objects.create(
            invoice=inv,
            category='TUITION',
            description='Tuition Fee',
            amount=Decimal('500.00'),
        )
        InvoiceItem.objects.create(
            invoice=inv,
            category='PTA',
            description='PTA Dues',
            amount=Decimal('100.00'),
        )
        inv.update_totals()
        inv.refresh_from_db()
        self.assertEqual(inv.subtotal, Decimal('600.00'))
        self.assertEqual(inv.total_amount, Decimal('600.00'))


class InvoiceItemModelTests(FinanceTestBase):
    """Tests for the InvoiceItem model."""

    def test_create_item(self):
        inv = Invoice.objects.create(
            student=self.student,
            academic_year=self.ay,
            term=self.term,
            due_date=date(2024, 10, 15),
            total_amount=Decimal('500.00'),
        )
        item = InvoiceItem.objects.create(
            invoice=inv,
            category='TUITION',
            description='Tuition Fee - Term 1',
            amount=Decimal('500.00'),
        )
        self.assertIn('Tuition Fee', str(item))


class PaymentModelTests(FinanceTestBase):
    """Tests for the Payment model."""

    def setUp(self):
        super().setUp()
        self.invoice = Invoice.objects.create(
            student=self.student,
            academic_year=self.ay,
            term=self.term,
            due_date=date(2024, 10, 15),
            total_amount=Decimal('1000.00'),
            subtotal=Decimal('1000.00'),
            status='ISSUED',
        )
        # Add line item so update_totals() recalculates correctly
        InvoiceItem.objects.create(
            invoice=self.invoice,
            category='TUITION',
            description='Tuition Fee',
            amount=Decimal('1000.00'),
        )

    def test_auto_generate_receipt_number(self):
        payment = Payment.objects.create(
            invoice=self.invoice,
            amount=Decimal('500.00'),
            method='CASH',
            status='PENDING',
        )
        self.assertTrue(payment.receipt_number.startswith('RCP-'))

    def test_sequential_receipt_numbers(self):
        p1 = Payment.objects.create(
            invoice=self.invoice,
            amount=Decimal('200.00'),
            method='CASH',
            status='PENDING',
        )
        p2 = Payment.objects.create(
            invoice=self.invoice,
            amount=Decimal('300.00'),
            method='MOBILE_MONEY',
            status='PENDING',
        )
        num1 = int(p1.receipt_number.split('-')[-1])
        num2 = int(p2.receipt_number.split('-')[-1])
        self.assertEqual(num2, num1 + 1)

    def test_completed_payment_updates_invoice(self):
        Payment.objects.create(
            invoice=self.invoice,
            amount=Decimal('500.00'),
            method='CASH',
            status='COMPLETED',
        )
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.amount_paid, Decimal('500.00'))
        self.assertEqual(self.invoice.balance, Decimal('500.00'))
        self.assertEqual(self.invoice.status, 'PARTIALLY_PAID')

    def test_full_payment_marks_invoice_paid(self):
        Payment.objects.create(
            invoice=self.invoice,
            amount=Decimal('1000.00'),
            method='BANK_TRANSFER',
            status='COMPLETED',
        )
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, 'PAID')
        self.assertEqual(self.invoice.balance, Decimal('0.00'))

    def test_str(self):
        payment = Payment.objects.create(
            invoice=self.invoice,
            amount=Decimal('500.00'),
            method='CASH',
            status='PENDING',
        )
        self.assertIn(payment.receipt_number, str(payment))
