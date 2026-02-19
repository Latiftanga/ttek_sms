from django.urls import path
from django.contrib.auth.views import LogoutView
from .views import (
    CustomLoginView, ForcePasswordChangeView,
    SchoolPasswordResetView, SchoolPasswordResetDoneView,
    SchoolPasswordResetConfirmView, SchoolPasswordResetCompleteView,
    profile_setup_wizard, profile_setup_step
)

app_name = 'accounts'

urlpatterns = [
    path('login/', CustomLoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(next_page='/login/'), name='logout'),
    path('password/change/', ForcePasswordChangeView.as_view(), name='password_change'),
    # Password reset flow
    path('password/reset/', SchoolPasswordResetView.as_view(), name='password_reset'),
    path('password/reset/done/', SchoolPasswordResetDoneView.as_view(), name='password_reset_done'),
    path('password/reset/<uidb64>/<token>/', SchoolPasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('password/reset/complete/', SchoolPasswordResetCompleteView.as_view(), name='password_reset_complete'),
    # Profile setup wizard
    path('profile-setup/', profile_setup_wizard, name='profile_setup'),
    path('profile-setup/<str:step>/', profile_setup_step, name='profile_setup_step'),
]
