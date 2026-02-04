import logging
import secrets
import string

from django.shortcuts import redirect, get_object_or_404, render
from django.http import HttpResponse
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.core.paginator import Paginator

from accounts.models import User
from core.email_backend import get_from_email
from academics.models import Class
from students.models import Student, Guardian, StudentGuardian
from students.forms import StudentForm, GuardianForm
from .utils import admin_required, htmx_render, create_enrollment_for_student

logger = logging.getLogger(__name__)


def generate_temp_password(length=10):
    """Generate a random temporary password."""
    chars = string.ascii_letters + string.digits
    return ''.join(secrets.choice(chars) for _ in range(length))


def send_student_credentials(user, password, student):
    """Send login credentials to student's guardian email."""
    from smtplib import SMTPException

    try:
        # Get primary guardian email
        guardian_email = None
        primary_guardian = student.get_primary_guardian()
        if primary_guardian and primary_guardian.email:
            guardian_email = primary_guardian.email

        recipient = user.email or guardian_email
        if not recipient:
            return False

        subject = f"Student Portal Login - {student.full_name}"
        message = render_to_string('students/emails/account_credentials.txt', {
            'student': student,
            'user': user,
            'password': password,
        })

        send_mail(
            subject,
            message,
            get_from_email(),
            [recipient],
            fail_silently=False,
        )
        return True
    except SMTPException as e:
        logger.error(f"Failed to send student credentials email: {e}")
        return False
    except OSError as e:
        logger.error(f"Network error sending student credentials: {e}")
        return False


@admin_required
def index(request):
    """Student list page with search and filter."""
    students = Student.objects.select_related('current_class').prefetch_related('guardians').all()

    # Search
    search = request.GET.get('search', '').strip()
    if search:
        students = students.filter(
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(middle_name__icontains=search) |
            Q(admission_number__icontains=search)
        )

    # Filter by class
    class_filter = request.GET.get('class', '')
    if class_filter:
        students = students.filter(current_class_id=class_filter)

    # Filter by status
    status_filter = request.GET.get('status', '')
    if status_filter:
        students = students.filter(status=status_filter)

    # Pagination
    per_page = request.GET.get('per_page', '25')
    try:
        per_page = int(per_page)
        if per_page not in [25, 50, 100]:
            per_page = 25
    except ValueError:
        per_page = 25

    paginator = Paginator(students.order_by('-created_at'), per_page)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'students': page_obj,
        'page_obj': page_obj,
        'paginator': paginator,
        'per_page': per_page,
        'classes': Class.objects.filter(is_active=True),
        'status_choices': Student.Status.choices,
        'search': search,
        'class_filter': class_filter,
        'status_filter': status_filter,
        'form': StudentForm(),
        'guardian_form': GuardianForm(),
        # Navigation
        'breadcrumbs': [
            {'label': 'Home', 'url': '/', 'icon': 'fa-solid fa-home'},
            {'label': 'Students'},
        ],
    }

    return htmx_render(
        request,
        'students/index.html',
        'students/partials/index_content.html',
        context
    )


@admin_required
def student_create(request):
    """Create a new student."""
    breadcrumbs = [
        {'label': 'Home', 'url': '/', 'icon': 'fa-solid fa-home'},
        {'label': 'Students', 'url': '/students/'},
        {'label': 'Add Student'},
    ]

    if request.method == 'GET':
        form = StudentForm()
        return htmx_render(
            request,
            'students/student_form.html',
            'students/partials/student_form_content.html',
            {
                'form': form,
                'guardian_form': GuardianForm(),
                'relationship_choices': Guardian.Relationship.choices,
                'breadcrumbs': breadcrumbs,
                'back_url': '/students/',
            }
        )

    if request.method != 'POST':
        return HttpResponse(status=405)

    form = StudentForm(request.POST, request.FILES)
    if form.is_valid():
        student = form.save()
        # Auto-create enrollment for current academic year
        enrollment, created = create_enrollment_for_student(student)
        if created:
            student.current_class = enrollment.class_assigned
            student.save()
        # Redirect to edit page to add guardians
        return redirect('students:student_edit', pk=student.pk)

    return htmx_render(
        request,
        'students/student_form.html',
        'students/partials/student_form_content.html',
        {
            'form': form,
            'guardian_form': GuardianForm(),
            'relationship_choices': Guardian.Relationship.choices,
            'breadcrumbs': breadcrumbs,
            'back_url': '/students/',
        }
    )


