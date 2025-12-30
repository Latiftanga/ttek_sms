from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal
from encrypted_model_fields.fields import EncryptedCharField  # pip install django-encrypted-model-fields
from django.conf import settings
from django.utils import timezone
import uuid

class PaymentGateway(models.Model):
    """Available payment gateways in the system"""
    GATEWAY_CHOICES = [
        ('PAYSTACK', 'Paystack'),
        ('FLUTTERWAVE', 'Flutterwave'),
        ('HUBTEL', 'Hubtel'),
    ]
    
    name = models.CharField(max_length=50, choices=GATEWAY_CHOICES, unique=True)
    display_name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    supports_mobile_money = models.BooleanField(default=True)
    supports_cards = models.BooleanField(default=True)
    supports_bank_transfer = models.BooleanField(default=False)
    setup_instructions = models.TextField(blank=True, help_text="Instructions for schools to set up this gateway")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['display_name']
    
    def __str__(self):
        return self.display_name


class PaymentGatewayConfig(models.Model):
    """Store each school's payment gateway credentials (tenant-specific)"""
    gateway = models.ForeignKey(PaymentGateway, on_delete=models.CASCADE, related_name='tenant_configs')
    
    # Encrypted credentials - each school has their own
    secret_key = EncryptedCharField(max_length=500, help_text="Gateway secret/private key")
    public_key = EncryptedCharField(max_length=500, blank=True, help_text="Gateway public key")
    webhook_secret = EncryptedCharField(max_length=500, blank=True, help_text="Webhook verification secret")
    
    # Additional configuration fields
    merchant_id = EncryptedCharField(max_length=200, blank=True, help_text="Merchant/Client ID")
    encryption_key = EncryptedCharField(max_length=500, blank=True, help_text="Encryption key (for Flutterwave)")
    merchant_account = EncryptedCharField(max_length=200, blank=True, help_text="Merchant account (for Hubtel)")
    
    # Settings
    is_active = models.BooleanField(default=True)
    is_test_mode = models.BooleanField(default=True, help_text="Enable test/sandbox mode")
    is_primary = models.BooleanField(default=False, help_text="Primary gateway for this school")
    
    # Transaction settings
    transaction_charge_percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=Decimal('0.00'),
        help_text="Additional charge percentage to add to transactions"
    )
    transaction_charge_fixed = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=Decimal('0.00'),
        help_text="Fixed amount to add to transactions"
    )
    who_bears_charge = models.CharField(
        max_length=20,
        choices=[
            ('SCHOOL', 'School bears charges'),
            ('PARENT', 'Parent bears charges'),
        ],
        default='SCHOOL'
    )
    
    # Metadata
    configured_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='configured_gateways'
    )
    configured_at = models.DateTimeField(auto_now_add=True)
    last_verified = models.DateTimeField(null=True, blank=True)
    verification_status = models.CharField(
        max_length=20,
        choices=[
            ('PENDING', 'Pending Verification'),
            ('VERIFIED', 'Verified'),
            ('FAILED', 'Verification Failed'),
        ],
        default='PENDING'
    )
    verification_error = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['gateway']
        ordering = ['-is_primary', 'gateway__display_name']
    
    def __str__(self):
        return f"{self.gateway.display_name} - {'Active' if self.is_active else 'Inactive'}"
    
    def save(self, *args, **kwargs):
        # Ensure only one primary gateway
        if self.is_primary:
            PaymentGatewayConfig.objects.filter(is_primary=True).exclude(pk=self.pk).update(is_primary=False)
        super().save(*args, **kwargs)
    
    def get_credentials(self):
        """Return decrypted credentials as dict"""
        return {
            'secret_key': self.secret_key,
            'public_key': self.public_key,
            'webhook_secret': self.webhook_secret,
            'merchant_id': self.merchant_id,
            'encryption_key': self.encryption_key,
            'merchant_account': self.merchant_account,
            'is_test_mode': self.is_test_mode
        }


