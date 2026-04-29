from django.urls import path

from . import views

urlpatterns = [
    path('dashboard/', views.dashboard_summary, name='admin-dashboard-summary'),
    path('users/', views.users_list, name='admin-users-list'),
    path('users/<uuid:user_id>/edit/', views.user_edit, name='admin-user-edit'),
    path('users/<uuid:user_id>/remove/', views.user_remove, name='admin-user-remove'),
    path('scans/', views.scans_list, name='admin-scans-list'),
    path('scans/weekend-weekly/', views.weekend_scans_by_week, name='admin-scans-weekend-weekly'),
    path('scans/today-3hours/', views.today_scans_by_three_hours, name='admin-scans-today-3hours'),
    path('subscriptions/', views.subscriptions_list, name='admin-subscriptions-list'),
]
