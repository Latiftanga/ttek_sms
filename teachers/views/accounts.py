import logging
import secrets
import string

from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.db import IntegrityError, transaction
from django.contrib import messages
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from accounts.models import User
from core.email_backend import get_from_email
from teachers.models import Teacher, TeacherInvitation
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
            get_from_email(),
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


# =============================================================================
# Invitation-based Account Creation
# =============================================================================

def send_invitation_email(invitation, request):
    """Send invitation email to teacher."""
    teacher = invitation.teacher

    # Build the accept URL
    accept_url = request.build_absolute_uri(f'/teachers/invite/{invitation.token}/')

    # Email context
    context = {
        'teacher': teacher,
        'invitation': invitation,
        'accept_url': accept_url,
        'expires_hours': 72,
    }

    # Render email content
    html_message = render_to_string('teachers/emails/invitation_email.html', context)
    plain_message = strip_tags(html_message)

    subject = "You're Invited to Join the School Portal"

    from smtplib import SMTPException
    try:
        send_mail(
            subject,
            plain_message,
            get_from_email(),
            [invitation.email],
            html_message=html_message,
            fail_silently=False,
        )
        return True
    except SMTPException as e:
        logger.error(f"Failed to send teacher invitation email: {e}")
        return False
    except OSError as e:
        logger.error(f"Network error sending teacher invitation: {e}")
        return False


@admin_required
def send_invitation(request, pk):
    """Send an invitation to a teacher to create their account."""
    teacher = get_object_or_404(Teacher, pk=pk)

    # If teacher already has an account, redirect
    if teacher.user:
        messages.warning(request, f"{teacher.full_name} already has an account.")
        response = HttpResponse(status=204)
        response['HX-Refresh'] = 'true'
        return response

    if request.method == 'GET':
        # Check for existing pending invitation
        pending_invitation = TeacherInvitation.objects.filter(
            teacher=teacher,
            status=TeacherInvitation.Status.PENDING
        ).first()

        return render(request, 'teachers/partials/modal_send_invitation.html', {
            'teacher': teacher,
            'pending_invitation': pending_invitation,
        })

    if request.method == 'POST':
        email = request.POST.get('email', '').strip()

        # Use teacher's email if not provided
        if not email:
            email = teacher.email

        if not email:
            return render(request, 'teachers/partials/modal_send_invitation.html', {
                'teacher': teacher,
                'error': 'Email address is required. Please provide an email.',
            })

        # Check if email already exists as a user
        if User.objects.filter(email=email).exists():
            return render(request, 'teachers/partials/modal_send_invitation.html', {
                'teacher': teacher,
                'error': f"An account with email '{email}' already exists.",
            })

        # Create invitation
        invitation = TeacherInvitation.create_for_teacher(
            teacher=teacher,
            email=email,
            created_by=request.user
        )

        # Update teacher's email if it was empty
        if not teacher.email:
            teacher.email = email
            teacher.save(update_fields=['email'])

        # Send invitation email
        email_sent = send_invitation_email(invitation, request)

        if email_sent:
            messages.success(
                request,
                f"Invitation sent to {teacher.full_name} at {email}."
            )
        else:
            # Show the link if email failed
            accept_url = request.build_absolute_uri(f'/teachers/invite/{invitation.token}/')
            messages.warning(
                request,
                f"Invitation created but email failed. Share this link: {accept_url}"
            )

        response = HttpResponse(status=204)
        response['HX-Refresh'] = 'true'
        return response

    return HttpResponse(status=405)


@admin_required
def resend_invitation(request, pk):
    """Resend invitation to a teacher."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    teacher = get_object_or_404(Teacher, pk=pk)

    if teacher.user:
        messages.warning(request, f"{teacher.full_name} already has an account.")
        response = HttpResponse(status=204)
        response['HX-Refresh'] = 'true'
        return response

    # Get or create new invitation
    email = teacher.email
    if not email:
        messages.error(request, f"No email address for {teacher.full_name}.")
        response = HttpResponse(status=204)
        response['HX-Refresh'] = 'true'
        return response

    # Create new invitation (cancels existing pending ones)
    invitation = TeacherInvitation.create_for_teacher(
        teacher=teacher,
        email=email,
        created_by=request.user
    )

    # Send invitation email
    email_sent = send_invitation_email(invitation, request)

    if email_sent:
        messages.success(request, f"Invitation resent to {teacher.full_name}.")
    else:
        accept_url = request.build_absolute_uri(f'/teachers/invite/{invitation.token}/')
        messages.warning(
            request,
            f"Invitation created but email failed. Share this link: {accept_url}"
        )

    response = HttpResponse(status=204)
    response['HX-Refresh'] = 'true'
    return response


@admin_required
def cancel_invitation(request, pk):
    """Cancel a pending invitation."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    teacher = get_object_or_404(Teacher, pk=pk)

    # Cancel all pending invitations
    cancelled = TeacherInvitation.objects.filter(
        teacher=teacher,
        status=TeacherInvitation.Status.PENDING
    ).update(status=TeacherInvitation.Status.CANCELLED)

    if cancelled:
        messages.success(request, f"Invitation for {teacher.full_name} cancelled.")
    else:
        messages.info(request, "No pending invitation to cancel.")

    response = HttpResponse(status=204)
    response['HX-Refresh'] = 'true'
    return response


def accept_invitation(request, token):
    """
    Accept an invitation and set password.
    This view is accessible without authentication.
    """
    invitation = TeacherInvitation.get_by_token(token)

    if not invitation:
        return render(request, 'teachers/invitation_invalid.html', {
            'reason': 'expired_or_invalid'
        })

    teacher = invitation.teacher

    # Check if teacher already has an account (race condition check)
    if teacher.user:
        return render(request, 'teachers/invitation_invalid.html', {
            'reason': 'already_has_account',
            'teacher': teacher,
        })

    if request.method == 'GET':
        return render(request, 'teachers/accept_invitation.html', {
            'invitation': invitation,
            'teacher': teacher,
        })

    if request.method == 'POST':
        password = request.POST.get('password', '')
        password_confirm = request.POST.get('password_confirm', '')

        errors = []

        # Validate password
        if len(password) < 8:
            errors.append("Password must be at least 8 characters long.")
        if password != password_confirm:
            errors.append("Passwords do not match.")
        if password.lower() == teacher.email.lower() if teacher.email else False:
            errors.append("Password cannot be your email address.")

        if errors:
            return render(request, 'teachers/accept_invitation.html', {
                'invitation': invitation,
                'teacher': teacher,
                'errors': errors,
            })

        # Create user account
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    email=invitation.email,
                    password=password,
                    first_name=teacher.first_name,
                    last_name=teacher.last_name,
                    is_teacher=True,
                    must_change_password=False,  # They just set it!
                )

                # Link to teacher
                teacher.user = user
                teacher.save(update_fields=['user'])

                # Also update teacher email if different
                if teacher.email != invitation.email:
                    teacher.email = invitation.email
                    teacher.save(update_fields=['email'])

                # Mark invitation as accepted
                invitation.mark_accepted()

        except IntegrityError:
            return render(request, 'teachers/accept_invitation.html', {
                'invitation': invitation,
                'teacher': teacher,
                'errors': [f"An account with email '{invitation.email}' already exists."],
            })

        # Success - redirect to login
        messages.success(
            request,
            "Your account has been created successfully! Please log in."
        )
        return redirect('accounts:login')

    return HttpResponse(status=405)
