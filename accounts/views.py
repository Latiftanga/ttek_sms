from django.shortcuts import render, redirect
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse_lazy, reverse
from django.http import HttpResponseRedirect, HttpResponse
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
TEACHER_STEPS = ['welcome', 'personal', 'photo', 'complete']
PARENT_STEPS = ['welcome', 'personal', 'preferences', 'complete']


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

    context = {
        'step': step,
        'steps': steps,
        'current_index': current_index,
        'progress': progress,
        'is_teacher': getattr(user, 'is_teacher', False),
        'is_parent': getattr(user, 'is_parent', False),
        'guardian': getattr(user, 'guardian_profile', None),
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
        # Save personal info
        phone = request.POST.get('phone', '').strip()
        address = request.POST.get('address', '').strip()

        # Update user profile fields if they exist
        if hasattr(user, 'phone'):
            user.phone = phone
        if hasattr(user, 'address'):
            user.address = address

        # For teachers, also get date of birth
        if getattr(user, 'is_teacher', False):
            dob = request.POST.get('date_of_birth', '').strip()
            if hasattr(user, 'date_of_birth') and dob:
                from datetime import datetime
                try:
                    user.date_of_birth = datetime.strptime(dob, '%Y-%m-%d').date()
                except ValueError:
                    pass

        # For parents, also get occupation
        if getattr(user, 'is_parent', False):
            occupation = request.POST.get('occupation', '').strip()
            if hasattr(user, 'occupation'):
                user.occupation = occupation

        try:
            user.save()
            messages.success(request, 'Personal information saved.')
        except Exception:
            messages.error(request, 'Failed to save personal information.')

        next_step = steps[current_index + 1]
        request.session['profile_setup_step'] = next_step
        return redirect('accounts:profile_setup_step', step=next_step)

    elif step == 'photo':
        # Handle photo upload (teachers only)
        if 'photo' in request.FILES:
            photo = request.FILES['photo']
            if hasattr(user, 'photo'):
                user.photo = photo
                try:
                    user.save()
                    messages.success(request, 'Profile photo uploaded.')
                except Exception:
                    messages.error(request, 'Failed to upload photo.')

        next_step = steps[current_index + 1]
        request.session['profile_setup_step'] = next_step
        return redirect('accounts:profile_setup_step', step=next_step)

    elif step == 'preferences':
        # Handle notification preferences (parents only)
        guardian = getattr(user, 'guardian_profile', None)
        if guardian:
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
    """
    template_name = 'accounts/password_change.html'
    success_url = reverse_lazy('core:index')

    def form_valid(self, form):
        response = super().form_valid(form)

        # Clear the must_change_password flag
        user = self.request.user
        if hasattr(user, 'must_change_password') and user.must_change_password:
            user.must_change_password = False
            user.save(update_fields=['must_change_password'])

        messages.success(self.request, 'Your password has been changed successfully.')
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_forced'] = getattr(self.request.user, 'must_change_password', False)
        return context
