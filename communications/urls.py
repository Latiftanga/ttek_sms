from django.urls import path
from . import views

app_name = 'communications'

urlpatterns = [
    path('', views.index, name='index'),
    path('send/class/recipients/', views.class_recipients, name='class_recipients'),
    path('send/staff/recipients/', views.staff_recipients, name='staff_recipients'),
    path('notify-absent/', views.notify_absent, name='notify_absent'),
    path('history/', views.message_history, name='history'),
    path('history/export/', views.message_history_export, name='history_export'),
    path('templates/', views.templates_list, name='templates'),
    path('templates/create/', views.template_create, name='template_create'),
    path('templates/<int:pk>/edit/', views.template_edit, name='template_edit'),
    path('templates/<int:pk>/delete/', views.template_delete, name='template_delete'),
    # Announcements
    path('announcements/', views.announcements_list, name='announcements'),
    path('announcements/create/', views.announcement_create, name='announcement_create'),
    path('announcements/recipients/', views.announcement_recipients, name='announcement_recipients'),
    path('announcements/search/', views.announcement_search, name='announcement_search'),
    path('announcements/feed/', views.announcements_feed, name='announcements_feed'),
    path('announcements/<uuid:pk>/', views.announcement_detail, name='announcement_detail'),
]
