import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.db import IntegrityError, transaction
from django.contrib import messages
from django.contrib.auth import login
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from accounts.models import User
from core.email_backend import get_from_email
from students.models import Guardian, GuardianInvitation
from .utils import admin_required

logger = logging.getLogger(__name__)


def send_invitation_email(invitation, request):
    """Send invitation email to guardian."""
    guardian = invitation.guardian

    # Build the accept URL
    accept_url = request.build_absolute_uri(f'/students/guardians/invite/{invitation.token}/')

    # Email context
    context = {
        'guardian': guardian,
        'invitation': invitation,
        'accept_url': accept_url,
        'expires_hours': 72,
    }

    # Render email content
    html_message = render_to_string('students/emails/guardian_invitation_email.html', context)
    plain_message = strip_tags(html_message)

    subject = "You're Invited to Join the Guardian Portal"

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
        logger.error(f"Failed to send guardian invitation email: {e}")
        return False
    except OSError as e:
        logger.error(f"Network error sending guardian invitation: {e}")
        return False


@admin_required
def guardian_detail(request, pk):
    """Guardian detail page showing wards and account status."""
    guardian = get_object_or_404(
        Guardian.objects.prefetch_related(
            'guardian_students__student__current_class',
            'invitations'
        ).select_related('user'),
        pk=pk
    )

    # Get wards with relationship info
    wards = guardian.guardian_students.select_related(
        'student__current_class'
    ).order_by('-is_primary', 'student__last_name')

    # Get pending invitation if any
    pending_invitation = guardian.invitations.filter(
        status=GuardianInvitation.Status.PENDING
    ).first()

    context = {
        'guardian': guardian,
        'wards': wards,
        'pending_invitation': pending_invitation,
        # Navigation
        'breadcrumbs': [
            {'label': 'Home', 'url': '/', 'icon': 'fa-solid fa-home'},
            {'label': 'Guardians', 'url': '/students/guardians/'},
            {'label': guardian.full_name},
        ],
        'back_url': '/students/guardians/',
    }

    if request.htmx:
        return render(request, 'students/partials/guardian_detail_content.html', context)
    return render(request, 'students/guardian_detail.html', context)