class FeeType(models.Model):
    """Types of fees (Tuition, Admission, Exam, etc.)"""
    # Ghana common fee categories
    CATEGORY_CHOICES = [
        ('TUITION', 'Tuition/School Fees'),
        ('ADMISSION', 'Admission Fees'),
        ('EXAM', 'Examination Fees'),
        ('PTA', 'PTA Dues'),
        ('SPORTS', 'Sports & Extra-curricular'),
        ('ICT', 'ICT/Computer Lab'),
        ('LIBRARY', 'Library Fees'),
        ('BOARDING', 'Boarding Fees'),
        ('FEEDING', 'Feeding Fees'),
        ('TRANSPORT', 'Transport/Bus Fees'),
        ('UNIFORM', 'Uniform & Materials'),
        ('CAUTION', 'Caution Deposit'),
        ('OTHER', 'Other Fees'),
    ]

    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='OTHER')
    description = models.TextField(blank=True)
    is_recurring = models.BooleanField(default=True, help_text="Charged every term")
    is_mandatory = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    # For SHS - some fees differ by programme
    applies_to_boarding = models.BooleanField(default=True, help_text="Applies to boarding students")
    applies_to_day = models.BooleanField(default=True, help_text="Applies to day students")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category', 'name']

    def __str__(self):
        return self.name


class FeeStructure(models.Model):
    """Fee amounts for different classes/terms"""
    LEVEL_TYPE_CHOICES = [
        ('', 'All Levels'),
        ('KG', 'Kindergarten'),
        ('PRIMARY', 'Primary (B1-B6)'),
        ('JHS', 'JHS (B7-B9)'),
        ('SHS', 'SHS'),
    ]

    fee_type = models.ForeignKey(FeeType, on_delete=models.CASCADE, related_name='structures')
    class_assigned = models.ForeignKey(
        'academics.Class',
        on_delete=models.CASCADE,
        related_name='fee_structures',
        null=True,
        blank=True,
        help_text="Leave blank to apply by level type"
    )
    level_type = models.CharField(
        max_length=10,
        choices=LEVEL_TYPE_CHOICES,
        blank=True,
        help_text="Apply to all classes of this level"
    )
    programme = models.ForeignKey(
        'academics.Programme',
        on_delete=models.CASCADE,
        related_name='fee_structures',
        null=True,
        blank=True,
        help_text="SHS programme (if applicable)"
    )
    academic_year = models.ForeignKey(
        'core.AcademicYear',
        on_delete=models.CASCADE,
        related_name='fee_structures'
    )
    term = models.ForeignKey(
        'core.Term',
        on_delete=models.CASCADE,
        related_name='fee_structures',
        null=True,
        blank=True,
        help_text="Leave blank for full year fee"
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    due_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['academic_year', 'term', 'fee_type']

    def __str__(self):
        if self.class_assigned:
            target = self.class_assigned.name
        elif self.level_type:
            target = self.get_level_type_display()
        else:
            target = "All Classes"
        return f"{self.fee_type.name} - {target} (GHS {self.amount})"


class Scholarship(models.Model):
    """Scholarships and fee discounts for students"""
    DISCOUNT_TYPE_CHOICES = [
        ('PERCENTAGE', 'Percentage'),
        ('FIXED', 'Fixed Amount'),
        ('FULL', 'Full Scholarship'),
    ]

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    discount_type = models.CharField(max_length=20, choices=DISCOUNT_TYPE_CHOICES)
    discount_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Percentage (0-100) or fixed amount in GHS"
    )
    # Which fees this applies to
    applies_to_fee_types = models.ManyToManyField(
        FeeType,
        blank=True,
        help_text="Leave blank to apply to all fees"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        if self.discount_type == 'PERCENTAGE':
            return f"{self.name} ({self.discount_value}%)"
        elif self.discount_type == 'FULL':
            return f"{self.name} (Full)"
        return f"{self.name} (GHS {self.discount_value})"


class StudentScholarship(models.Model):
    """Assign scholarships to specific students"""
    student = models.ForeignKey(
        'students.Student',
        on_delete=models.CASCADE,
        related_name='scholarships'
    )
    scholarship = models.ForeignKey(Scholarship, on_delete=models.CASCADE, related_name='recipients')
    academic_year = models.ForeignKey(
        'core.AcademicYear',
        on_delete=models.CASCADE,
        related_name='student_scholarships'
    )
    reason = models.TextField(blank=True, help_text="Reason for awarding scholarship")
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='approved_scholarships'
    )
    is_active = models.BooleanField(default=True)
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['student', 'scholarship', 'academic_year']
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.student.full_name} - {self.scholarship.name}"


