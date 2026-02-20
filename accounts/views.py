import logging
from PIL import Image

from django.shortcuts import render, redirect
from django.contrib.auth.views import (
    LoginView, PasswordChangeView,
    PasswordResetView, PasswordResetDoneView,
    PasswordResetConfirmView, PasswordResetCompleteView,
)
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import DatabaseError
from django.conf import settings
from django.urls import reverse_lazy
from .forms import LoginForm, ProfilePhoneForm

logger = logging.getLogger(__name__)

ALLOWED_IMAGE_TYPES = {'image/jpeg', 'image/png', 'image/webp'}
MAX_PHOTO_SIZE = 5 * 1024 * 1024  # 5MB


def validate_photo(photo):
    """Validate uploaded photo file type and size."""
    if photo.size > MAX_PHOTO_SIZE:
        raise ValidationError('Photo must be less than 5MB.')
    if photo.content_type not in ALLOWED_IMAGE_TYPES:
        raise ValidationError('Photo must be a JPEG, PNG, or WebP image.')
    # Verify it's actually an image by opening with PIL
    try:
        img = Image.open(photo)
        img.verify()
        photo.seek(0)  # Reset file pointer after verify
    except Exception:
        raise ValidationError('Invalid image file.')


def axes_lockout_response(request, credentials, *args, **kwargs):
    """
    Custom lockout response for django-axes.
    Returns a user-friendly error page when account is locked.
    """
    return render(
        request,
        'accounts/lockout.html',
        {
            'cooloff_time': int(settings.AXES_COOLOFF_TIME * 60),
        },
        status=403
    )


# Profile setup wizard steps for different user types
# Personal info is already filled by admin, so skip to optional photo/preferences
TEACHER_STEPS = ['welcome', 'photo', 'complete']
PARENT_STEPS = ['welcome', 'preferences', 'complete']


def get_wizard_steps(user):
    """Get the wizard steps based on user type."""
    if getattr(user, 'is_teacher', False):
        return TEACHER_STEPS
    elif getattr(user, 'is_parent', False):
        return PARENT_STEPS
    return TEACHER_STEPS  # Default fallback


@login_required
def profile_setup_wizard(request):
    """Main profile setup wizard view - redirects to current step."""
    user = request.user

    # If profile setup is already completed, redirect to dashboard
    if getattr(user, 'profile_setup_completed', True):
        return redirect('core:index')

    # Get current step from session or start at welcome
    current_step = request.session.get('profile_setup_step', 'welcome')
    steps = get_wizard_steps(user)

    # Validate current step
    if current_step not in steps:
        current_step = 'welcome'
        request.session['profile_setup_step'] = current_step

    return redirect('accounts:profile_setup_step', step=current_step)


@login_required
def profile_setup_step(request, step):
    """Handle individual wizard steps."""
    user = request.user

    # If profile setup is already completed, redirect to dashboard
    if getattr(user, 'profile_setup_completed', True):
        return redirect('core:index')

    steps = get_wizard_steps(user)

    # Validate step
    if step not in steps:
        return redirect('accounts:profile_setup')

    current_index = steps.index(step)
    progress = int((current_index / (len(steps) - 1)) * 100) if len(steps) > 1 else 0

    # Get the actual profile for pre-filling forms
    # Use try/except because OneToOneField raises ObjectDoesNotExist, not AttributeError
    teacher_profile = None
    guardian_profile = None

    if getattr(user, 'is_teacher', False):
        try:
            teacher_profile = user.teacher_profile
        except ObjectDoesNotExist:
            pass

    if getattr(user, 'is_parent', False):
        try:
            guardian_profile = user.guardian_profile
        except ObjectDoesNotExist:
            pass

    context = {
        'step': step,
        'steps': steps,
        'current_index': current_index,
        'progress': progress,
        'is_teacher': getattr(user, 'is_teacher', False),
        'is_parent': getattr(user, 'is_parent', False),
        'guardian': guardian_profile,
        'teacher': teacher_profile,
        'profile': teacher_profile or guardian_profile,
    }

    if request.method == 'POST':
        return handle_step_post(request, step, steps, context)

    # Store current step in session
    request.session['profile_setup_step'] = step

    return render(request, f'accounts/profile_setup/{step}.html', context)