@admin_required
def student_edit(request, pk):
    """Edit a student."""
    student = get_object_or_404(
        Student.objects.prefetch_related('student_guardians__guardian'),
        pk=pk
    )
    student_guardians = student.get_guardians_with_relationships()

    breadcrumbs = [
        {'label': 'Home', 'url': '/', 'icon': 'fa-solid fa-home'},
        {'label': 'Students', 'url': '/students/'},
        {'label': student.full_name, 'url': f'/students/{pk}/'},
        {'label': 'Edit'},
    ]
    back_url = f'/students/{pk}/'

    if request.method == 'GET':
        form = StudentForm(instance=student)
        return htmx_render(
            request,
            'students/student_form.html',
            'students/partials/student_form_content.html',
            {
                'form': form,
                'student': student,
                'student_guardians': student_guardians,
                'guardian_form': GuardianForm(),
                'relationship_choices': Guardian.Relationship.choices,
                'breadcrumbs': breadcrumbs,
                'back_url': back_url,
            }
        )

    if request.method != 'POST':
        return HttpResponse(status=405)

    form = StudentForm(request.POST, request.FILES, instance=student)
    if form.is_valid():
        student = form.save()
        # Ensure current_class is updated if changed in the form
        enrollment, created = create_enrollment_for_student(student)
        if created:
            student.current_class = enrollment.class_assigned
            student.save()
        return redirect('students:student_detail', pk=student.pk)

    return htmx_render(
        request,
        'students/student_form.html',
        'students/partials/student_form_content.html',
        {
            'form': form,
            'student': student,
            'student_guardians': student_guardians,
            'guardian_form': GuardianForm(),
            'relationship_choices': Guardian.Relationship.choices,
            'breadcrumbs': breadcrumbs,
            'back_url': back_url,
        }
    )


