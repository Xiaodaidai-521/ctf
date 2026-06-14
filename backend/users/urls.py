from django.urls import path
from . import views

app_name = 'users'

urlpatterns = [
    path('register/', views.RegisterView.as_view(), name='register'),
    path('login/', views.login_view, name='login'),
    path('profile/', views.profile_view, name='profile'),
    path('profile/update/', views.profile_update_view, name='profile_update'),
    path('leaderboard/', views.leaderboard_view, name='leaderboard'),
    path('admin/users/', views.admin_user_list_view, name='admin_user_list'),
    path('admin/users/create/', views.admin_user_create_view, name='admin_user_create'),
    path('admin/users/<int:user_id>/update/', views.admin_user_update_view, name='admin_user_update'),
    path('admin/users/<int:user_id>/delete/', views.admin_user_delete_view, name='admin_user_delete'),
]