class Invoice(models.Model):
    """Student fee invoices"""
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('ISSUED', 'Issued'),
        ('PARTIALLY_PAID', 'Partially Paid'),
        ('PAID', 'Paid'),
        ('OVERDUE', 'Overdue'),
        ('CANCELLED', 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice_number = models.CharField(max_length=50, unique=True)
    student = models.ForeignKey(
        'students.Student',
        on_delete=models.CASCADE,
        related_name='invoices'
    )
    academic_year = models.ForeignKey(
        'core.AcademicYear',
        on_delete=models.PROTECT,
        related_name='invoices'
    )
    term = models.ForeignKey(
        'core.Term',
        on_delete=models.PROTECT,
        related_name='invoices'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')

    # Amounts
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    # Dates
    issue_date = models.DateField(default=timezone.now)
    due_date = models.DateField()

    # Notes
    notes = models.TextField(blank=True)

    # Metadata
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_invoices'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.invoice_number} - {self.student.full_name}"

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            # Generate invoice number: INV-YYYY-XXXXX
            year = timezone.now().year
            last_invoice = Invoice.objects.filter(
                invoice_number__startswith=f'INV-{year}'
            ).order_by('-invoice_number').first()

            if last_invoice:
                last_num = int(last_invoice.invoice_number.split('-')[-1])
                new_num = last_num + 1
            else:
                new_num = 1

            self.invoice_number = f'INV-{year}-{new_num:05d}'

        # Calculate balance
        self.balance = self.total_amount - self.amount_paid

        # Update status based on payment
        if self.amount_paid >= self.total_amount:
            self.status = 'PAID'
        elif self.amount_paid > 0:
            self.status = 'PARTIALLY_PAID'
        elif self.status not in ['DRAFT', 'CANCELLED'] and self.due_date < timezone.now().date():
            self.status = 'OVERDUE'

        super().save(*args, **kwargs)

    def update_totals(self):
        """Recalculate totals from line items"""
        self.subtotal = sum(item.amount for item in self.items.all())
        self.total_amount = self.subtotal - self.discount
        self.amount_paid = sum(p.amount for p in self.payments.filter(status='COMPLETED'))
        self.save()


class InvoiceItem(models.Model):
    """Individual line items on an invoice"""
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='items')
    fee_type = models.ForeignKey(FeeType, on_delete=models.PROTECT)
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.description} - {self.amount}"


class Payment(models.Model):
    """Payment records"""
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
        ('REFUNDED', 'Refunded'),
        ('CANCELLED', 'Cancelled'),
    ]

    METHOD_CHOICES = [
        ('CASH', 'Cash'),
        ('BANK_TRANSFER', 'Bank Transfer'),
        ('MOBILE_MONEY', 'Mobile Money'),
        ('CARD', 'Card Payment'),
        ('CHEQUE', 'Cheque'),
        ('ONLINE', 'Online Payment'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    receipt_number = models.CharField(max_length=50, unique=True)
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name='payments')

    # Payment details
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    method = models.CharField(max_length=20, choices=METHOD_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')

    # Payer information
    payer_name = models.CharField(max_length=200, blank=True)
    payer_phone = models.CharField(max_length=20, blank=True)
    payer_email = models.EmailField(blank=True)

    # Transaction details
    reference = models.CharField(max_length=200, blank=True, help_text="Bank/Mobile money reference")
    transaction_date = models.DateTimeField(default=timezone.now)

    # Notes
    notes = models.TextField(blank=True)

    # Metadata
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='received_payments'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.receipt_number} - {self.amount}"

    def save(self, *args, **kwargs):
        if not self.receipt_number:
            # Generate receipt number: RCP-YYYY-XXXXX
            year = timezone.now().year
            last_payment = Payment.objects.filter(
                receipt_number__startswith=f'RCP-{year}'
            ).order_by('-receipt_number').first()

            if last_payment:
                last_num = int(last_payment.receipt_number.split('-')[-1])
                new_num = last_num + 1
            else:
                new_num = 1

            self.receipt_number = f'RCP-{year}-{new_num:05d}'

        super().save(*args, **kwargs)

        # Update invoice totals after payment
        if self.status == 'COMPLETED':
            self.invoice.update_totals()


class PaymentGatewayTransaction(models.Model):
    """Track all gateway-specific transaction details"""
    payment = models.OneToOneField(Payment, on_delete=models.CASCADE, related_name='gateway_transaction')
    gateway_config = models.ForeignKey(PaymentGatewayConfig, on_delete=models.PROTECT, related_name='transactions')

    # Gateway response details
    gateway_reference = models.CharField(max_length=200, blank=True)
    gateway_transaction_id = models.CharField(max_length=200, blank=True)
    authorization_code = models.CharField(max_length=200, blank=True)

    # Charges breakdown
    amount_charged = models.DecimalField(max_digits=10, decimal_places=2)
    gateway_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    platform_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    net_amount = models.DecimalField(max_digits=10, decimal_places=2)

    # Response data
    full_response = models.JSONField(blank=True, null=True)
    callback_data = models.JSONField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.gateway_config.gateway.name} - {self.payment.receipt_number}"