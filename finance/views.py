from functools import wraps
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.db.models import Sum, Count, Q, F
from django.contrib import messages
from django.core.paginator import Paginator

from .models import (
    PaymentGateway, PaymentGatewayConfig, FeeType, FeeStructure,
    Scholarship, StudentScholarship, Invoice, InvoiceItem, Payment
)
from .forms import (
    FeeTypeForm, FeeStructureForm, ScholarshipForm, StudentScholarshipForm,
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
# FEE TYPES
# =============================================================================

@admin_required
def fee_types(request):
    """List all fee types."""
    fee_types_list = FeeType.objects.all().order_by('category', 'name')

    # Group by category
    fee_types_by_category = {}
    for fee_type in fee_types_list:
        category = fee_type.get_category_display()
        if category not in fee_types_by_category:
            fee_types_by_category[category] = []
        fee_types_by_category[category].append(fee_type)

    context = {
        'fee_types': fee_types_list,
        'fee_types_by_category': fee_types_by_category,
        'form': FeeTypeForm(),
    }

    return htmx_render(
        request,
        'finance/fee_types.html',
        'finance/partials/fee_types_content.html',
        context
    )


@admin_required
def fee_type_create(request):
    """Create a new fee type."""
    if request.method == 'POST':
        form = FeeTypeForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Fee type created successfully.')
            return redirect('finance:fee_types')
    else:
        form = FeeTypeForm()

    return htmx_render(
        request,
        'finance/fee_type_form.html',
        'finance/partials/fee_type_form_content.html',
        {'form': form}
    )


@admin_required
def fee_type_edit(request, pk):
    """Edit a fee type."""
    fee_type = get_object_or_404(FeeType, pk=pk)

    if request.method == 'POST':
        form = FeeTypeForm(request.POST, instance=fee_type)
        if form.is_valid():
            form.save()
            messages.success(request, 'Fee type updated successfully.')
            return redirect('finance:fee_types')
    else:
        form = FeeTypeForm(instance=fee_type)

    return htmx_render(
        request,
        'finance/fee_type_form.html',
        'finance/partials/fee_type_form_content.html',
        {'form': form, 'fee_type': fee_type}
    )


@admin_required
def fee_type_delete(request, pk):
    """Delete a fee type."""
    fee_type = get_object_or_404(FeeType, pk=pk)

    if request.method == 'POST':
        fee_type.delete()
        messages.success(request, 'Fee type deleted successfully.')
        return redirect('finance:fee_types')

    return htmx_render(
        request,
        'finance/fee_type_delete.html',
        'finance/partials/fee_type_delete_content.html',
        {'fee_type': fee_type}
    )


# =============================================================================
# FEE STRUCTURES
# =============================================================================

@admin_required
def fee_structures(request):
    """List fee structures with filtering."""
    current_year = AcademicYear.get_current()

    structures = FeeStructure.objects.select_related(
        'fee_type', 'class_assigned', 'programme', 'academic_year', 'term'
    ).order_by('-academic_year__start_date', 'fee_type__category')

    # Filters
    year_filter = request.GET.get('year')
    if year_filter:
        structures = structures.filter(academic_year_id=year_filter)
    else:
        structures = structures.filter(academic_year=current_year)

    category_filter = request.GET.get('category')
    if category_filter:
        structures = structures.filter(fee_type__category=category_filter)

    context = {
        'structures': structures,
        'current_year': current_year,
        'academic_years': AcademicYear.objects.all().order_by('-start_date'),
        'categories': FeeType.CATEGORY_CHOICES,
        'form': FeeStructureForm(),
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
            return redirect('finance:fee_structures')
    else:
        form = FeeStructureForm()

    return htmx_render(
        request,
        'finance/fee_structure_form.html',
        'finance/partials/fee_structure_form_content.html',
        {'form': form}
    )


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

    return htmx_render(
        request,
        'finance/fee_structure_form.html',
        'finance/partials/fee_structure_form_content.html',
        {'form': form, 'structure': structure}
    )


@admin_required
def fee_structure_delete(request, pk):
    """Delete a fee structure."""
    structure = get_object_or_404(FeeStructure, pk=pk)

    if request.method == 'POST':
        structure.delete()
        messages.success(request, 'Fee structure deleted successfully.')
        return redirect('finance:fee_structures')

    return htmx_render(
        request,
        'finance/fee_structure_delete.html',
        'finance/partials/fee_structure_delete_content.html',
        {'structure': structure}
    )


# =============================================================================
# SCHOLARSHIPS
# =============================================================================

@admin_required
def scholarships(request):
    """List all scholarships."""
    scholarships_list = Scholarship.objects.annotate(
        recipient_count=Count('recipients', filter=Q(recipients__is_active=True))
    ).order_by('name')

    context = {
        'scholarships': scholarships_list,
        'form': ScholarshipForm(),
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

    return htmx_render(
        request,
        'finance/scholarship_form.html',
        'finance/partials/scholarship_form_content.html',
        {'form': form}
    )


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

    return htmx_render(
        request,
        'finance/scholarship_form.html',
        'finance/partials/scholarship_form_content.html',
        {'form': form, 'scholarship': scholarship}
    )


@admin_required
def scholarship_delete(request, pk):
    """Delete a scholarship."""
    scholarship = get_object_or_404(Scholarship, pk=pk)

    if request.method == 'POST':
        scholarship.delete()
        messages.success(request, 'Scholarship deleted successfully.')
        return redirect('finance:scholarships')

    return htmx_render(
        request,
        'finance/scholarship_delete.html',
        'finance/partials/scholarship_delete_content.html',
        {'scholarship': scholarship}
    )


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

    context = {
        'invoices': invoices_page,
        'current_year': current_year,
        'status_choices': Invoice.STATUS_CHOICES,
        'classes': Class.objects.filter(is_active=True),
        'status_filter': status_filter,
        'class_filter': class_filter,
        'search': search,
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

    context = {
        'form': form,
        'classes': Class.objects.filter(is_active=True),
    }

    return htmx_render(
        request,
        'finance/invoice_generate.html',
        'finance/partials/invoice_generate_content.html',
        context
    )


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
    ).select_related('fee_type')

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
        fee_type = structure.fee_type

        # Check if fee applies to student type (boarding/day)
        if hasattr(student, 'is_boarding'):
            if student.is_boarding and not fee_type.applies_to_boarding:
                continue
            if not student.is_boarding and not fee_type.applies_to_day:
                continue

        InvoiceItem.objects.create(
            invoice=invoice,
            fee_type=fee_type,
            description=fee_type.name,
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

    items = invoice.items.select_related('fee_type').all()
    payments = invoice.payments.all().order_by('-created_at')

    # Check if online payment gateway is available
    gateway_available = PaymentGatewayConfig.objects.filter(
        is_active=True,
        is_primary=True,
        verification_status='VERIFIED'
    ).exists()

    context = {
        'invoice': invoice,
        'items': items,
        'payments': payments,
        'gateway_available': gateway_available,
    }

    return htmx_render(
        request,
        'finance/invoice_detail.html',
        'finance/partials/invoice_detail_content.html',
        context
    )


@admin_required
def invoice_edit(request, pk):
    """Edit invoice (only draft invoices)."""
    invoice = get_object_or_404(Invoice, pk=pk)

    if invoice.status != 'DRAFT':
        messages.error(request, 'Only draft invoices can be edited.')
        return redirect('finance:invoice_detail', pk=pk)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'issue':
            invoice.status = 'ISSUED'
            invoice.issue_date = timezone.now().date()
            invoice.save()
            messages.success(request, 'Invoice issued successfully.')
            return redirect('finance:invoice_detail', pk=pk)

    context = {
        'invoice': invoice,
        'items': invoice.items.select_related('fee_type').all(),
    }

    return htmx_render(
        request,
        'finance/invoice_edit.html',
        'finance/partials/invoice_edit_content.html',
        context
    )


@admin_required
def invoice_cancel(request, pk):
    """Cancel an invoice."""
    invoice = get_object_or_404(Invoice, pk=pk)

    if invoice.status == 'PAID':
        messages.error(request, 'Cannot cancel a paid invoice.')
        return redirect('finance:invoice_detail', pk=pk)

    if request.method == 'POST':
        invoice.status = 'CANCELLED'
        invoice.save()
        messages.success(request, 'Invoice cancelled successfully.')
        return redirect('finance:invoices')

    return htmx_render(
        request,
        'finance/invoice_cancel.html',
        'finance/partials/invoice_cancel_content.html',
        {'invoice': invoice}
    )


@admin_required
def invoice_print(request, pk):
    """Print-friendly invoice view."""
    invoice = get_object_or_404(
        Invoice.objects.select_related('student', 'academic_year', 'term'),
        pk=pk
    )

    context = {
        'invoice': invoice,
        'items': invoice.items.select_related('fee_type').all(),
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

    context = {
        'payments': payments_page,
        'status_choices': Payment.STATUS_CHOICES,
        'method_choices': Payment.METHOD_CHOICES,
        'status_filter': status_filter,
        'method_filter': method_filter,
        'search': search,
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
            return redirect('finance:payment_detail', pk=payment.pk)
    else:
        form = PaymentForm()

    # Get pending invoices for dropdown
    pending_invoices = Invoice.objects.filter(
        status__in=['ISSUED', 'PARTIALLY_PAID', 'OVERDUE']
    ).select_related('student').order_by('student__last_name')

    context = {
        'form': form,
        'pending_invoices': pending_invoices,
    }

    return htmx_render(
        request,
        'finance/payment_record.html',
        'finance/partials/payment_record_content.html',
        context
    )


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

    # Summary by day
    by_day = payments.extra(
        select={'date': 'DATE(transaction_date)'}
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
    ).select_related('fee_type')

    fees = []
    for structure in structures:
        fees.append({
            'fee_type': structure.fee_type.name,
            'amount': float(structure.amount),
            'is_mandatory': structure.fee_type.is_mandatory,
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
    """
    # Get signature from headers
    signature = request.headers.get('X-Paystack-Signature', '') or \
                request.headers.get('X-Flutterwave-Signature', '') or \
                request.headers.get('X-Hubtel-Signature', '')

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)

    # Determine which gateway this is from and get reference
    reference = None
    if 'data' in payload and 'reference' in payload.get('data', {}):
        reference = payload['data']['reference']
    elif 'Data' in payload and 'ClientReference' in payload.get('Data', {}):
        reference = payload['Data']['ClientReference']  # Hubtel format

    if not reference:
        return JsonResponse({'status': 'error', 'message': 'No reference found'}, status=400)

    # Find the payment
    from .models import Payment, PaymentGatewayTransaction
    try:
        payment = Payment.objects.get(reference=reference)
        gateway_tx = payment.gateway_transaction
        gateway_config = gateway_tx.gateway_config
    except (Payment.DoesNotExist, PaymentGatewayTransaction.DoesNotExist):
        return JsonResponse({'status': 'error', 'message': 'Payment not found'}, status=404)

    # Skip if already processed
    if payment.status == 'COMPLETED':
        return JsonResponse({'status': 'success', 'message': 'Already processed'})

    # Verify with gateway adapter
    from .gateways import get_gateway_adapter
    adapter = get_gateway_adapter(gateway_config)
    response = adapter.handle_webhook(payload, signature)

    # Store webhook data
    gateway_tx.callback_data = payload
    gateway_tx.save()

    if response.success:
        payment.status = 'COMPLETED'
        payment.transaction_date = timezone.now()
        payment.save()

        gateway_tx.gateway_transaction_id = response.transaction_id
        gateway_tx.gateway_fee = response.gateway_fee
        gateway_tx.net_amount = response.amount - response.gateway_fee
        gateway_tx.save()

        return JsonResponse({'status': 'success', 'message': 'Payment confirmed'})
    else:
        payment.status = 'FAILED'
        payment.save()

        return JsonResponse({'status': 'success', 'message': 'Payment failed recorded'})
