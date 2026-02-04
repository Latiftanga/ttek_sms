from django.shortcuts import render, redirect
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.urls import reverse_lazy
from .forms import LoginForm


def axes_lockout_response(request, credentials, *args, **kwargs):
    """
    Custom lockout response for django-axes.
    Returns a user-friendly error page when account is locked.
    """
    return render(
        request,
        'accounts/lockout.html',
        {
            'cooloff_time': 15,  # minutes - matches AXES_COOLOFF_TIME (0.25 hours)
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
        except Exception:
            pass

    if getattr(user, 'is_parent', False):
        try:
            guardian_profile = user.guardian_profile
        except Exception:
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
        # Save personal info to the correct profile model
        phone = request.POST.get('phone', '').strip()
        address = request.POST.get('address', '').strip()

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
                        teacher.date_of_birth = datetime.strptime(dob, '%Y-%m-%d').date()
                    except ValueError:
                        pass
                teacher.save()
                messages.success(request, 'Personal information saved.')
            except ObjectDoesNotExist:
                messages.error(request, 'Teacher profile not found.')
            except Exception:
                messages.error(request, 'Failed to save personal information.')

        # For parents, save to guardian_profile
        elif getattr(user, 'is_parent', False):
            try:
                guardian = user.guardian_profile
                if phone:
                    guardian.phone_number = phone
                if address:
                    guardian.address = address
                occupation = request.POST.get('occupation', '').strip()
                if occupation:
                    guardian.occupation = occupation
                guardian.save()
                messages.success(request, 'Personal information saved.')
            except ObjectDoesNotExist:
                messages.error(request, 'Guardian profile not found.')
            except Exception:
                messages.error(request, 'Failed to save personal information.')

        next_step = steps[current_index + 1]
        request.session['profile_setup_step'] = next_step
        return redirect('accounts:profile_setup_step', step=next_step)

    elif step == 'photo':
        # Handle photo upload (teachers only) - save to teacher_profile
        if 'photo' in request.FILES:
            photo = request.FILES['photo']
            try:
                teacher = user.teacher_profile
                teacher.photo = photo
                teacher.save()
                messages.success(request, 'Profile photo uploaded.')
            except ObjectDoesNotExist:
                messages.error(request, 'Teacher profile not found.')
            except Exception:
                messages.error(request, 'Failed to upload photo.')

        next_step = steps[current_index + 1]
        request.session['profile_setup_step'] = next_step
        return redirect('accounts:profile_setup_step', step=next_step)

    elif step == 'preferences':
        # Handle notification preferences (parents only)
        try:
            guardian = user.guardian_profile
            guardian.email_notifications = 'email_notifications' in request.POST
            guardian.sms_notifications = 'sms_notifications' in request.POST
            guardian.academic_alerts = 'academic_alerts' in request.POST
            guardian.attendance_alerts = 'attendance_alerts' in request.POST
            guardian.fee_alerts = 'fee_alerts' in request.POST
            guardian.announcement_alerts = 'announcement_alerts' in request.POST
            guardian.save(update_fields=[
                'email_notifications', 'sms_notifications', 'academic_alerts',
                'attendance_alerts', 'fee_alerts', 'announcement_alerts'
            ])
            messages.success(request, 'Notification preferences saved.')
        except ObjectDoesNotExist:
            messages.error(request, 'Guardian profile not found.')
        except Exception:
            messages.error(request, 'Failed to save preferences.')

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
            # Session expires in 2 weeks (1209600 seconds)
            self.request.session.set_expiry(1209600)
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
        if not context.get('is_forced') and self.request.headers.get('HX-Request'):
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
        if self.request.headers.get('HX-Request'):
            response = HttpResponse(status=204)
            response['HX-Trigger'] = json.dumps({
                'closeModal': True,
                'showToast': {'message': 'Password changed successfully', 'type': 'success'}
            })
            return response

        # For regular requests, redirect with message
        messages.success(self.request, 'Your password has been changed successfully.')
        return redirect(self.success_url)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_forced'] = getattr(self.request.user, 'must_change_password', False)
        return context
