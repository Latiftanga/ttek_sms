from django.urls import path
from . import views

app_name = 'academics'

urlpatterns = [
    # Main page
    path('', views.index, name='index'),

    # Programme routes (SHS only)
    path('programmes/create/', views.programme_create, name='programme_create'),
    path('programmes/<int:pk>/edit/', views.programme_edit, name='programme_edit'),
    path('programmes/<int:pk>/delete/', views.programme_delete, name='programme_delete'),

    # Class routes
    path('classes/create/', views.class_create, name='class_create'),
    path('classes/<int:pk>/edit/', views.class_edit, name='class_edit'),
    path('classes/<int:pk>/delete/', views.class_delete, name='class_delete'),

    # Subject routes
    path('subjects/create/', views.subject_create, name='subject_create'),
    path('subjects/<int:pk>/edit/', views.subject_edit, name='subject_edit'),
    path('subjects/<int:pk>/delete/', views.subject_delete, name='subject_delete'),
]
