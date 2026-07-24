import json
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
from gradebook.utils import get_school_context
from students.models import Guardian, GuardianInvitation
from .utils import admin_required

logger = logging.getLogger(__name__)


def send_invitation_email(invitation, request):
    """Send invitation email to guardian."""
    guardian = invitation.guardian

    # Build the accept URL
    accept_url = request.build_absolute_uri(f'/students/guardians/invite/{invitation.token}/')

    # Get school context for branding
    school_ctx = get_school_context()
    school = school_ctx.get('school')
    school_name = school.display_name or school.name if school else 'School'

    # Email context
    context = {
        'guardian': guardian,
        'invitation': invitation,
        'accept_url': accept_url,
        'expires_hours': 72,
        **school_ctx,
    }

    # Render email content
    html_message = render_to_string('students/emails/guardian_invitation_email.html', context)
    plain_message = strip_tags(html_message)

    subject = f"You're Invited to Join {school_name} Guardian Portal"

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


def _guardian_detail_context(guardian):
    """Build the context guardian_detail_content.html needs - shared by the
    detail view itself and by every action below that redraws it."""
    wards = guardian.guardian_students.select_related(
        'student__current_class'
    ).order_by('-is_primary', 'student__last_name')

    pending_invitation = guardian.invitations.filter(
        status=GuardianInvitation.Status.PENDING
    ).first()

    return {
        'guardian': guardian,
        'wards': wards,
        'pending_invitation': pending_invitation,
        'breadcrumbs': [
            {'label': 'Home', 'url': '/', 'icon': 'fa-solid fa-home'},
            {'label': 'Guardians', 'url': '/students/guardians/'},
            {'label': guardian.full_name},
        ],
        'back_url': '/students/guardians/',
    }


def _render_guardian_detail(request, guardian, toast_message=None, toast_type='success', close_modal=False):
    """
    Re-render the guardian detail partial with a toast, for account-action
    views below. These used to respond with HX-Refresh (a full page reload
    of guardian_detail.html, which extends core/base.html - a template that
    never renders Django's messages framework output), so the
    messages.success()/warning() call for the outcome was invisible. This
    reloads the same content via HTMX instead and attaches the toast via
    HX-Trigger, the mechanism that actually works in this app's flows.

    HX-Retarget/HX-Reswap redirect the swap to #main-content regardless of
    which element's hx-target actually issued the request - some of these
    actions come from a plain form on the page (no explicit hx-target, so
    htmx would otherwise try to swap this whole page into that one small
    form), others from the send-invitation modal (close_modal=True closes
    it via the same global closeModal event this app already uses).
    """
    guardian.refresh_from_db()
    response = render(
        request, 'students/partials/guardian_detail_content.html',
        _guardian_detail_context(guardian)
    )
    response['HX-Retarget'] = '#main-content'
    response['HX-Reswap'] = 'innerHTML'
    triggers = {}
    if toast_message:
        triggers['showToast'] = {'message': toast_message, 'type': toast_type}
    if close_modal:
        triggers['closeModal'] = True
    if triggers:
        response['HX-Trigger'] = json.dumps(triggers)
    return response


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

    context = _guardian_detail_context(guardian)

    if request.htmx:
        return render(request, 'students/partials/guardian_detail_content.html', context)
    return render(request, 'students/guardian_detail.html', context)


@admin_required
def send_invitation(request, pk):
    """Send an invitation to a guardian to create their account."""
    guardian = get_object_or_404(Guardian, pk=pk)

    # If guardian already has an account, redirect
    if guardian.user:
        return _render_guardian_detail(
            request, guardian,
            f"{guardian.full_name} already has an account.", 'warning',
            close_modal=True
        )

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
            return _render_guardian_detail(
                request, guardian,
                f"Invitation sent to {guardian.full_name} at {email}.", 'success',
                close_modal=True
            )

        # Email failed - keep the modal open so the admin can copy the
        # link directly, rather than closing it and losing the URL in a
        # transient toast.
        accept_url = request.build_absolute_uri(f'/students/guardians/invite/{invitation.token}/')
        return render(request, 'students/partials/modal_send_guardian_invitation.html', {
            'guardian': guardian,
            'share_link': accept_url,
        })

    return HttpResponse(status=405)


@admin_required
def resend_invitation(request, pk):
    """Resend invitation to a guardian."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    guardian = get_object_or_404(Guardian, pk=pk)

    if guardian.user:
        return _render_guardian_detail(
            request, guardian, f"{guardian.full_name} already has an account.", 'warning'
        )

    # Get or create new invitation
    email = guardian.email
    if not email:
        return _render_guardian_detail(
            request, guardian, f"No email address for {guardian.full_name}.", 'error'
        )

    # Create new invitation (cancels existing pending ones)
    invitation = GuardianInvitation.create_for_guardian(
        guardian=guardian,
        email=email,
        created_by=request.user
    )

    # Send invitation email
    email_sent = send_invitation_email(invitation, request)

    if email_sent:
        return _render_guardian_detail(
            request, guardian, f"Invitation resent to {guardian.full_name}.", 'success'
        )

    accept_url = request.build_absolute_uri(f'/students/guardians/invite/{invitation.token}/')
    return _render_guardian_detail(
        request, guardian,
        f"Invitation created but email failed. Share this link: {accept_url}", 'warning'
    )


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
        return _render_guardian_detail(
            request, guardian, f"Invitation for {guardian.full_name} cancelled.", 'success'
        )
    return _render_guardian_detail(
        request, guardian, "No pending invitation to cancel.", 'info'
    )


def accept_invitation(request, token):
    """
    Accept an invitation and set password.
    This view is accessible without authentication.
    """
    invitation = GuardianInvitation.get_by_token(token)
    school_ctx = get_school_context()

    if not invitation:
        return render(request, 'students/guardian_invitation_invalid.html', {
            'reason': 'expired_or_invalid',
            **school_ctx,
        })

    guardian = invitation.guardian

    # Check if guardian already has an account (race condition check)
    if guardian.user:
        return render(request, 'students/guardian_invitation_invalid.html', {
            'reason': 'already_has_account',
            'guardian': guardian,
            **school_ctx,
        })

    if request.method == 'GET':
        return render(request, 'students/guardian_accept_invitation.html', {
            'invitation': invitation,
            'guardian': guardian,
            **school_ctx,
        })

    if request.method == 'POST':
        password = request.POST.get('password', '')
        password_confirm = request.POST.get('password_confirm', '')

        errors = []

        # Validate password
        if password != password_confirm:
            errors.append("Passwords do not match.")
        else:
            from django.contrib.auth.password_validation import validate_password
            from django.core.exceptions import ValidationError as DjangoValidationError
            try:
                validate_password(password)
            except DjangoValidationError as e:
                errors.extend(e.messages)

        if errors:
            return render(request, 'students/guardian_accept_invitation.html', {
                'invitation': invitation,
                'guardian': guardian,
                'errors': errors,
                **school_ctx,
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
                **school_ctx,
            })

        # Auto-login and redirect to profile setup
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
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
        return _render_guardian_detail(
            request, guardian, f"Account for {guardian.full_name} has been deactivated.", 'success'
        )
    return _render_guardian_detail(request, guardian)


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
        return _render_guardian_detail(
            request, guardian, f"Account for {guardian.full_name} has been reactivated.", 'success'
        )
    return _render_guardian_detail(request, guardian)