@admin_required
def student_delete(request, pk):
    """Delete a student."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    student = get_object_or_404(Student, pk=pk)
    student.delete()

    if request.htmx:
        response = HttpResponse(status=200)
        response['HX-Refresh'] = 'true'
        return response
    return redirect('students:index')


@admin_required
def student_detail(request, pk):
    """View student details."""
    student = get_object_or_404(
        Student.objects.select_related('current_class', 'user').prefetch_related(
            'student_guardians__guardian'
        ),
        pk=pk
    )
    enrollments = student.get_enrollment_history()
    student_guardians = student.get_guardians_with_relationships()

    breadcrumbs = [
        {'label': 'Home', 'url': '/', 'icon': 'fa-solid fa-home'},
        {'label': 'Students', 'url': '/students/'},
        {'label': student.full_name},
    ]

    return htmx_render(
        request,
        'students/student_detail.html',
        'students/partials/student_detail_content.html',
        {
            'student': student,
            'enrollments': enrollments,
            'student_guardians': student_guardians,
            'breadcrumbs': breadcrumbs,
            'back_url': '/students/',
        }
    )


# ============ Student Guardian Management ============

@admin_required
@require_POST
def student_add_guardian(request, pk):
    """Add a guardian to a student."""
    student = get_object_or_404(Student, pk=pk)

    guardian_id = request.POST.get('guardian_id')
    relationship = request.POST.get('relationship', Guardian.Relationship.GUARDIAN)
    is_primary = request.POST.get('is_primary') == 'true'

    if not guardian_id:
        if request.htmx:
            return HttpResponse(
                '<div class="alert alert-error">Please select a guardian</div>',
                status=400
            )
        return redirect('students:student_edit', pk=pk)

    guardian = get_object_or_404(Guardian, pk=guardian_id)

    # Check if already linked
    if StudentGuardian.objects.filter(student=student, guardian=guardian).exists():
        if request.htmx:
            return HttpResponse(
                '<div class="alert alert-warning">This guardian is already linked to this student</div>',
                status=400
            )
        return redirect('students:student_edit', pk=pk)

    # Add guardian
    student.add_guardian(guardian, relationship, is_primary=is_primary)

    if request.htmx:
        # Return updated guardian list
        student_guardians = student.get_guardians_with_relationships()
        return render(request, 'students/partials/student_guardians_list.html', {
            'student': student,
            'student_guardians': student_guardians,
            'relationship_choices': Guardian.Relationship.choices,
        })

    return redirect('students:student_edit', pk=pk)


@admin_required
@require_POST
def student_remove_guardian(request, pk, guardian_pk):
    """Remove a guardian from a student."""
    student = get_object_or_404(Student, pk=pk)
    guardian = get_object_or_404(Guardian, pk=guardian_pk)

    student.remove_guardian(guardian)

    if request.htmx:
        # Return updated guardian list
        student_guardians = student.get_guardians_with_relationships()
        return render(request, 'students/partials/student_guardians_list.html', {
            'student': student,
            'student_guardians': student_guardians,
            'relationship_choices': Guardian.Relationship.choices,
        })

    return redirect('students:student_edit', pk=pk)


@admin_required
@require_POST
def student_set_primary_guardian(request, pk, guardian_pk):
    """Set a guardian as primary for a student."""
    student = get_object_or_404(Student, pk=pk)

    try:
        sg = StudentGuardian.objects.get(student=student, guardian_id=guardian_pk)
        sg.is_primary = True
        sg.save()  # This will unset other primary guardians
    except StudentGuardian.DoesNotExist:
        pass

    if request.htmx:
        student_guardians = student.get_guardians_with_relationships()
        return render(request, 'students/partials/student_guardians_list.html', {
            'student': student,
            'student_guardians': student_guardians,
            'relationship_choices': Guardian.Relationship.choices,
        })

    return redirect('students:student_edit', pk=pk)


@admin_required
@require_POST
def student_update_guardian_relationship(request, pk, guardian_pk):
    """Update the relationship type for a student-guardian link."""
    student = get_object_or_404(Student, pk=pk)
    relationship = request.POST.get('relationship', Guardian.Relationship.GUARDIAN)

    try:
        sg = StudentGuardian.objects.get(student=student, guardian_id=guardian_pk)
        sg.relationship = relationship
        sg.save()
    except StudentGuardian.DoesNotExist:
        pass

    if request.htmx:
        student_guardians = student.get_guardians_with_relationships()
        return render(request, 'students/partials/student_guardians_list.html', {
            'student': student,
            'student_guardians': student_guardians,
            'relationship_choices': Guardian.Relationship.choices,
        })

    return redirect('students:student_edit', pk=pk)


@admin_required
def student_detail_pdf(request, pk):
    """Download PDF profile for a student."""
    import logging
    from io import BytesIO
    from django.template.loader import render_to_string
    from django.conf import settings as django_settings
    from django.db import connection

    logger = logging.getLogger(__name__)

    student = get_object_or_404(
        Student.objects.select_related('current_class'),
        pk=pk
    )

    # Get guardians
    student_guardians = student.get_guardians_with_relationships()

    # Get enrollment history
    enrollments = student.enrollments.select_related(
        'academic_year', 'class_assigned'
    ).order_by('-academic_year__start_date')

    # Get school context with logo
    from gradebook.utils import get_school_context
    school_ctx = get_school_context(include_logo_base64=True)

    # Encode student photo if exists
    photo_base64 = None
    if student.photo:
        try:
            import base64
            import os
            photo_path = os.path.join(
                django_settings.MEDIA_ROOT,
                'schools',
                connection.schema_name,
                student.photo.name.split('/')[-1] if '/' in student.photo.name else student.photo.name
            )
            # Try direct path first
            if not os.path.exists(photo_path):
                photo_path = student.photo.path

            if os.path.exists(photo_path):
                with open(photo_path, 'rb') as f:
                    photo_data = f.read()
                    ext = os.path.splitext(photo_path)[1].lower()
                    mime_types = {
                        '.jpg': 'image/jpeg',
                        '.jpeg': 'image/jpeg',
                        '.png': 'image/png',
                        '.gif': 'image/gif',
                        '.webp': 'image/webp',
                    }
                    mime = mime_types.get(ext, 'image/jpeg')
                    photo_base64 = f"data:{mime};base64,{base64.b64encode(photo_data).decode()}"
        except (IOError, OSError, ValueError) as e:
            logger.warning(f"Could not encode student photo for {student.admission_number}: {e}")

    # Create verification record and generate QR code
    from core.models import DocumentVerification
    from core.utils import generate_verification_qr

    verification = DocumentVerification.create_for_document(
        document_type=DocumentVerification.DocumentType.STUDENT_PROFILE,
        student=student,
        title=f"Student Profile - {student.full_name}",
        user=request.user,
    )

    # Generate QR code for verification
    qr_code_base64 = generate_verification_qr(verification.verification_code, request=request)

    context = {
        'student': student,
        'student_guardians': student_guardians,
        'enrollments': enrollments,
        'school': school_ctx['school'],
        'school_settings': school_ctx['school_settings'],
        'logo_base64': school_ctx.get('logo_base64'),
        'photo_base64': photo_base64,
        'verification': verification,
        'qr_code_base64': qr_code_base64,
    }

    # Generate PDF using WeasyPrint
    try:
        from weasyprint import HTML

        html_string = render_to_string('students/student_detail_pdf.html', context)
        html = HTML(string=html_string, base_url=str(django_settings.BASE_DIR))
        pdf_buffer = BytesIO()
        html.write_pdf(pdf_buffer)
        pdf_buffer.seek(0)

        response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="student_profile_{student.admission_number}.pdf"'
        return response

    except ImportError:
        logger.error("WeasyPrint not installed")
        from django.contrib import messages
        messages.error(request, 'PDF generation is not available. WeasyPrint is not installed.')
        return redirect('students:student_detail', pk=pk)
    except Exception as e:
        import traceback
        logger.error(f"Failed to generate student PDF: {str(e)}\n{traceback.format_exc()}")
        from django.contrib import messages
        messages.error(request, f'Failed to generate PDF: {str(e)}')
        return redirect('students:student_detail', pk=pk)


@admin_required
def student_create_account(request, pk):
    """Create a user account for a student - Admin only."""
    student = get_object_or_404(Student, pk=pk)

    # If student already has an account, redirect
    if student.user:
        messages.warning(request, f"{student.full_name} already has an account.")
        response = HttpResponse(status=204)
        response['HX-Refresh'] = 'true'
        return response

    # Get primary guardian for email
    primary_guardian = student.get_primary_guardian()
    guardian_email = primary_guardian.email if primary_guardian else None

    if request.method == 'GET':
        return render(request, 'students/partials/modal_create_account.html', {
            'student': student,
            'guardian_email': guardian_email,
        })

    if request.method == 'POST':
        email = request.POST.get('email', '').strip()

        if not email:
            return render(request, 'students/partials/modal_create_account.html', {
                'student': student,
                'guardian_email': guardian_email,
                'error': 'Email address is required.',
            })

        # Generate temporary password
        temp_password = generate_temp_password()

        # Create user account with atomic transaction to prevent race conditions
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    email=email,
                    password=temp_password,
                    first_name=student.first_name,
                    last_name=student.last_name,
                    is_student=True,
                    must_change_password=True,
                )
                # Link to student
                student.user = user
                student.save(update_fields=['user'])
        except IntegrityError:
            return render(request, 'students/partials/modal_create_account.html', {
                'student': student,
                'guardian_email': guardian_email,
                'error': f"An account with email '{email}' already exists.",
            })

        # Send credentials via email
        email_sent = send_student_credentials(user, temp_password, student)

        if email_sent:
            messages.success(
                request,
                f"Account created for {student.full_name}. Credentials sent to {email}."
            )
        else:
            # Show the password if email failed
            messages.warning(
                request,
                f"Account created but email failed. Temporary password: {temp_password}"
            )

        response = HttpResponse(status=204)
        response['HX-Refresh'] = 'true'
        return response

    return HttpResponse(status=405)
