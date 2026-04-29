from django.urls import path

from . import views

urlpatterns = [
    path('dashboard/', views.dashboard_summary, name='admin-dashboard-summary'),
    path('users/', views.users_list, name='admin-users-list'),
    path('users/<uuid:user_id>/edit/', views.user_edit, name='admin-user-edit'),
    path('users/<uuid:user_id>/remove/', views.user_remove, name='admin-user-remove'),
    path('scans/', views.scans_list, name='admin-scans-list'),
    path('subscriptions/', views.subscriptions_list, name='admin-subscriptions-list'),
]
