from django.urls import path
from . import views

app_name = 'communications'

urlpatterns = [
    path('', views.index, name='index'),
    path('send/', views.send_single, name='send_single'),
    path('send/class/', views.send_to_class, name='send_to_class'),
    path('notify-absent/', views.notify_absent, name='notify_absent'),
    path('history/', views.message_history, name='history'),
    path('templates/', views.templates_list, name='templates'),
    path('templates/create/', views.template_create, name='template_create'),
    path('templates/<int:pk>/delete/', views.template_delete, name='template_delete'),
]
