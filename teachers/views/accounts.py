import logging
import secrets
import string

from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse
from django.db import IntegrityError, transaction
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings

from accounts.models import User
from teachers.models import Teacher
from .utils import admin_required

logger = logging.getLogger(__name__)


def generate_temp_password(length=10):
    """Generate a random temporary password."""
    chars = string.ascii_letters + string.digits
    return ''.join(secrets.choice(chars) for _ in range(length))


def send_account_credentials(user, password, teacher):
    """Send account credentials via email."""
    subject = "Your Teacher Account Has Been Created"
    message = f"""
Dear {teacher.get_title_display()} {teacher.full_name},

Your account for the school management system has been created.

Login Details:
Email: {user.email}
Temporary Password: {password}

Please log in and change your password immediately.

This is an automated message. Please do not reply.
"""
    from smtplib import SMTPException

    try:
        send_mail(
            subject,
            message,
            getattr(settings, 'DEFAULT_FROM_EMAIL', None),
            [user.email],
            fail_silently=False,
        )
        return True
    except SMTPException as e:
        logger.error(f"Failed to send teacher credentials email: {e}")
        return False
    except OSError as e:
        logger.error(f"Network error sending teacher credentials: {e}")
        return False


@admin_required
def create_account(request, pk):
    """Create a user account for a teacher."""
    teacher = get_object_or_404(Teacher, pk=pk)

    # If teacher already has an account, redirect
    if teacher.user:
        messages.warning(request, f"{teacher.full_name} already has an account.")
        response = HttpResponse(status=204)
        response['HX-Refresh'] = 'true'
        return response

    if request.method == 'GET':
        return render(request, 'teachers/partials/modal_create_account.html', {
            'teacher': teacher,
        })

    if request.method == 'POST':
        email = request.POST.get('email', '').strip()

        # Use teacher's email if not provided
        if not email:
            email = teacher.email

        if not email:
            return render(request, 'teachers/partials/modal_create_account.html', {
                'teacher': teacher,
                'error': 'Email address is required. Please provide an email.',
            })

        # Generate temporary password
        temp_password = generate_temp_password()

        # Create user account with atomic transaction to prevent race conditions
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    email=email,
                    password=temp_password,
                    first_name=teacher.first_name,
                    last_name=teacher.last_name,
                    is_teacher=True,
                    must_change_password=True,
                )

                # Link to teacher
                teacher.user = user
                teacher.save(update_fields=['user'])

                # Also update teacher email if it was empty
                if not teacher.email:
                    teacher.email = email
                    teacher.save(update_fields=['email'])
        except IntegrityError:
            return render(request, 'teachers/partials/modal_create_account.html', {
                'teacher': teacher,
                'error': f"An account with email '{email}' already exists.",
            })

        # Send credentials via email
        email_sent = send_account_credentials(user, temp_password, teacher)

        if email_sent:
            messages.success(
                request,
                f"Account created for {teacher.full_name}. Credentials sent to {email}."
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


@admin_required
def deactivate_account(request, pk):
    """Deactivate a teacher's user account."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    teacher = get_object_or_404(Teacher, pk=pk)

    if teacher.user:
        user = teacher.user
        user.is_active = False
        user.save(update_fields=['is_active'])
        messages.success(request, f"Account for {teacher.full_name} has been deactivated.")

    response = HttpResponse(status=204)
    response['HX-Refresh'] = 'true'
    return response


@admin_required
def reset_password(request, pk):
    """Reset a teacher's password and send new credentials."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    teacher = get_object_or_404(Teacher, pk=pk)

    if not teacher.user:
        messages.error(request, f"{teacher.full_name} does not have an account.")
        response = HttpResponse(status=204)
        response['HX-Refresh'] = 'true'
        return response

    # Generate new temporary password
    temp_password = generate_temp_password()

    user = teacher.user
    user.set_password(temp_password)
    user.must_change_password = True
    user.save(update_fields=['password', 'must_change_password'])

    # Send new credentials
    email_sent = send_account_credentials(user, temp_password, teacher)

    if email_sent:
        messages.success(
            request,
            f"Password reset for {teacher.full_name}. New credentials sent to {user.email}."
        )
    else:
        messages.warning(
            request,
            f"Password reset but email failed. New temporary password: {temp_password}"
        )

    response = HttpResponse(status=204)
    response['HX-Refresh'] = 'true'
    return response
