from functools import wraps
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.db.models import Sum, Count, Q, F
from django.db.models.functions import TruncDate
from django.contrib import messages
from django.core.paginator import Paginator

from .models import (
    PaymentGateway, PaymentGatewayConfig, FeeStructure, CATEGORY_CHOICES,
    Scholarship, StudentScholarship, Invoice, InvoiceItem, Payment
)
from .forms import (
    FeeStructureForm, ScholarshipForm, StudentScholarshipForm,
    InvoiceGenerateForm, PaymentForm, GatewayConfigForm
)
from students.models import Student
from academics.models import Class
from core.models import AcademicYear, Term


def is_school_admin(user):
    """Check if user is a school admin or superuser."""
    return user.is_superuser or getattr(user, 'is_school_admin', False)


def admin_required(view_func):
    """Decorator to require school admin or superuser access."""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('accounts:login')
        if not is_school_admin(request.user):
            messages.error(request, "You don't have permission to access this page.")
            return redirect('core:index')
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def htmx_render(request, full_template, partial_template, context=None):
    """Render full template for regular requests, partial for HTMX requests."""
    context = context or {}
    template = partial_template if request.htmx else full_template
    return render(request, template, context)


# =============================================================================
# DASHBOARD
# =============================================================================

@admin_required
def index(request):
    """Finance dashboard with summary statistics."""
    current_year = AcademicYear.get_current()
    current_term = Term.get_current() if hasattr(Term, 'get_current') else None

    # Calculate statistics
    total_invoiced = Invoice.objects.filter(
        academic_year=current_year
    ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')

    total_collected = Payment.objects.filter(
        invoice__academic_year=current_year,
        status='COMPLETED'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    total_outstanding = Invoice.objects.filter(
        academic_year=current_year,
        status__in=['ISSUED', 'PARTIALLY_PAID', 'OVERDUE']
    ).aggregate(total=Sum('balance'))['total'] or Decimal('0.00')

    # Recent payments
    recent_payments = Payment.objects.filter(
        status='COMPLETED'
    ).select_related('invoice__student').order_by('-created_at')[:10]

    # Overdue invoices
    overdue_invoices = Invoice.objects.filter(
        status='OVERDUE'
    ).select_related('student').order_by('due_date')[:10]

    # Collection by method
    collection_by_method = Payment.objects.filter(
        invoice__academic_year=current_year,
        status='COMPLETED'
    ).values('method').annotate(
        total=Sum('amount'),
        count=Count('id')
    ).order_by('-total')

    # Students with outstanding balance
    students_with_balance = Invoice.objects.filter(
        academic_year=current_year,
        balance__gt=0
    ).values('student').annotate(
        total_balance=Sum('balance')
    ).count()

    context = {
        'current_year': current_year,
        'current_term': current_term,
        'total_invoiced': total_invoiced,
        'total_collected': total_collected,
        'total_outstanding': total_outstanding,
        'collection_rate': (total_collected / total_invoiced * 100) if total_invoiced > 0 else 0,
        'recent_payments': recent_payments,
        'overdue_invoices': overdue_invoices,
        'collection_by_method': collection_by_method,
        'students_with_balance': students_with_balance,
    }

    return htmx_render(
        request,
        'finance/index.html',
        'finance/partials/index_content.html',
        context
    )


# =============================================================================
# FEE STRUCTURES
# =============================================================================

@admin_required
def fee_structures(request):
    """List fee structures with filtering."""
    current_year = AcademicYear.get_current()

    structures = FeeStructure.objects.select_related(
        'class_assigned', 'programme', 'academic_year', 'term'
    ).order_by('-academic_year__start_date', 'category')

    # Filters
    year_filter = request.GET.get('year')
    if year_filter:
        structures = structures.filter(academic_year_id=year_filter)
    else:
        structures = structures.filter(academic_year=current_year)

    category_filter = request.GET.get('category')
    if category_filter:
        structures = structures.filter(category=category_filter)

    # Stats
    total_count = structures.count()
    active_count = structures.filter(is_active=True).count()
    mandatory_count = structures.filter(is_mandatory=True).count()
    category_count = structures.values('category').distinct().count()

    context = {
        'structures': structures,
        'current_year': current_year,
        'academic_years': AcademicYear.objects.all().order_by('-start_date'),
        'categories': CATEGORY_CHOICES,
        'form': FeeStructureForm(),
        'total_count': total_count,
        'active_count': active_count,
        'mandatory_count': mandatory_count,
        'category_count': category_count,
    }

    return htmx_render(
        request,
        'finance/fee_structures.html',
        'finance/partials/fee_structures_content.html',
        context
    )


@admin_required
def fee_structure_create(request):
    """Create a new fee structure."""
    if request.method == 'POST':
        form = FeeStructureForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Fee structure created successfully.')
            # Return the refreshed list for HTMX
            if request.htmx:
                return redirect('finance:fee_structures')
            return redirect('finance:fee_structures')
    else:
        form = FeeStructureForm()

    # For modal, just return the partial
    if request.htmx:
        return render(request, 'finance/partials/fee_structure_form_content.html', {'form': form})

    return render(request, 'finance/fee_structure_form.html', {'form': form})


@admin_required
def fee_structure_edit(request, pk):
    """Edit a fee structure."""
    structure = get_object_or_404(FeeStructure, pk=pk)

    if request.method == 'POST':
        form = FeeStructureForm(request.POST, instance=structure)
        if form.is_valid():
            form.save()
            messages.success(request, 'Fee structure updated successfully.')
            return redirect('finance:fee_structures')
    else:
        form = FeeStructureForm(instance=structure)

    # For modal, just return the partial
    if request.htmx:
        return render(request, 'finance/partials/fee_structure_form_content.html', {'form': form, 'structure': structure})

    return render(request, 'finance/fee_structure_form.html', {'form': form, 'structure': structure})


@admin_required
def fee_structure_delete(request, pk):
    """Delete a fee structure."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    structure = get_object_or_404(FeeStructure, pk=pk)
    structure.delete()
    messages.success(request, 'Fee structure deleted successfully.')

    if request.htmx:
        # Return refreshed fee structures list
        current_year = AcademicYear.get_current()
        structures = FeeStructure.objects.select_related(
            'class_assigned', 'programme', 'academic_year', 'term'
        ).filter(academic_year=current_year).order_by('-academic_year__start_date', 'category')

        return render(request, 'finance/partials/fee_structures_content.html', {
            'structures': structures,
            'current_year': current_year,
            'academic_years': AcademicYear.objects.all().order_by('-start_date'),
            'categories': CATEGORY_CHOICES,
        })

    return redirect('finance:fee_structures')


# =============================================================================
# SCHOLARSHIPS
# =============================================================================

@admin_required
def scholarships(request):
    """List all scholarships."""
    scholarships_list = Scholarship.objects.annotate(
        recipient_count=Count('recipients', filter=Q(recipients__is_active=True))
    ).order_by('name')

    # Stats for the dashboard
    total_recipients = StudentScholarship.objects.filter(is_active=True).count()
    percentage_count = Scholarship.objects.filter(discount_type='PERCENTAGE', is_active=True).count()
    full_count = Scholarship.objects.filter(discount_type='FULL', is_active=True).count()

    context = {
        'scholarships': scholarships_list,
        'form': ScholarshipForm(),
        'total_recipients': total_recipients,
        'percentage_count': percentage_count,
        'full_count': full_count,
    }

    return htmx_render(
        request,
        'finance/scholarships.html',
        'finance/partials/scholarships_content.html',
        context
    )


@admin_required
def scholarship_create(request):
    """Create a new scholarship."""
    if request.method == 'POST':
        form = ScholarshipForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Scholarship created successfully.')
            return redirect('finance:scholarships')
    else:
        form = ScholarshipForm()

    # For modal, just return the partial
    if request.htmx:
        return render(request, 'finance/partials/scholarship_form_content.html', {'form': form})

    return render(request, 'finance/scholarship_form.html', {'form': form})


@admin_required
def scholarship_edit(request, pk):
    """Edit a scholarship."""
    scholarship = get_object_or_404(Scholarship, pk=pk)

    if request.method == 'POST':
        form = ScholarshipForm(request.POST, instance=scholarship)
        if form.is_valid():
            form.save()
            messages.success(request, 'Scholarship updated successfully.')
            return redirect('finance:scholarships')
    else:
        form = ScholarshipForm(instance=scholarship)

    # For modal, just return the partial
    if request.htmx:
        return render(request, 'finance/partials/scholarship_form_content.html', {'form': form, 'scholarship': scholarship})

    return render(request, 'finance/scholarship_form.html', {'form': form, 'scholarship': scholarship})


@admin_required
def scholarship_delete(request, pk):
    """Delete a scholarship."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    scholarship = get_object_or_404(Scholarship, pk=pk)

    # Check for active recipients
    active_recipients = scholarship.recipients.filter(is_active=True).count()
    if active_recipients > 0:
        messages.error(
            request,
            f'Cannot delete "{scholarship.name}": It has {active_recipients} active recipient(s). '
            'Remove or deactivate those assignments first.'
        )
    else:
        scholarship.delete()
        messages.success(request, f'Scholarship "{scholarship.name}" deleted successfully.')

    if request.htmx:
        # Return refreshed scholarships list
        scholarships_list = Scholarship.objects.annotate(
            recipient_count=Count('recipients', filter=Q(recipients__is_active=True))
        ).order_by('name')

        return render(request, 'finance/partials/scholarships_content.html', {
            'scholarships': scholarships_list,
        })

    return redirect('finance:scholarships')


@admin_required
def scholarship_assign(request, pk):
    """Assign scholarship to students."""
    scholarship = get_object_or_404(Scholarship, pk=pk)
    current_year = AcademicYear.get_current()

    if request.method == 'POST':
        form = StudentScholarshipForm(request.POST)
        if form.is_valid():
            student_scholarship = form.save(commit=False)
            student_scholarship.scholarship = scholarship
            student_scholarship.approved_by = request.user
            student_scholarship.save()
            messages.success(request, f'Scholarship assigned to {student_scholarship.student.full_name}.')
            return redirect('finance:scholarships')
    else:
        form = StudentScholarshipForm(initial={
            'scholarship': scholarship,
            'academic_year': current_year
        })

    # Get current recipients
    recipients = StudentScholarship.objects.filter(
        scholarship=scholarship,
        is_active=True
    ).select_related('student', 'academic_year')

    context = {
        'scholarship': scholarship,
        'form': form,
        'recipients': recipients,
        'students': Student.objects.filter(status='active').order_by('last_name', 'first_name'),
    }

    return htmx_render(
        request,
        'finance/scholarship_assign.html',
        'finance/partials/scholarship_assign_content.html',
        context
    )


# =============================================================================
# INVOICES
# =============================================================================

@admin_required
def invoices(request):
    """List all invoices with filtering."""
    current_year = AcademicYear.get_current()

    invoices_list = Invoice.objects.select_related(
        'student', 'academic_year', 'term'
    ).order_by('-created_at')

    # Filters
    status_filter = request.GET.get('status')
    if status_filter:
        invoices_list = invoices_list.filter(status=status_filter)

    class_filter = request.GET.get('class')
    if class_filter:
        invoices_list = invoices_list.filter(student__current_class_id=class_filter)

    search = request.GET.get('search', '').strip()
    if search:
        invoices_list = invoices_list.filter(
            Q(invoice_number__icontains=search) |
            Q(student__first_name__icontains=search) |
            Q(student__last_name__icontains=search) |
            Q(student__admission_number__icontains=search)
        )

    # Pagination
    paginator = Paginator(invoices_list, 25)
    page = request.GET.get('page', 1)
    invoices_page = paginator.get_page(page)

    # Stats for dashboard
    all_invoices = Invoice.objects.all()
    total_count = all_invoices.count()
    paid_count = all_invoices.filter(status='PAID').count()
    pending_count = all_invoices.filter(status__in=['ISSUED', 'PARTIALLY_PAID']).count()
    overdue_count = all_invoices.filter(status='OVERDUE').count()

    context = {
        'invoices': invoices_page,
        'current_year': current_year,
        'status_choices': Invoice.STATUS_CHOICES,
        'classes': Class.objects.filter(is_active=True),
        'status_filter': status_filter,
        'class_filter': class_filter,
        'search': search,
        'total_count': total_count,
        'paid_count': paid_count,
        'pending_count': pending_count,
        'overdue_count': overdue_count,
    }

    return htmx_render(
        request,
        'finance/invoices.html',
        'finance/partials/invoices_content.html',
        context
    )


@admin_required
def invoice_generate(request):
    """Generate invoices for students."""
    current_year = AcademicYear.get_current()
    current_term = Term.get_current() if hasattr(Term, 'get_current') else None

    if request.method == 'POST':
        form = InvoiceGenerateForm(request.POST)
        if form.is_valid():
            class_obj = form.cleaned_data.get('class_assigned')
            student = form.cleaned_data.get('student')
            term = form.cleaned_data['term']
            due_date = form.cleaned_data['due_date']

            # Get students to invoice
            if student:
                students = [student]
            elif class_obj:
                students = Student.objects.filter(
                    current_class=class_obj,
                    status='active'
                )
            else:
                messages.error(request, 'Please select a class or student.')
                return redirect('finance:invoice_generate')

            invoices_created = 0
            for student in students:
                invoice = create_student_invoice(
                    student=student,
                    academic_year=current_year,
                    term=term,
                    due_date=due_date,
                    created_by=request.user
                )
                if invoice:
                    invoices_created += 1

            messages.success(request, f'{invoices_created} invoice(s) generated successfully.')
            return redirect('finance:invoices')
    else:
        form = InvoiceGenerateForm(initial={
            'academic_year': current_year,
            'term': current_term
        })

    # For modal, just return the partial
    if request.htmx:
        return render(request, 'finance/partials/invoice_generate_content.html', {'form': form})

    return render(request, 'finance/invoice_generate.html', {'form': form})


def create_student_invoice(student, academic_year, term, due_date, created_by):
    """Create an invoice for a student based on applicable fee structures."""
    # Check if invoice already exists
    existing = Invoice.objects.filter(
        student=student,
        academic_year=academic_year,
        term=term
    ).first()

    if existing:
        return None

    # Get applicable fee structures
    fee_structures = FeeStructure.objects.filter(
        academic_year=academic_year,
        is_active=True
    ).filter(
        Q(term=term) | Q(term__isnull=True)
    )

    # Filter by class or level
    applicable_structures = []
    for structure in fee_structures:
        if structure.class_assigned:
            if structure.class_assigned == student.current_class:
                applicable_structures.append(structure)
        elif structure.level_type:
            if student.current_class and student.current_class.level_type == structure.level_type:
                applicable_structures.append(structure)
        else:
            applicable_structures.append(structure)

    if not applicable_structures:
        return None

    # Create invoice
    invoice = Invoice.objects.create(
        student=student,
        academic_year=academic_year,
        term=term,
        due_date=due_date,
        created_by=created_by,
        status='DRAFT'
    )

    # Add line items
    subtotal = Decimal('0.00')
    for structure in applicable_structures:
        # Check if fee applies to student type (boarding/day)
        if hasattr(student, 'is_boarding'):
            if student.is_boarding and not structure.applies_to_boarding:
                continue
            if not student.is_boarding and not structure.applies_to_day:
                continue

        InvoiceItem.objects.create(
            invoice=invoice,
            category=structure.category,
            description=structure.get_description(),
            amount=structure.amount
        )
        subtotal += structure.amount

    # Apply scholarships
    discount = Decimal('0.00')
    student_scholarships = StudentScholarship.objects.filter(
        student=student,
        academic_year=academic_year,
        is_active=True
    ).select_related('scholarship')

    for ss in student_scholarships:
        scholarship = ss.scholarship
        if scholarship.discount_type == 'FULL':
            discount = subtotal
            break
        elif scholarship.discount_type == 'PERCENTAGE':
            discount += subtotal * (scholarship.discount_value / 100)
        elif scholarship.discount_type == 'FIXED':
            discount += scholarship.discount_value

    # Update invoice totals
    invoice.subtotal = subtotal
    invoice.discount = min(discount, subtotal)  # Can't discount more than subtotal
    invoice.total_amount = subtotal - invoice.discount
    invoice.balance = invoice.total_amount
    invoice.save()

    return invoice


@admin_required
def invoice_detail(request, pk):
    """View invoice details."""
    invoice = get_object_or_404(
        Invoice.objects.select_related('student', 'academic_year', 'term', 'created_by'),
        pk=pk
    )

    items = invoice.items.all()
    payments = invoice.payments.all().order_by('-created_at')

    # Check if online payment gateway is available
    gateway_available = PaymentGatewayConfig.objects.filter(
        is_active=True,
        is_primary=True,
        verification_status='VERIFIED'
    ).exists()

    # Get last notification
    last_notification = invoice.notification_logs.first()

    context = {
        'invoice': invoice,
        'items': items,
        'payments': payments,
        'gateway_available': gateway_available,
        'last_notification': last_notification,
    }

    return htmx_render(
        request,
        'finance/invoice_detail.html',
        'finance/partials/invoice_detail_content.html',
        context
    )


@admin_required
def invoice_edit(request, pk):
    """Edit invoice (only draft invoices) - handles issue action."""
    if request.method != 'POST':
        return redirect('finance:invoice_detail', pk=pk)

    invoice = get_object_or_404(Invoice, pk=pk)

    if invoice.status != 'DRAFT':
        messages.error(request, 'Only draft invoices can be edited.')
        return redirect('finance:invoice_detail', pk=pk)

    action = request.POST.get('action')
    if action == 'issue':
        invoice.status = 'ISSUED'
        invoice.issue_date = timezone.now().date()
        invoice.save()
        messages.success(request, 'Invoice issued successfully.')

    return redirect('finance:invoice_detail', pk=pk)


@admin_required
def invoice_cancel(request, pk):
    """Cancel an invoice."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    invoice = get_object_or_404(Invoice, pk=pk)

    if invoice.status == 'PAID':
        messages.error(request, 'Cannot cancel a paid invoice.')
        return redirect('finance:invoice_detail', pk=pk)

    invoice.status = 'CANCELLED'
    invoice.save()
    messages.success(request, 'Invoice cancelled successfully.')

    if request.htmx:
        # Return to invoices list
        return redirect('finance:invoices')

    return redirect('finance:invoices')


@admin_required
def invoice_print(request, pk):
    """Print-friendly invoice view."""
    invoice = get_object_or_404(
        Invoice.objects.select_related('student', 'academic_year', 'term'),
        pk=pk
    )

    context = {
        'invoice': invoice,
        'items': invoice.items.all(),
    }

    return render(request, 'finance/invoice_print.html', context)


# =============================================================================
# PAYMENTS
# =============================================================================

@admin_required
def payments(request):
    """List all payments with filtering."""
    payments_list = Payment.objects.select_related(
        'invoice__student', 'received_by'
    ).order_by('-created_at')

    # Filters
    status_filter = request.GET.get('status')
    if status_filter:
        payments_list = payments_list.filter(status=status_filter)

    method_filter = request.GET.get('method')
    if method_filter:
        payments_list = payments_list.filter(method=method_filter)

    search = request.GET.get('search', '').strip()
    if search:
        payments_list = payments_list.filter(
            Q(receipt_number__icontains=search) |
            Q(invoice__invoice_number__icontains=search) |
            Q(invoice__student__first_name__icontains=search) |
            Q(invoice__student__last_name__icontains=search)
        )

    # Date range
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if date_from:
        payments_list = payments_list.filter(transaction_date__date__gte=date_from)
    if date_to:
        payments_list = payments_list.filter(transaction_date__date__lte=date_to)

    # Pagination
    paginator = Paginator(payments_list, 25)
    page = request.GET.get('page', 1)
    payments_page = paginator.get_page(page)

    # Stats for dashboard
    all_payments = Payment.objects.filter(status='COMPLETED')
    total_count = all_payments.count()
    total_amount = all_payments.aggregate(total=Sum('amount'))['total'] or 0
    momo_count = all_payments.filter(method='MOBILE_MONEY').count()
    cash_count = all_payments.filter(method='CASH').count()

    context = {
        'payments': payments_page,
        'status_choices': Payment.STATUS_CHOICES,
        'method_choices': Payment.METHOD_CHOICES,
        'status_filter': status_filter,
        'method_filter': method_filter,
        'search': search,
        'total_count': total_count,
        'total_amount': total_amount,
        'momo_count': momo_count,
        'cash_count': cash_count,
    }

    return htmx_render(
        request,
        'finance/payments.html',
        'finance/partials/payments_content.html',
        context
    )


@admin_required
def payment_record(request):
    """Record a manual payment."""
    if request.method == 'POST':
        form = PaymentForm(request.POST)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.received_by = request.user
            payment.status = 'COMPLETED'
            payment.save()
            messages.success(request, f'Payment recorded successfully. Receipt: {payment.receipt_number}')
            return redirect('finance:payments')
    else:
        form = PaymentForm()

    # For modal, just return the partial
    if request.htmx:
        return render(request, 'finance/partials/payment_record_content.html', {'form': form})

    return render(request, 'finance/payment_record.html', {'form': form})


@admin_required
def payment_detail(request, pk):
    """View payment details."""
    payment = get_object_or_404(
        Payment.objects.select_related(
            'invoice__student', 'invoice__academic_year', 'invoice__term', 'received_by'
        ),
        pk=pk
    )

    context = {
        'payment': payment,
    }

    return htmx_render(
        request,
        'finance/payment_detail.html',
        'finance/partials/payment_detail_content.html',
        context
    )


@admin_required
def payment_receipt(request, pk):
    """Print-friendly payment receipt."""
    payment = get_object_or_404(
        Payment.objects.select_related('invoice__student', 'received_by'),
        pk=pk
    )

    context = {
        'payment': payment,
    }

    return render(request, 'finance/payment_receipt.html', context)


# =============================================================================
# STUDENT FEES
# =============================================================================

@admin_required
def student_fees(request, student_id):
    """View a student's fee summary."""
    student = get_object_or_404(Student, pk=student_id)
    current_year = AcademicYear.get_current()

    invoices = Invoice.objects.filter(
        student=student
    ).select_related('academic_year', 'term').order_by('-created_at')

    payments = Payment.objects.filter(
        invoice__student=student,
        status='COMPLETED'
    ).select_related('invoice').order_by('-created_at')

    # Calculate totals
    total_invoiced = invoices.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
    total_paid = payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    total_balance = invoices.filter(
        status__in=['ISSUED', 'PARTIALLY_PAID', 'OVERDUE']
    ).aggregate(total=Sum('balance'))['total'] or Decimal('0.00')

    # Get scholarships
    scholarships = StudentScholarship.objects.filter(
        student=student,
        is_active=True
    ).select_related('scholarship', 'academic_year')

    context = {
        'student': student,
        'invoices': invoices,
        'payments': payments,
        'total_invoiced': total_invoiced,
        'total_paid': total_paid,
        'total_balance': total_balance,
        'scholarships': scholarships,
    }

    return htmx_render(
        request,
        'finance/student_fees.html',
        'finance/partials/student_fees_content.html',
        context
    )


@admin_required
def student_statement(request, student_id):
    """Generate a fee statement for a student."""
    student = get_object_or_404(Student, pk=student_id)

    invoices = Invoice.objects.filter(
        student=student
    ).select_related('academic_year', 'term').order_by('created_at')

    payments = Payment.objects.filter(
        invoice__student=student,
        status='COMPLETED'
    ).select_related('invoice').order_by('transaction_date')

    # Build statement entries
    entries = []
    balance = Decimal('0.00')

    for invoice in invoices:
        balance += invoice.total_amount
        entries.append({
            'date': invoice.issue_date,
            'description': f'Invoice {invoice.invoice_number}',
            'type': 'invoice',
            'debit': invoice.total_amount,
            'credit': None,
            'balance': balance,
        })

    for payment in payments:
        balance -= payment.amount
        entries.append({
            'date': payment.transaction_date.date(),
            'description': f'Payment {payment.receipt_number}',
            'type': 'payment',
            'debit': None,
            'credit': payment.amount,
            'balance': balance,
        })

    # Sort by date
    entries.sort(key=lambda x: x['date'])

    context = {
        'student': student,
        'entries': entries,
        'final_balance': balance,
    }

    return render(request, 'finance/student_statement.html', context)


# =============================================================================
# REPORTS
# =============================================================================

@admin_required
def reports(request):
    """Finance reports dashboard."""
    context = {}
    return htmx_render(
        request,
        'finance/reports.html',
        'finance/partials/reports_content.html',
        context
    )


@admin_required
def collection_report(request):
    """Fee collection report."""
    current_year = AcademicYear.get_current()

    # Get date range
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')

    payments = Payment.objects.filter(status='COMPLETED')

    if date_from:
        payments = payments.filter(transaction_date__date__gte=date_from)
    if date_to:
        payments = payments.filter(transaction_date__date__lte=date_to)

    # Summary by method
    by_method = payments.values('method').annotate(
        total=Sum('amount'),
        count=Count('id')
    ).order_by('-total')

    # Summary by day (using TruncDate for database-agnostic date grouping)
    by_day = payments.annotate(
        date=TruncDate('transaction_date')
    ).values('date').annotate(
        total=Sum('amount'),
        count=Count('id')
    ).order_by('-date')[:30]

    # Summary by class
    by_class = payments.values(
        'invoice__student__current_class__name'
    ).annotate(
        total=Sum('amount'),
        count=Count('id')
    ).order_by('-total')

    total_collected = payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    context = {
        'by_method': by_method,
        'by_day': by_day,
        'by_class': by_class,
        'total_collected': total_collected,
        'date_from': date_from,
        'date_to': date_to,
    }

    return htmx_render(
        request,
        'finance/collection_report.html',
        'finance/partials/collection_report_content.html',
        context
    )


@admin_required
def outstanding_report(request):
    """Outstanding fees report."""
    current_year = AcademicYear.get_current()

    # Get students with outstanding balance
    students_with_balance = Invoice.objects.filter(
        academic_year=current_year,
        balance__gt=0
    ).values(
        'student__id',
        'student__first_name',
        'student__last_name',
        'student__admission_number',
        'student__current_class__name'
    ).annotate(
        total_invoiced=Sum('total_amount'),
        total_paid=Sum('amount_paid'),
        total_balance=Sum('balance')
    ).order_by('-total_balance')

    # Summary by class
    by_class = Invoice.objects.filter(
        academic_year=current_year,
        balance__gt=0
    ).values('student__current_class__name').annotate(
        student_count=Count('student', distinct=True),
        total_balance=Sum('balance')
    ).order_by('-total_balance')

    total_outstanding = Invoice.objects.filter(
        academic_year=current_year,
        balance__gt=0
    ).aggregate(total=Sum('balance'))['total'] or Decimal('0.00')

    context = {
        'students_with_balance': students_with_balance,
        'by_class': by_class,
        'total_outstanding': total_outstanding,
        'current_year': current_year,
    }

    return htmx_render(
        request,
        'finance/outstanding_report.html',
        'finance/partials/outstanding_report_content.html',
        context
    )


@admin_required
def export_report(request):
    """Export report data to CSV/Excel."""
    import csv
    from django.http import HttpResponse

    report_type = request.GET.get('type', 'collection')
    format_type = request.GET.get('format', 'csv')

    if report_type == 'collection':
        payments = Payment.objects.filter(
            status='COMPLETED'
        ).select_related('invoice__student').order_by('-transaction_date')

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="collection_report.csv"'

        writer = csv.writer(response)
        writer.writerow(['Receipt', 'Date', 'Student', 'Invoice', 'Amount', 'Method'])

        for payment in payments:
            writer.writerow([
                payment.receipt_number,
                payment.transaction_date.strftime('%Y-%m-%d'),
                payment.invoice.student.full_name,
                payment.invoice.invoice_number,
                payment.amount,
                payment.get_method_display()
            ])

        return response

    elif report_type == 'outstanding':
        invoices = Invoice.objects.filter(
            balance__gt=0
        ).select_related('student', 'student__current_class').order_by('student__last_name')

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="outstanding_report.csv"'

        writer = csv.writer(response)
        writer.writerow(['Student', 'Admission No', 'Class', 'Invoice', 'Total', 'Paid', 'Balance'])

        for invoice in invoices:
            writer.writerow([
                invoice.student.full_name,
                invoice.student.admission_number,
                invoice.student.current_class.name if invoice.student.current_class else '-',
                invoice.invoice_number,
                invoice.total_amount,
                invoice.amount_paid,
                invoice.balance
            ])

        return response

    return redirect('finance:reports')


# =============================================================================
# PAYMENT GATEWAY SETTINGS
# =============================================================================

@admin_required
def gateway_settings(request):
    """Payment gateway configuration page."""
    gateways = PaymentGateway.objects.all()
    configs = PaymentGatewayConfig.objects.select_related('gateway').all()

    context = {
        'gateways': gateways,
        'configs': configs,
    }

    return htmx_render(
        request,
        'finance/gateway_settings.html',
        'finance/partials/gateway_settings_content.html',
        context
    )


@admin_required
def gateway_configure(request, pk):
    """Configure a payment gateway."""
    gateway = get_object_or_404(PaymentGateway, pk=pk)

    # Get or create config for this gateway
    config, created = PaymentGatewayConfig.objects.get_or_create(
        gateway=gateway,
        defaults={'configured_by': request.user}
    )

    if request.method == 'POST':
        form = GatewayConfigForm(request.POST, instance=config)
        if form.is_valid():
            config = form.save(commit=False)
            config.configured_by = request.user
            config.configured_at = timezone.now()
            config.verification_status = 'PENDING'
            config.save()
            messages.success(request, f'{gateway.display_name} configuration saved.')
            return redirect('finance:gateway_settings')
    else:
        form = GatewayConfigForm(instance=config)

    context = {
        'gateway': gateway,
        'config': config,
        'form': form,
    }

    return htmx_render(
        request,
        'finance/gateway_configure.html',
        'finance/partials/gateway_configure_content.html',
        context
    )


@admin_required
def gateway_verify(request, pk):
    """Verify gateway credentials."""
    config = get_object_or_404(PaymentGatewayConfig, pk=pk)

    # Import gateway adapter
    from .gateways import get_gateway_adapter

    try:
        adapter = get_gateway_adapter(config)
        is_valid, message = adapter.verify_credentials()

        if is_valid:
            config.verification_status = 'VERIFIED'
            config.verification_error = ''
            config.last_verified = timezone.now()
            messages.success(request, f'{config.gateway.display_name} credentials verified successfully.')
        else:
            config.verification_status = 'FAILED'
            config.verification_error = message
            messages.error(request, f'Verification failed: {message}')

        config.save()

    except Exception as e:
        config.verification_status = 'FAILED'
        config.verification_error = str(e)
        config.save()
        messages.error(request, f'Verification error: {str(e)}')

    return redirect('finance:gateway_settings')


# =============================================================================
# API ENDPOINTS
# =============================================================================

@admin_required
def student_search(request):
    """Search students for HTMX autocomplete."""
    q = request.GET.get('q', '').strip()

    if len(q) < 2:
        return HttpResponse('')

    students = Student.objects.filter(
        status='active'
    ).filter(
        Q(first_name__icontains=q) |
        Q(last_name__icontains=q) |
        Q(admission_number__icontains=q)
    ).select_related('current_class')[:10]

    if not students:
        return HttpResponse('<div class="p-2 text-sm text-base-content/60">No students found</div>')

    html = '<ul class="menu bg-base-100 shadow-lg rounded-box absolute z-50 w-full mt-1 max-h-48 overflow-y-auto">'
    for student in students:
        class_name = student.current_class.name if student.current_class else 'No class'
        html += f'''<li><a onclick="selectStudent('{student.pk}', '{student.full_name}')" class="text-sm">
            <span class="font-medium">{student.full_name}</span>
            <span class="text-xs text-base-content/60">{student.admission_number} • {class_name}</span>
        </a></li>'''
    html += '</ul>'

    return HttpResponse(html)


@admin_required
def invoice_search(request):
    """Search invoices for HTMX autocomplete."""
    q = request.GET.get('q', '').strip()

    if len(q) < 2:
        return HttpResponse('')

    invoices = Invoice.objects.filter(
        status__in=['ISSUED', 'PARTIALLY_PAID', 'OVERDUE']
    ).filter(
        Q(invoice_number__icontains=q) |
        Q(student__first_name__icontains=q) |
        Q(student__last_name__icontains=q) |
        Q(student__admission_number__icontains=q)
    ).select_related('student')[:10]

    if not invoices:
        return HttpResponse('<div class="p-2 text-sm text-base-content/60">No pending invoices found</div>')

    html = '<ul class="menu bg-base-100 shadow-lg rounded-box absolute z-50 w-full mt-1 max-h-48 overflow-y-auto">'
    for invoice in invoices:
        balance = f"{invoice.balance:.2f}"
        html += f'''<li><a onclick="selectInvoice('{invoice.pk}', '{invoice.invoice_number}', '{invoice.student.full_name}', '{balance}')" class="text-sm py-2">
            <div class="flex flex-col">
                <span class="font-medium">{invoice.invoice_number}</span>
                <span class="text-xs text-base-content/60">{invoice.student.full_name} • Balance: GHS {balance}</span>
            </div>
        </a></li>'''
    html += '</ul>'

    return HttpResponse(html)


@login_required
def api_student_balance(request, student_id):
    """Get student's current balance."""
    student = get_object_or_404(Student, pk=student_id)

    balance = Invoice.objects.filter(
        student=student,
        status__in=['ISSUED', 'PARTIALLY_PAID', 'OVERDUE']
    ).aggregate(total=Sum('balance'))['total'] or Decimal('0.00')

    return JsonResponse({
        'student_id': str(student_id),
        'student_name': student.full_name,
        'balance': float(balance)
    })


@login_required
def api_class_fees(request, class_id):
    """Get fee structures for a class."""
    class_obj = get_object_or_404(Class, pk=class_id)
    current_year = AcademicYear.get_current()

    structures = FeeStructure.objects.filter(
        academic_year=current_year,
        is_active=True
    ).filter(
        Q(class_assigned=class_obj) |
        Q(level_type=class_obj.level_type) |
        Q(class_assigned__isnull=True, level_type='')
    )

    fees = []
    for structure in structures:
        fees.append({
            'category': structure.get_category_display(),
            'description': structure.get_description(),
            'amount': float(structure.amount),
            'is_mandatory': structure.is_mandatory,
        })

    return JsonResponse({
        'class_id': class_id,
        'class_name': class_obj.name,
        'fees': fees,
        'total': sum(f['amount'] for f in fees)
    })


# =============================================================================
# ONLINE PAYMENT
# =============================================================================

def pay_online(request, invoice_pk):
    """
    Initiate an online payment for an invoice.
    Redirects user to the payment gateway.
    """
    invoice = get_object_or_404(
        Invoice.objects.select_related('student'),
        pk=invoice_pk
    )

    # Check invoice can be paid
    if invoice.status in ['PAID', 'CANCELLED']:
        messages.error(request, 'This invoice cannot be paid.')
        return redirect('finance:invoice_detail', pk=invoice_pk)

    if invoice.balance <= 0:
        messages.error(request, 'This invoice has no outstanding balance.')
        return redirect('finance:invoice_detail', pk=invoice_pk)

    # Get primary gateway config
    from .models import PaymentGatewayConfig
    gateway_config = PaymentGatewayConfig.objects.filter(
        is_active=True,
        is_primary=True
    ).select_related('gateway').first()

    if not gateway_config:
        messages.error(request, 'No payment gateway is configured. Please contact the school.')
        return redirect('finance:invoice_detail', pk=invoice_pk)

    if gateway_config.verification_status != 'VERIFIED':
        messages.error(request, 'Payment gateway is not verified. Please contact the school.')
        return redirect('finance:invoice_detail', pk=invoice_pk)

    # Get gateway adapter
    from .gateways import get_gateway_adapter
    adapter = get_gateway_adapter(gateway_config)

    # Generate unique reference
    import uuid
    reference = f"PAY-{invoice.invoice_number}-{uuid.uuid4().hex[:8].upper()}"

    # Get payer email (student's guardian email or use a default)
    payer_email = getattr(invoice.student, 'guardian_email', '') or \
                  getattr(invoice.student, 'email', '') or \
                  'noreply@school.com'

    # Build callback URL
    callback_url = request.build_absolute_uri(
        reverse('finance:payment_callback')
    ) + f'?reference={reference}'

    # Metadata for tracking
    metadata = {
        'invoice_id': str(invoice.pk),
        'invoice_number': invoice.invoice_number,
        'student_id': str(invoice.student.pk),
        'student_name': invoice.student.full_name,
    }

    # Initialize payment
    response = adapter.initialize_payment(
        amount=invoice.balance,
        email=payer_email,
        reference=reference,
        callback_url=callback_url,
        metadata=metadata
    )

    if response.success:
        # Create pending payment record
        from .models import Payment, PaymentGatewayTransaction
        payment = Payment.objects.create(
            invoice=invoice,
            amount=invoice.balance,
            method='ONLINE',
            status='PENDING',
            reference=reference,
            payer_email=payer_email,
        )

        # Create gateway transaction record
        PaymentGatewayTransaction.objects.create(
            payment=payment,
            gateway_config=gateway_config,
            gateway_reference=reference,
            amount_charged=response.amount,
            net_amount=invoice.balance,
            full_response=response.raw_response,
        )

        # Redirect to gateway
        return redirect(response.authorization_url)
    else:
        messages.error(request, f'Payment initialization failed: {response.message}')
        return redirect('finance:invoice_detail', pk=invoice_pk)


def payment_callback(request):
    """
    Handle return from payment gateway.
    Verifies the payment and updates records.
    """
    reference = request.GET.get('reference', '')

    if not reference:
        messages.error(request, 'Invalid payment callback.')
        return redirect('finance:payments')

    # Find the payment
    from .models import Payment, PaymentGatewayTransaction
    try:
        payment = Payment.objects.select_related(
            'invoice__student'
        ).get(reference=reference)
    except Payment.DoesNotExist:
        messages.error(request, 'Payment not found.')
        return redirect('finance:payments')

    # If already processed, show result
    if payment.status == 'COMPLETED':
        messages.success(request, 'Payment was successful!')
        return redirect('finance:payment_detail', pk=payment.pk)
    elif payment.status in ['FAILED', 'CANCELLED']:
        messages.error(request, 'Payment was not successful.')
        return redirect('finance:invoice_detail', pk=payment.invoice.pk)

    # Get gateway transaction
    try:
        gateway_tx = payment.gateway_transaction
        gateway_config = gateway_tx.gateway_config
    except PaymentGatewayTransaction.DoesNotExist:
        messages.error(request, 'Payment configuration error.')
        return redirect('finance:invoice_detail', pk=payment.invoice.pk)

    # Verify with gateway
    from .gateways import get_gateway_adapter
    adapter = get_gateway_adapter(gateway_config)
    response = adapter.verify_payment(reference)

    if response.success:
        # Update payment
        payment.status = 'COMPLETED'
        payment.transaction_date = timezone.now()
        payment.save()

        # Update gateway transaction
        gateway_tx.gateway_transaction_id = response.transaction_id
        gateway_tx.gateway_fee = response.gateway_fee
        gateway_tx.net_amount = response.amount - response.gateway_fee
        gateway_tx.full_response = response.raw_response
        gateway_tx.save()

        # Invoice totals are updated automatically via Payment.save()
        messages.success(request, f'Payment successful! Receipt: {payment.receipt_number}')
        return redirect('finance:payment_detail', pk=payment.pk)
    else:
        payment.status = 'FAILED'
        payment.save()

        gateway_tx.full_response = response.raw_response
        gateway_tx.save()

        messages.error(request, f'Payment verification failed: {response.message}')
        return redirect('finance:invoice_detail', pk=payment.invoice.pk)


from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
import json


@csrf_exempt
@require_POST
def payment_webhook(request):
    """
    Handle webhook notifications from payment gateway.
    This is called server-to-server by the gateway.

    SECURITY: Signature verification happens in the gateway adapter.
    We reject webhooks with invalid signatures before any database changes.
    """
    import logging
    logger = logging.getLogger(__name__)

    # Get signature from headers
    signature = request.headers.get('X-Paystack-Signature', '') or \
                request.headers.get('X-Flutterwave-Signature', '') or \
                request.headers.get('X-Hubtel-Signature', '')

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        logger.warning("Payment webhook received invalid JSON")
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)

    # Determine which gateway this is from and get reference
    reference = None
    if 'data' in payload and 'reference' in payload.get('data', {}):
        reference = payload['data']['reference']
    elif 'Data' in payload and 'ClientReference' in payload.get('Data', {}):
        reference = payload['Data']['ClientReference']  # Hubtel format

    if not reference:
        logger.warning("Payment webhook received without reference")
        return JsonResponse({'status': 'error', 'message': 'No reference found'}, status=400)

    # Find the payment
    from .models import Payment, PaymentGatewayTransaction
    try:
        payment = Payment.objects.get(reference=reference)
        gateway_tx = payment.gateway_transaction
        gateway_config = gateway_tx.gateway_config
    except (Payment.DoesNotExist, PaymentGatewayTransaction.DoesNotExist):
        # Don't reveal whether payment exists - use generic message
        logger.warning(f"Payment webhook for unknown reference: {reference[:20]}...")
        return JsonResponse({'status': 'error', 'message': 'Invalid request'}, status=400)

    # Skip if already processed
    if payment.status == 'COMPLETED':
        return JsonResponse({'status': 'success', 'message': 'Already processed'})

    # Verify signature and process with gateway adapter
    # SECURITY: The adapter verifies the signature using HMAC
    # If signature is invalid, response.success will be False
    from .gateways import get_gateway_adapter
    adapter = get_gateway_adapter(gateway_config)
    response = adapter.handle_webhook(payload, signature)

    # SECURITY: Check for signature verification failure
    # The adapter returns success=False with "signature" in message for invalid signatures
    if not response.success and 'signature' in response.message.lower():
        logger.warning(f"Payment webhook signature verification failed for {reference[:20]}...")
        return JsonResponse({'status': 'error', 'message': 'Signature verification failed'}, status=403)

    # Signature verified - now store webhook data
    gateway_tx.callback_data = payload
    gateway_tx.save()

    if response.success:
        # Payment successful
        payment.status = 'COMPLETED'
        payment.transaction_date = timezone.now()
        payment.save()

        gateway_tx.gateway_transaction_id = response.transaction_id
        gateway_tx.gateway_fee = response.gateway_fee
        gateway_tx.net_amount = response.amount - response.gateway_fee
        gateway_tx.save()

        logger.info(f"Payment {reference[:20]}... confirmed via webhook")
        return JsonResponse({'status': 'success', 'message': 'Payment confirmed'})
    else:
        # Payment failed (but webhook signature was valid)
        payment.status = 'FAILED'
        payment.save()

        logger.info(f"Payment {reference[:20]}... failed: {response.message}")
        return JsonResponse({'status': 'success', 'message': 'Payment failed recorded'})


# =============================================================================
# FINANCE NOTIFICATIONS
# =============================================================================

@admin_required
def notification_center(request):
    """Finance notification center - manage and send invoice notifications."""
    from datetime import timedelta
    from .models import FinanceNotificationLog

    current_year = AcademicYear.get_current()
    current_term = Term.get_current() if hasattr(Term, 'get_current') else None
    today = timezone.now().date()

    # Get invoices with balance
    invoices = Invoice.objects.filter(
        balance__gt=0,
        status__in=['ISSUED', 'PARTIALLY_PAID', 'OVERDUE']
    ).select_related(
        'student', 'student__current_class', 'academic_year', 'term'
    ).prefetch_related('notification_logs').order_by('student__last_name', 'student__first_name')

    # Apply filters
    status_filter = request.GET.get('status', '')
    class_filter = request.GET.get('class_id', '')
    search = request.GET.get('search', '')

    if status_filter:
        invoices = invoices.filter(status=status_filter)
    if class_filter:
        invoices = invoices.filter(student__current_class_id=class_filter)
    if search:
        invoices = invoices.filter(
            Q(student__first_name__icontains=search) |
            Q(student__last_name__icontains=search) |
            Q(invoice_number__icontains=search)
        )

    # Overall Stats
    all_invoices = Invoice.objects.filter(academic_year=current_year)
    total_invoices = all_invoices.count()
    paid_count = all_invoices.filter(status='PAID').count()

    all_with_balance = Invoice.objects.filter(balance__gt=0, status__in=['ISSUED', 'PARTIALLY_PAID', 'OVERDUE'])
    overdue_count = all_with_balance.filter(status='OVERDUE').count()
    partial_count = all_with_balance.filter(status='PARTIALLY_PAID').count()
    issued_count = all_with_balance.filter(status='ISSUED').count()
    total_balance = all_with_balance.aggregate(total=Sum('balance'))['total'] or Decimal('0.00')
    overdue_balance = all_with_balance.filter(status='OVERDUE').aggregate(total=Sum('balance'))['total'] or Decimal('0.00')

    # Collection rate
    total_invoiced = all_invoices.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
    total_collected = Payment.objects.filter(
        invoice__academic_year=current_year,
        status='COMPLETED'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    collection_rate = int((total_collected / total_invoiced * 100) if total_invoiced > 0 else 0)

    # Notification stats
    sent_today = FinanceNotificationLog.objects.filter(
        created_at__date=today
    ).count()

    week_start = today - timedelta(days=today.weekday())
    sent_week = FinanceNotificationLog.objects.filter(
        created_at__date__gte=week_start
    ).count()

    # Class summary with fee collection stats
    classes = Class.objects.filter(
        students__invoices__balance__gt=0
    ).distinct().order_by('name')

    class_summary = []
    for cls in classes:
        class_invoices = Invoice.objects.filter(
            student__current_class=cls,
            academic_year=current_year
        )
        class_total = class_invoices.count()
        class_paid = class_invoices.filter(status='PAID').count()
        class_overdue = class_invoices.filter(status='OVERDUE').count()
        class_pending = class_invoices.filter(status__in=['ISSUED', 'PARTIALLY_PAID']).count()
        class_balance = class_invoices.filter(balance__gt=0).aggregate(total=Sum('balance'))['total'] or Decimal('0.00')
        class_rate = int((class_paid / class_total * 100) if class_total > 0 else 0)

        class_summary.append({
            'class': cls,
            'total': class_total,
            'paid': class_paid,
            'overdue': class_overdue,
            'pending': class_pending,
            'balance': class_balance,
            'rate': class_rate,
        })

    # Get last notification and guardian info for each invoice
    invoice_list = list(invoices)
    for invoice in invoice_list:
        last_log = invoice.notification_logs.first()
        invoice.last_notification = last_log
        # Calculate days overdue
        if invoice.status == 'OVERDUE' and invoice.due_date:
            invoice.days_overdue = (today - invoice.due_date).days
        else:
            invoice.days_overdue = 0
        # Get guardian contact info
        primary_guardian = invoice.student.get_primary_guardian() if hasattr(invoice.student, 'get_primary_guardian') else None
        invoice.guardian_phone = primary_guardian.phone_number if primary_guardian else None
        invoice.guardian_email = primary_guardian.email if primary_guardian else None

    # Separate overdue invoices for dedicated section
    overdue_invoices = [inv for inv in invoice_list if inv.status == 'OVERDUE']

    context = {
        'invoices': invoice_list,
        'overdue_invoices': overdue_invoices,
        'classes': classes,
        'class_summary': class_summary,
        'total_invoices': total_invoices,
        'paid_count': paid_count,
        'overdue_count': overdue_count,
        'partial_count': partial_count,
        'issued_count': issued_count,
        'total_balance': total_balance,
        'overdue_balance': overdue_balance,
        'collection_rate': collection_rate,
        'sent_today': sent_today,
        'sent_week': sent_week,
        'today': today,
        'status_filter': status_filter,
        'class_filter': class_filter,
        'search': search,
        'current_year': current_year,
        'current_term': current_term,
    }

    return htmx_render(
        request,
        'finance/notification_center.html',
        'finance/partials/notification_center_content.html',
        context
    )


@admin_required
def send_invoice_notification_view(request, pk):
    """Send notification for a single invoice."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    invoice = get_object_or_404(Invoice, pk=pk)
    distribution_type = request.POST.get('type', 'SMS')
    notification_type = request.POST.get('notification_type', 'BALANCE_REMINDER')
    custom_sms = request.POST.get('custom_sms', '').strip() or None

    # Get tenant schema
    from django.db import connection
    tenant_schema = connection.tenant.schema_name if hasattr(connection, 'tenant') else 'public'

    # Queue the notification task
    from .tasks import send_invoice_notification
    send_invoice_notification.delay(
        invoice_id=str(invoice.pk),
        notification_type=notification_type,
        distribution_type=distribution_type,
        tenant_schema=tenant_schema,
        sent_by_id=request.user.id,
        custom_sms=custom_sms,
    )

    # Return success response with HTMX trigger for toast
    response = HttpResponse(status=204)
    response['HX-Trigger'] = '{"showToast": {"message": "Notification queued for sending", "type": "success"}}'
    return response


@admin_required
def send_bulk_notifications_view(request):
    """Send bulk notifications for multiple invoices."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    distribution_type = request.POST.get('type', 'SMS')
    notification_type = request.POST.get('notification_type', 'OVERDUE_REMINDER')
    custom_sms = request.POST.get('custom_sms', '').strip() or None

    # Build filters from request
    filters = {}
    if request.POST.get('status'):
        filters['status'] = request.POST.get('status')
    if request.POST.get('class_id'):
        filters['class_id'] = request.POST.get('class_id')

    # Get selected invoice IDs if any
    selected_ids = request.POST.getlist('invoice_ids')
    if selected_ids:
        filters['invoice_ids'] = selected_ids

    # Get tenant schema
    from django.db import connection
    tenant_schema = connection.tenant.schema_name if hasattr(connection, 'tenant') else 'public'

    # Queue the bulk notification task
    from .tasks import send_bulk_notifications
    send_bulk_notifications.delay(
        notification_type=notification_type,
        distribution_type=distribution_type,
        tenant_schema=tenant_schema,
        sent_by_id=request.user.id,
        filters=filters,
        custom_sms=custom_sms,
    )

    # Return success response with HTMX trigger
    response = HttpResponse(status=204)
    response['HX-Trigger'] = '{"showToast": {"message": "Bulk notifications queued for sending", "type": "success"}}'
    return response


@admin_required
def notification_history(request):
    """View notification history with filters."""
    from datetime import timedelta
    from .models import FinanceNotificationLog

    today = timezone.now().date()

    logs = FinanceNotificationLog.objects.select_related(
        'invoice', 'invoice__student', 'sent_by'
    ).order_by('-created_at')

    # Stats for all logs (before filtering)
    all_logs = FinanceNotificationLog.objects.all()
    total_count = all_logs.count()
    success_count = all_logs.filter(Q(email_status='SENT') | Q(sms_status='SENT')).count()
    failed_count = all_logs.filter(email_status='FAILED', sms_status='FAILED').count()
    delivery_rate = int((success_count / total_count * 100) if total_count > 0 else 0)

    today_count = all_logs.filter(created_at__date=today).count()
    week_start = today - timedelta(days=today.weekday())
    week_count = all_logs.filter(created_at__date__gte=week_start).count()

    # Filters
    notification_type = request.GET.get('notification_type', '')
    status = request.GET.get('status', '')
    search = request.GET.get('search', '')

    if notification_type:
        logs = logs.filter(notification_type=notification_type)
    if status:
        if status == 'SUCCESS':
            logs = logs.filter(Q(email_status='SENT') | Q(sms_status='SENT'))
        elif status == 'FAILED':
            logs = logs.filter(email_status='FAILED', sms_status='FAILED')
        elif status == 'PENDING':
            logs = logs.filter(email_status='PENDING', sms_status='PENDING')
    if search:
        logs = logs.filter(
            Q(invoice__invoice_number__icontains=search) |
            Q(invoice__student__first_name__icontains=search) |
            Q(invoice__student__last_name__icontains=search)
        )

    # Paginate
    paginator = Paginator(logs, 50)
    page = request.GET.get('page', 1)
    logs = paginator.get_page(page)

    context = {
        'logs': logs,
        'notification_type': notification_type,
        'status_filter': status,
        'search': search,
        'notification_types': FinanceNotificationLog.NOTIFICATION_TYPE,
        'success_count': success_count,
        'failed_count': failed_count,
        'delivery_rate': delivery_rate,
        'today_count': today_count,
        'week_count': week_count,
    }

    return htmx_render(
        request,
        'finance/notification_history.html',
        'finance/partials/notification_history_content.html',
        context
    )
