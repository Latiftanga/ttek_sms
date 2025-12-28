from django.urls import path
from django.contrib.auth.views import LoginView, LogoutView
from .forms import LoginForm
from .views import ForcePasswordChangeView

app_name = 'accounts'

urlpatterns = [
    path('login/', LoginView.as_view(
        template_name='accounts/login.html',
        authentication_form=LoginForm, redirect_authenticated_user=True
    ), name='login'),
    path('logout/', LogoutView.as_view(next_page='accounts:login'), name='logout'),
    path('password/change/', ForcePasswordChangeView.as_view(), name='password_change'),
]