@admin_required
def send_invitation(request, pk):
    """Send an invitation to a guardian to create their account."""
    guardian = get_object_or_404(Guardian, pk=pk)

    # If guardian already has an account, redirect
    if guardian.user:
        messages.warning(request, f"{guardian.full_name} already has an account.")
        response = HttpResponse(status=204)
        response['HX-Refresh'] = 'true'
        return response

    if request.method == 'GET':
        # Check for existing pending invitation
        pending_invitation = GuardianInvitation.objects.filter(
            guardian=guardian,
            status=GuardianInvitation.Status.PENDING
        ).first()

        return render(request, 'students/partials/modal_send_guardian_invitation.html', {
            'guardian': guardian,
            'pending_invitation': pending_invitation,
        })

    if request.method == 'POST':
        email = request.POST.get('email', '').strip()

        # Use guardian's email if not provided
        if not email:
            email = guardian.email

        if not email:
            return render(request, 'students/partials/modal_send_guardian_invitation.html', {
                'guardian': guardian,
                'error': 'Email address is required. Please provide an email.',
            })

        # Check if email already exists as a user
        if User.objects.filter(email=email).exists():
            return render(request, 'students/partials/modal_send_guardian_invitation.html', {
                'guardian': guardian,
                'error': f"An account with email '{email}' already exists.",
            })

        # Create invitation
        invitation = GuardianInvitation.create_for_guardian(
            guardian=guardian,
            email=email,
            created_by=request.user
        )

        # Update guardian's email if it was empty
        if not guardian.email:
            guardian.email = email
            guardian.save(update_fields=['email'])

        # Send invitation email
        email_sent = send_invitation_email(invitation, request)

        if email_sent:
            messages.success(
                request,
                f"Invitation sent to {guardian.full_name} at {email}."
            )
        else:
            # Show the link if email failed
            accept_url = request.build_absolute_uri(f'/students/guardians/invite/{invitation.token}/')
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
    """Resend invitation to a guardian."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    guardian = get_object_or_404(Guardian, pk=pk)

    if guardian.user:
        messages.warning(request, f"{guardian.full_name} already has an account.")
        response = HttpResponse(status=204)
        response['HX-Refresh'] = 'true'
        return response

    # Get or create new invitation
    email = guardian.email
    if not email:
        messages.error(request, f"No email address for {guardian.full_name}.")
        response = HttpResponse(status=204)
        response['HX-Refresh'] = 'true'
        return response

    # Create new invitation (cancels existing pending ones)
    invitation = GuardianInvitation.create_for_guardian(
        guardian=guardian,
        email=email,
        created_by=request.user
    )

    # Send invitation email
    email_sent = send_invitation_email(invitation, request)

    if email_sent:
        messages.success(request, f"Invitation resent to {guardian.full_name}.")
    else:
        accept_url = request.build_absolute_uri(f'/students/guardians/invite/{invitation.token}/')
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

    guardian = get_object_or_404(Guardian, pk=pk)

    # Cancel all pending invitations
    cancelled = GuardianInvitation.objects.filter(
        guardian=guardian,
        status=GuardianInvitation.Status.PENDING
    ).update(status=GuardianInvitation.Status.CANCELLED)

    if cancelled:
        messages.success(request, f"Invitation for {guardian.full_name} cancelled.")
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
    invitation = GuardianInvitation.get_by_token(token)

    if not invitation:
        return render(request, 'students/guardian_invitation_invalid.html', {
            'reason': 'expired_or_invalid'
        })

    guardian = invitation.guardian

    # Check if guardian already has an account (race condition check)
    if guardian.user:
        return render(request, 'students/guardian_invitation_invalid.html', {
            'reason': 'already_has_account',
            'guardian': guardian,
        })

    if request.method == 'GET':
        return render(request, 'students/guardian_accept_invitation.html', {
            'invitation': invitation,
            'guardian': guardian,
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
        if guardian.email and password.lower() == guardian.email.lower():
            errors.append("Password cannot be your email address.")

        if errors:
            return render(request, 'students/guardian_accept_invitation.html', {
                'invitation': invitation,
                'guardian': guardian,
                'errors': errors,
            })

        # Create user account
        try:
            with transaction.atomic():
                # Split full name for first/last name
                name_parts = guardian.full_name.split(' ', 1)
                first_name = name_parts[0]
                last_name = name_parts[1] if len(name_parts) > 1 else ''

                user = User.objects.create_user(
                    email=invitation.email,
                    password=password,
                    first_name=first_name,
                    last_name=last_name,
                    is_parent=True,
                    must_change_password=False,  # They just set it!
                    profile_setup_completed=False,
                )

                # Link to guardian
                guardian.user = user
                guardian.save(update_fields=['user'])

                # Also update guardian email if different
                if guardian.email != invitation.email:
                    guardian.email = invitation.email
                    guardian.save(update_fields=['email'])

                # Mark invitation as accepted
                invitation.mark_accepted()

        except IntegrityError:
            return render(request, 'students/guardian_accept_invitation.html', {
                'invitation': invitation,
                'guardian': guardian,
                'errors': [f"An account with email '{invitation.email}' already exists."],
            })

        # Auto-login and redirect to profile setup
        login(request, user)
        messages.success(
            request,
            "Your account has been created successfully! Let's complete your profile."
        )
        return redirect('accounts:profile_setup')

    return HttpResponse(status=405)


@admin_required
def deactivate_account(request, pk):
    """Deactivate a guardian's user account."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    guardian = get_object_or_404(Guardian, pk=pk)

    if guardian.user:
        user = guardian.user
        user.is_active = False
        user.save(update_fields=['is_active'])
        messages.success(request, f"Account for {guardian.full_name} has been deactivated.")

    response = HttpResponse(status=204)
    response['HX-Refresh'] = 'true'
    return response


@admin_required
def activate_account(request, pk):
    """Reactivate a guardian's user account."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    guardian = get_object_or_404(Guardian, pk=pk)

    if guardian.user:
        user = guardian.user
        user.is_active = True
        user.save(update_fields=['is_active'])
        messages.success(request, f"Account for {guardian.full_name} has been reactivated.")

    response = HttpResponse(status=204)
    response['HX-Refresh'] = 'true'
    return response
