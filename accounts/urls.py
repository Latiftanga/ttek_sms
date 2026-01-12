from django.urls import path
from django.contrib.auth.views import LogoutView
from .views import CustomLoginView, ForcePasswordChangeView

app_name = 'accounts'

urlpatterns = [
    path('login/', CustomLoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(next_page='accounts:login'), name='logout'),
    path('password/change/', ForcePasswordChangeView.as_view(), name='password_change'),
]