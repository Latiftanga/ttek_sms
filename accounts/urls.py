from django.urls import path
from django.contrib.auth.views import LogoutView
from .views import (
    CustomLoginView, ForcePasswordChangeView,
    profile_setup_wizard, profile_setup_step
)

app_name = 'accounts'

urlpatterns = [
    path('login/', CustomLoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(next_page='accounts:login'), name='logout'),
    path('password/change/', ForcePasswordChangeView.as_view(), name='password_change'),
    # Profile setup wizard
    path('profile-setup/', profile_setup_wizard, name='profile_setup'),
    path('profile-setup/<str:step>/', profile_setup_step, name='profile_setup_step'),
]