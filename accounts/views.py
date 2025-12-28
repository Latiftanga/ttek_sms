from django.shortcuts import render, redirect
from django.contrib.auth.views import PasswordChangeView
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse_lazy


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