def handle_step_post(request, step, steps, context):
    """Handle POST requests for wizard steps."""
    user = request.user
    current_index = steps.index(step)

    if step == 'welcome':
        # Just advance to next step
        next_step = steps[current_index + 1]
        request.session['profile_setup_step'] = next_step
        return redirect('accounts:profile_setup_step', step=next_step)

    elif step == 'personal':
        # Validate phone and address
        form = ProfilePhoneForm(request.POST)
        if not form.is_valid():
            for field_errors in form.errors.values():
                for error in field_errors:
                    messages.error(request, error)
            return redirect('accounts:profile_setup_step', step=step)

        phone = form.cleaned_data['phone']
        address = form.cleaned_data['address']

        # For teachers, save to teacher_profile
        if getattr(user, 'is_teacher', False):
            try:
                teacher = user.teacher_profile
                if phone:
                    teacher.phone_number = phone
                if address:
                    teacher.address = address
                dob = request.POST.get('date_of_birth', '').strip()
                if dob:
                    from datetime import datetime
                    try:
                        teacher.date_of_birth = datetime.strptime(
                            dob, '%Y-%m-%d').date()
                    except ValueError:
                        messages.warning(
                            request,
                            'Invalid date format. Date of birth was not saved.'
                        )
                teacher.save()
                messages.success(request, 'Personal information saved.')
            except ObjectDoesNotExist:
                messages.error(request, 'Teacher profile not found.')
            except DatabaseError:
                logger.exception('Failed to save teacher personal info')
                messages.error(request, 'Failed to save personal information.')

        # For parents, save to guardian_profile
        elif getattr(user, 'is_parent', False):
            try:
                guardian = user.guardian_profile
                if phone:
                    guardian.phone_number = phone
                if address:
                    guardian.address = address
                occupation = request.POST.get('occupation', '').strip()[:100]
                if occupation:
                    guardian.occupation = occupation
                guardian.save()
                messages.success(request, 'Personal information saved.')
            except ObjectDoesNotExist:
                messages.error(request, 'Guardian profile not found.')
            except DatabaseError:
                logger.exception('Failed to save guardian personal info')
                messages.error(request, 'Failed to save personal information.')

        next_step = steps[current_index + 1]
        request.session['profile_setup_step'] = next_step
        return redirect('accounts:profile_setup_step', step=next_step)

    elif step == 'photo':
        # Handle photo upload (teachers only) - save to teacher_profile
        if 'photo' in request.FILES:
            photo = request.FILES['photo']
            try:
                validate_photo(photo)
                teacher = user.teacher_profile
                teacher.photo = photo
                teacher.save()
                messages.success(request, 'Profile photo uploaded.')
            except ValidationError as e:
                messages.error(request, e.message)
            except ObjectDoesNotExist:
                messages.error(request, 'Teacher profile not found.')
            except DatabaseError:
                logger.exception('Failed to upload photo')
                messages.error(request, 'Failed to upload photo.')

        next_step = steps[current_index + 1]
        request.session['profile_setup_step'] = next_step
        return redirect('accounts:profile_setup_step', step=next_step)

    elif step == 'preferences':
        # Preferences step — just advance to next step
        next_step = steps[current_index + 1]
        request.session['profile_setup_step'] = next_step
        return redirect('accounts:profile_setup_step', step=next_step)

    elif step == 'complete':
        # Mark profile setup as complete
        user.profile_setup_completed = True
        user.save(update_fields=['profile_setup_completed'])

        # Clear session data
        if 'profile_setup_step' in request.session:
            del request.session['profile_setup_step']

        logger.info('Profile setup completed for user %s', user.email)
        messages.success(request, 'Profile setup completed! Welcome to the platform.')

        # Redirect based on user type
        if getattr(user, 'is_teacher', False):
            return redirect('teachers:index')
        elif getattr(user, 'is_parent', False):
            return redirect('students:guardian_dashboard')
        return redirect('core:index')

    return redirect('accounts:profile_setup')


class CustomLoginView(LoginView):
    """
    Custom login view that handles the 'remember me' checkbox.
    """
    template_name = 'accounts/login.html'
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        remember = self.request.POST.get('remember')
        if not remember:
            # Session expires when browser closes
            self.request.session.set_expiry(0)
        else:
            # Session expires in 7 days (604800 seconds)
            self.request.session.set_expiry(604800)
        return super().form_valid(form)


class ForcePasswordChangeView(PasswordChangeView):
    """
    Password change view that clears the must_change_password flag.

    For forced password changes, uses standalone template (no navigation).
    For voluntary changes, uses modal with HTMX support.
    """
    template_name = 'accounts/password_change.html'
    success_url = reverse_lazy('core:index')

    def render_to_response(self, context, **response_kwargs):
        # For voluntary changes via HTMX, return modal content
        if not context.get('is_forced') and self.request.htmx:
            return render(self.request, 'accounts/partials/password_change_modal.html', context)
        return super().render_to_response(context, **response_kwargs)

    def form_valid(self, form):
        import json
        from django.http import HttpResponse

        # Save the new password
        form.save()

        # Clear the must_change_password flag
        user = self.request.user
        if hasattr(user, 'must_change_password') and user.must_change_password:
            user.must_change_password = False
            user.save(update_fields=['must_change_password'])

        # For HTMX requests, close modal and show toast
        if self.request.htmx:
            response = HttpResponse(status=204)
            response['HX-Trigger'] = json.dumps({
                'closeModal': True,
                'showToast': {'message': 'Password changed successfully', 'type': 'success'}
            })
            return response

        # For regular requests, redirect with message
        logger.info('Password changed for user %s', self.request.user.email)
        messages.success(self.request, 'Your password has been changed successfully.')
        return redirect(self.success_url)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_forced'] = getattr(self.request.user, 'must_change_password', False)
        return context


class SchoolPasswordResetView(PasswordResetView):
    """Password reset request with school branding."""
    template_name = 'accounts/password_reset.html'
    email_template_name = 'accounts/password_reset_email.html'
    subject_template_name = 'accounts/password_reset_subject.txt'
    success_url = reverse_lazy('accounts:password_reset_done')


class SchoolPasswordResetDoneView(PasswordResetDoneView):
    """Password reset email sent confirmation with school branding."""
    template_name = 'accounts/password_reset_done.html'


class SchoolPasswordResetConfirmView(PasswordResetConfirmView):
    """Set new password form with school branding."""
    template_name = 'accounts/password_reset_confirm.html'
    success_url = reverse_lazy('accounts:password_reset_complete')


class SchoolPasswordResetCompleteView(PasswordResetCompleteView):
    """Password reset success page with school branding."""
    template_name = 'accounts/password_reset_complete.html'
