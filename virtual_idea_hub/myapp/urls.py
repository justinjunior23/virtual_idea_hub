from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [

    # ── Static / Misc ─────────────────────────────────────────────
    path('', views.home_view, name='home_view'),
    path('about/', views.about, name='about'),
    path('contact/', views.contact, name='contact'),
    path('contact/submit/', views.contact_form_submit, name='contact_form_submit'),
    path('profile/', views.profile, name='profile'),
    path('profile/settings/submit/', views.profile_settings_submit, name='profile_settings_submit'),
    path('privacy-policy/', views.privacy_policy, name='privacy_policy'),
    path('terms-of-service/', views.terms_of_service, name='terms_of_service'),
    path('search/', views.search_results, name='search_results'),

    # ── Auth ─────────────────────────────────────────────────────
    path('register/', views.register_view, name='register'),
    path('verify-otp/', views.verify_otp, name='verify_otp'),
    path('resend-otp/', views.resend_otp, name='resend_otp'),
    path('login/', views.login_view, name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    # ── Dashboards ────────────────────────────────────────────────
    path('user_dashboard/', views.user_dashboard, name='user_dashboard'),
    path('staff/', views.staff_dashboard, name='staff_dashboard'),
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),

    # ── Staff ────────────────────────────────────────────────────
    path('staff/<slug:category_slug>/', views.staff_category_list, name='staff_category_list'),
    path('staff/<slug:category_slug>/<int:pk>/', views.staff_post_detail, name='staff_post_detail'),
    path('staff/<slug:category_slug>/bulk-update/', views.staff_bulk_update, name='staff_bulk_update'),

    # ── Admin User Management ─────────────────────────────────────
    path('admin-dashboard/users/', views.admin_user_list, name='admin_user_list'),
    path('admin-dashboard/users/create/', views.admin_user_create, name='admin_user_create'),  # ✅ fixed
    path('admin-dashboard/users/<int:user_id>/', views.admin_user_detail, name='admin_user_detail'),
    path('admin-dashboard/users/<int:user_id>/toggle-active/', views.admin_toggle_user_active, name='admin_toggle_user_active'),
    path('admin-dashboard/users/<int:user_id>/update-role/', views.update_user_role, name='update_user_role'),
    path('admin-dashboard/users/<int:user_id>/delete/', views.delete_user, name='delete_user'),

    # ── Ideas ─────────────────────────────────────────────────────
    path('ideas/', views.idea_list, name='idea_list'),
    path('ideas/<int:pk>/', views.idea_detail, name='idea_detail'),

    # ── Awareness ────────────────────────────────────────────────
    path('awareness/', views.awareness_dashboard, name='awareness_dashboard'),
    path('awareness/create/', views.create_awareness, name='create_awareness'),
    path('awareness/<int:pk>/', views.awareness_detail, name='awareness_detail'),
    path('awareness/<int:pk>/edit/', views.edit_awareness, name='edit_awareness'),
    path('awareness/<int:pk>/delete/', views.delete_awareness, name='delete_awareness'),

    # ── Innovation ───────────────────────────────────────────────
    path('innovation/', views.innovation_dashboard, name='innovation_dashboard'),
    path('innovation/create/', views.create_innovation, name='create_innovation'),
    path('innovation/<int:pk>/', views.innovation_detail, name='innovation_detail'),
    path('innovation/<int:pk>/edit/', views.edit_innovation, name='edit_innovation'),
    path('innovation/<int:pk>/delete/', views.delete_innovation, name='delete_innovation'),

    # ── Suggestions ──────────────────────────────────────────────
    path('suggestions/', views.suggestions_dashboard, name='suggestions_dashboard'),
    path('suggestions/create/', views.create_suggestion, name='create_suggestion'),
    path('suggestions/<int:pk>/', views.suggestion_detail, name='suggestion_detail'),
    path('suggestions/<int:pk>/edit/', views.edit_suggestion, name='edit_suggestion'),
    path('suggestions/<int:pk>/delete/', views.delete_suggestion, name='delete_suggestion'),

    # ── Emergency ────────────────────────────────────────────────
    path('emergency/', views.emergency_dashboard, name='emergency_dashboard'),
    path('emergency/create/', views.create_emergency, name='create_emergency'),
    path('emergency/<int:pk>/', views.emergency_detail, name='emergency_detail'),
    path('emergency/<int:pk>/edit/', views.edit_emergency, name='edit_emergency'),
    path('emergency/<int:pk>/delete/', views.delete_emergency, name='delete_emergency'),

    # ── Recommendations ──────────────────────────────────────────
    path('recommendations/', views.recommendations_dashboard, name='recommendations_dashboard'),
    path('recommendations/create/', views.create_recommendation, name='create_recommendation'),
    path('recommendations/<int:pk>/', views.recommendation_detail, name='recommendation_detail'),
    path('recommendations/<int:pk>/edit/', views.edit_recommendation, name='edit_recommendation'),
    path('recommendations/<int:pk>/delete/', views.delete_recommendation, name='delete_recommendation'),

    # ── Complaints ───────────────────────────────────────────────
    path('complaints/', views.complaints_dashboard, name='complaints_dashboard'),
    path('complaints/create/', views.create_complain, name='create_complain'),
    path('complaints/<int:pk>/', views.complain_detail, name='complain_detail'),
    path('complaints/<int:pk>/edit/', views.edit_complain, name='edit_complain'),
    path('complaints/<int:pk>/delete/', views.delete_complain, name='delete_complain'),

    # ── Others ───────────────────────────────────────────────────
    path('others/', views.others_dashboard, name='others_dashboard'),
    path('others/create/', views.create_others, name='create_others'),
    path('others/<int:pk>/', views.others_detail, name='others_detail'),
    path('others/<int:pk>/edit/', views.edit_others, name='edit_others'),
    path('others/<int:pk>/delete/', views.delete_others, name='delete_others'),

    # ── Reporting ────────────────────────────────────────────────
    path('reporting/', views.reporting_dashboard, name='reporting_dashboard'),
    path('reporting/create/', views.post_reporting, name='post_reporting'),
    path('reporting/<int:pk>/', views.reporting_detail, name='reporting_detail'),
    path('reporting/<int:pk>/edit/', views.edit_reporting, name='edit_reporting'),
    path('reporting/<int:pk>/delete/', views.delete_reporting, name='delete_reporting'),

    # ── Redirect ─────────────────────────────────────────────────
    path('login-redirect/', views.login_redirect, name='login_redirect'),
]