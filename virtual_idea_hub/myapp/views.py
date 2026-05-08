from django.core.mail import send_mail
import random
from django.template.loader import render_to_string
from django.utils.html import strip_tags, escape
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.utils import timezone
from datetime import timedelta
from .decorators import admin_required, staff_required
from .models import (
    Idea, UserProfile, PostAwareness, PostOthers, Reporting,
    PostEmergency, PostRecommendations, PostInnovation, PostSuggestions,
    PostComplain, EmailOTP, StaffFeedback,
)
from django.http import HttpResponse
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.contrib.sites.shortcuts import get_current_site
from django.contrib.auth.models import User
from .forms import UserRegistrationForm
from django.contrib import messages
from django.db.models import Q
from django.views.generic import RedirectView
from django.views.decorators.http import require_POST
import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db.models import Count



CATEGORY_MAP = {
    'awareness':      (PostAwareness,       'Awareness'),
    'innovation':     (PostInnovation,      'Innovation'),
    'suggestion':     (PostSuggestions,     'Suggestions'),
    'emergency':      (PostEmergency,       'Emergency'),
    'recommendation': (PostRecommendations, 'Recommendations'),
    'complaint':      (PostComplain,        'Complaints'),
    'others':         (PostOthers,          'Others'),
    'reporting':      (Reporting,           'Reporting'),
}


def _get_post_email(post, category_slug):
    """
Return the best contact email for a post.
 Authenticated users       → user.email
    Anonymous with contact_email field → contact_email
    Reporting posts           → post.email  (field already on that model)
    """
    if hasattr(post, 'user') and post.user:
        return post.user.email
    if category_slug == 'reporting' and hasattr(post, 'email'):
        return post.email
    if hasattr(post, 'contact_email') and post.contact_email:
        return post.contact_email
    return None


def _send_feedback_email(request, post, category_slug, feedback_message, new_status):
    """
    Send a feedback email to the submitter.
    Returns True if sent, False otherwise.
    """
    recipient = _get_post_email(post, category_slug)
    if not recipient:
        return False

    category_display = CATEGORY_MAP[category_slug][1]
    post_title = getattr(post, 'title', None) or getattr(post, 'report_name', 'Your submission')

    subject = f"Update on your {category_display} submission – Virtual Idea Hub"
    html_message = render_to_string('staff/feedback_email.html', {
        'post':             post,
        'post_title':       post_title,
        'category':         category_display,
        'feedback_message': feedback_message,
        'new_status':       new_status,
        'staff_name':       request.user.get_full_name() or request.user.username,
    })

    try:
        send_mail(
            subject,
            f"Update on your submission '{post_title}':\n\n{feedback_message}\n\nStatus: {new_status}",
            'noreply@yourdomain.com',
            [recipient],
            html_message=html_message,
            fail_silently=False,
        )
        return True
    except Exception:
        return False



@login_required
@staff_required
def staff_dashboard(request):
    """Overview: counts by category and status so staff can see what needs attention."""
    stats = {}
    for slug, (Model, label) in CATEGORY_MAP.items():
        stats[slug] = {
            'label':     label,
            'pending':   Model.objects.filter(status='pending').count(),
            'in_review': Model.objects.filter(status='in_review').count(),
            'resolved':  Model.objects.filter(status='resolved').count(),
            'rejected':  Model.objects.filter(status='rejected').count(),
            'total':     Model.objects.count(),
        }

    # ── Gather recent submissions across ALL categories ──
    recent_submissions = []
    for slug, (Model, label) in CATEGORY_MAP.items():
        qs = Model.objects.select_related('user').order_by('-created_at')[:5]
        for sub in qs:
            sub.category_slug  = slug
            sub.category_label = label
            # Normalize subject field (Reporting uses report_name, others use title)
            if not hasattr(sub, 'title'):
                sub.subject = getattr(sub, 'report_name', '—')
            else:
                sub.subject = sub.title or '—'
            recent_submissions.append(sub)

    recent_submissions.sort(key=lambda x: x.created_at, reverse=True)
    recent_submissions = recent_submissions[:20]

    recent_feedback = StaffFeedback.objects.select_related('staff').order_by('-created_at')[:10]

    return render(request, 'staff/dashboard.html', {
        'stats':              stats,
        'recent_feedback':    recent_feedback,
        'recent_submissions': recent_submissions,
    })


@login_required
@staff_required
def submission_detail_ajax(request, category_slug, pk):
    """AJAX GET — returns JSON for the slide-in panel."""
    if category_slug not in CATEGORY_MAP:
        return JsonResponse({'error': 'Unknown category'}, status=404)

    Model, label = CATEGORY_MAP[category_slug]
    post = get_object_or_404(Model, pk=pk)

    feedbacks = StaffFeedback.objects.filter(
        category=category_slug, post_id=pk      # same field name as staff_post_detail
    ).select_related('staff').order_by('created_at')

    fb_data = [{
        'staff_name':    fb.staff.get_full_name() or fb.staff.username,
        'staff_initial': fb.staff.username[0].upper(),
        'new_status':    fb.new_status,
        'message':       fb.message,
        'created_at':    fb.created_at.strftime('%b %d, %Y %H:%M'),
    } for fb in feedbacks]

    # Handle Reporting (different field names) vs all other categories
    if category_slug == 'reporting':
        subject      = getattr(post, 'report_name', '')
        message      = getattr(post, 'report_description', '')
        if post.user:
            user_display = post.user.get_full_name() or post.user.username
        else:
            name = f"{getattr(post,'first_name','')} {getattr(post,'last_name','')}".strip()
            user_display = name or 'Anonymous'
    else:
        subject      = getattr(post, 'title', '')
        message      = getattr(post, 'content', '')
        user_display = (
            post.user.get_full_name() or post.user.username
        ) if post.user else 'Anonymous'

    return JsonResponse({
        'id':             post.pk,
        'category_label': label,
        'category_slug':  category_slug,
        'user_display':   user_display,
        'status':         post.status,
        'subject':        subject,
        'message':        message,
        'created_at':     post.created_at.strftime('%b %d, %Y %H:%M'),
        'feedbacks':      fb_data,
    })


@login_required
@staff_required
@require_http_methods(['POST'])
def submission_update_ajax(request, category_slug, pk):
    """AJAX POST — update status and/or save feedback."""
    if category_slug not in CATEGORY_MAP:
        return JsonResponse({'ok': False, 'error': 'Unknown category'}, status=404)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': 'Invalid JSON'}, status=400)

    new_status = body.get('status', '').strip()
    message    = body.get('message', '').strip()

    if not new_status and not message:
        return JsonResponse({'ok': False, 'error': 'Nothing to update.'}, status=400)

    Model, label = CATEGORY_MAP[category_slug]
    post = get_object_or_404(Model, pk=pk)

    if new_status in ('pending', 'in_review', 'resolved', 'rejected'):
        post.status = new_status
        post.save(update_fields=['status'])

    email_sent = False
    if message:
        email_sent = _send_feedback_email(
            request, post, category_slug,
            message, new_status or post.status
        )

    StaffFeedback.objects.create(
        staff      = request.user,
        category   = category_slug,
        post_id    = pk,                    # same field as staff_post_detail
        message    = message or f'Status changed to {new_status}',
        new_status = new_status or post.status,
        email_sent = email_sent,
    )

    return JsonResponse({'ok': True})
@login_required
@staff_required
def staff_category_list(request, category_slug):
    """List all submissions in a category with filtering by status and search."""
    if category_slug not in CATEGORY_MAP:
        messages.error(request, "Unknown category.")
        return redirect('staff_dashboard')

    Model, label = CATEGORY_MAP[category_slug]

    status_filter = request.GET.get('status', '')
    query         = request.GET.get('q', '')

    posts = Model.objects.all().order_by('-created_at')

    if status_filter:
        posts = posts.filter(status=status_filter)

    if query:
        if category_slug == 'reporting':
            posts = posts.filter(
                Q(report_name__icontains=query) |
                Q(report_description__icontains=query) |
                Q(location__icontains=query)
            )
        else:
            posts = posts.filter(
                Q(title__icontains=query) | Q(content__icontains=query)
            )

    paginator = Paginator(posts, 20)
    page_obj  = paginator.get_page(request.GET.get('page'))

    return render(request, 'staff/category_list.html', {
        'page_obj':       page_obj,
        'category_slug':  category_slug,
        'category_label': label,
        'status_filter':  status_filter,
        'query':          query,
        'status_choices': [
            ('', 'All'), ('pending', 'Pending'), ('in_review', 'In Review'),
            ('resolved', 'Resolved'), ('rejected', 'Rejected'),
        ],
    })


@login_required
def staff_post_detail(request, category_slug, pk):
    """View a single submission and submit feedback / change status."""
    
    # Temporary: manual role check with visible error
    try:
        role = request.user.userprofile.role
        if role not in ('staff', 'admin'):
            return redirect('user_dashboard')
    except Exception as e:
        print(f"ROLE CHECK ERROR: {e}")
        return redirect('user_dashboard')

    if category_slug not in CATEGORY_MAP:
        print(f"SLUG ERROR: '{category_slug}' not in {list(CATEGORY_MAP.keys())}")
        messages.error(request, "Unknown category.")
        return redirect('staff_dashboard')

    Model, label = CATEGORY_MAP[category_slug]
    post = get_object_or_404(Model, pk=pk)

    previous_feedback = StaffFeedback.objects.filter(
        category=category_slug, post_id=pk
    ).select_related('staff').order_by('-created_at')

    if request.method == 'POST':
        feedback_message = request.POST.get('feedback_message', '').strip()
        new_status       = request.POST.get('new_status', 'in_review')
        send_email_flag  = request.POST.get('send_email') == 'on'

        print(f"POST received: message='{feedback_message}', status='{new_status}', email={send_email_flag}")

        if not feedback_message:
            messages.error(request, "Feedback message cannot be empty.")
        else:
            try:
                post.status = new_status
                post.save(update_fields=['status'])
                print("✅ post.save() OK")

                email_sent = False
                if send_email_flag:
                    email_sent = _send_feedback_email(
                        request, post, category_slug, feedback_message, new_status
                    )
                print(f"✅ email_sent={email_sent}")

                StaffFeedback.objects.create(
                    staff      = request.user,
                    category   = category_slug,
                    post_id    = pk,
                    message    = feedback_message,
                    new_status = new_status,
                    email_sent = email_sent,
                )
                print("✅ StaffFeedback.create() OK")

                if send_email_flag and not email_sent:
                    messages.warning(request, "Feedback saved but email could not be sent.")
                elif send_email_flag and email_sent:
                    messages.success(request, "Feedback saved and email sent to submitter.")
                else:
                    messages.success(request, "Feedback saved (no email sent).")

                return redirect('staff_post_detail', category_slug=category_slug, pk=pk)

            except Exception as e:
                import traceback
                print(f"❌ ERROR: {type(e).__name__}: {e}")
                traceback.print_exc()
                messages.error(request, f"Error: {e}")

    if post.status == 'pending':
        post.status = 'in_review'
        post.save(update_fields=['status'])

    contact_email = _get_post_email(post, category_slug)

    return render(request, 'staff/post_detail.html', {
        'post':              post,
        'category_slug':     category_slug,
        'category_label':    label,
        'previous_feedback': previous_feedback,
        'contact_email':     contact_email,
        'status_choices': [
            ('in_review', 'In Review'),
            ('resolved',  'Resolved'),
            ('rejected',  'Rejected'),
        ],
    })

@login_required
@staff_required
def staff_bulk_update(request, category_slug):
    """Allow staff to mark multiple submissions at once (e.g. bulk-resolve)."""
    if request.method != 'POST' or category_slug not in CATEGORY_MAP:
        return redirect('staff_dashboard')

    Model, label = CATEGORY_MAP[category_slug]
    post_ids   = request.POST.getlist('post_ids')
    new_status = request.POST.get('new_status', 'resolved')

    updated = Model.objects.filter(pk__in=post_ids).update(status=new_status)
    messages.success(request, f"{updated} submission(s) marked as '{new_status}'.")
    return redirect('staff_category_list', category_slug=category_slug)


@login_required
@admin_required
def admin_dashboard(request):
    """Full site-wide stats: post counts, user counts, recent activity."""
    now      = timezone.now()
    week_ago = now - timedelta(days=7)

    category_stats = [
        {
            'label':     'Awareness',
            'slug':      'awareness',
            'total':     PostAwareness.objects.count(),
            'pending':   PostAwareness.objects.filter(status='pending').count(),
            'resolved':  PostAwareness.objects.filter(status='resolved').count(),
            'this_week': PostAwareness.objects.filter(created_at__gte=week_ago).count(),
        },
        {
            'label':     'Innovation',
            'slug':      'innovation',
            'total':     PostInnovation.objects.count(),
            'pending':   PostInnovation.objects.filter(status='pending').count(),
            'resolved':  PostInnovation.objects.filter(status='resolved').count(),
            'this_week': PostInnovation.objects.filter(created_at__gte=week_ago).count(),
        },
        {
            'label':     'Suggestions',
            'slug':      'suggestion',
            'total':     PostSuggestions.objects.count(),
            'pending':   PostSuggestions.objects.filter(status='pending').count(),
            'resolved':  PostSuggestions.objects.filter(status='resolved').count(),
            'this_week': PostSuggestions.objects.filter(created_at__gte=week_ago).count(),
        },
        {
            'label':     'Emergency',
            'slug':      'emergency',
            'total':     PostEmergency.objects.count(),
            'pending':   PostEmergency.objects.filter(status='pending').count(),
            'resolved':  PostEmergency.objects.filter(status='resolved').count(),
            'this_week': PostEmergency.objects.filter(created_at__gte=week_ago).count(),
        },
        {
            'label':     'Recommendations',
            'slug':      'recommendation',
            'total':     PostRecommendations.objects.count(),
            'pending':   PostRecommendations.objects.filter(status='pending').count(),
            'resolved':  PostRecommendations.objects.filter(status='resolved').count(),
            'this_week': PostRecommendations.objects.filter(created_at__gte=week_ago).count(),
        },
        {
            'label':     'Complaints',
            'slug':      'complaint',
            'total':     PostComplain.objects.count(),
            'pending':   PostComplain.objects.filter(status='pending').count(),
            'resolved':  PostComplain.objects.filter(status='resolved').count(),
            'this_week': PostComplain.objects.filter(created_at__gte=week_ago).count(),
        },
        {
            'label':     'Others',
            'slug':      'others',
            'total':     PostOthers.objects.count(),
            'pending':   PostOthers.objects.filter(status='pending').count(),
            'resolved':  PostOthers.objects.filter(status='resolved').count(),
            'this_week': PostOthers.objects.filter(created_at__gte=week_ago).count(),
        },
        {
            'label':     'Reporting',
            'slug':      'reporting',
            'total':     Reporting.objects.count(),
            'pending':   Reporting.objects.filter(status='pending').count(),
            'resolved':  Reporting.objects.filter(status='resolved').count(),
            'this_week': Reporting.objects.filter(created_at__gte=week_ago).count(),
        },
    ]

    total_posts    = sum(c['total']     for c in category_stats)
    total_pending  = sum(c['pending']   for c in category_stats)
    total_resolved = sum(c['resolved']  for c in category_stats)
    total_new      = sum(c['this_week'] for c in category_stats)

    total_users   = User.objects.count()
    new_users     = User.objects.filter(date_joined__gte=week_ago).count()
    staff_count   = UserProfile.objects.filter(role='staff').count()
    admin_count   = UserProfile.objects.filter(role='admin').count()
    regular_count = UserProfile.objects.filter(role='regular_user').count()

    recent_feedback = StaffFeedback.objects.select_related('staff').order_by('-created_at')[:10]
    recent_users    = User.objects.select_related('userprofile').order_by('-date_joined')[:10]

    return render(request, 'admin/dashboard.html', {
        'category_stats':  category_stats,
        'total_posts':     total_posts,
        'total_pending':   total_pending,
        'total_resolved':  total_resolved,
        'total_new':       total_new,
        'total_users':     total_users,
        'new_users':       new_users,
        'staff_count':     staff_count,
        'admin_count':     admin_count,
        'regular_count':   regular_count,
        'recent_feedback': recent_feedback,
        'recent_users':    recent_users,
    })


@login_required
@admin_required
def admin_user_list(request):
    query       = request.GET.get('q', '')
    role_filter = request.GET.get('role', '')

    users = User.objects.select_related('userprofile').order_by('-date_joined')

    # ✅ Auto-create UserProfile for superusers/staff with no profile
    for user in users:
        if not hasattr(user, 'userprofile'):
            role = 'admin' if user.is_superuser else 'staff' if user.is_staff else 'regular_user'
            UserProfile.objects.create(user=user, role=role)

    if query:
        users = users.filter(
            Q(username__icontains=query)   |
            Q(email__icontains=query)      |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query)
        )
    if role_filter:
        users = users.filter(userprofile__role=role_filter)

    return render(request, 'admin/user_list.html', {
        'users':       users,
        'query':       query,
        'role_filter': role_filter,
        'role_choices': [
            ('', 'All Roles'),
            ('regular_user', 'Regular User'),
            ('staff',        'Staff'),
            ('admin',        'Admin'),
        ],
    })


@login_required
@admin_required
def admin_user_detail(request, user_id):
    """View a user's profile and change their role."""
    target_user = get_object_or_404(User, pk=user_id)
    profile, _  = UserProfile.objects.get_or_create(user=target_user)

    if request.method == 'POST':
        new_role = request.POST.get('role', profile.role)
        if new_role in ['regular_user', 'staff', 'admin']:
            profile.role = new_role
            profile.save()

            target_user.is_staff     = new_role in ('staff', 'admin')
            target_user.is_superuser = new_role == 'admin'
            target_user.save(update_fields=['is_staff', 'is_superuser'])

            messages.success(request, f"{target_user.username}'s role updated to '{new_role}'.")
        else:
            messages.error(request, "Invalid role selected.")
        return redirect('admin_user_detail', user_id=user_id)

    submission_counts = {
        'Awareness':       PostAwareness.objects.filter(user=target_user).count(),
        'Innovation':      PostInnovation.objects.filter(user=target_user).count(),
        'Suggestions':     PostSuggestions.objects.filter(user=target_user).count(),
        'Emergency':       PostEmergency.objects.filter(user=target_user).count(),
        'Recommendations': PostRecommendations.objects.filter(user=target_user).count(),
        'Complaints':      PostComplain.objects.filter(user=target_user).count(),
        'Others':          PostOthers.objects.filter(user=target_user).count(),
        'Reporting':       Reporting.objects.filter(user=target_user).count(),
    }

    return render(request, 'admin/user_detail.html', {
        'target_user':       target_user,
        'profile':           profile,
        'submission_counts': submission_counts,
        'role_choices': [
            ('regular_user', 'Regular User'),
            ('staff',        'Staff'),
            ('admin',        'Admin'),
        ],
    })


@login_required
@admin_required
def admin_toggle_user_active(request, user_id):
    """Enable / disable a user account."""
    if request.method == 'POST':
        target_user           = get_object_or_404(User, pk=user_id)
        target_user.is_active = not target_user.is_active
        target_user.save(update_fields=['is_active'])
        state = "activated" if target_user.is_active else "deactivated"
        messages.success(request, f"Account {state} for {target_user.username}.")
    return redirect('admin_user_list')

@login_required
@admin_required
@require_POST
def update_user_role(request, user_id):
    new_role = request.POST.get('role')

    user = get_object_or_404(User, id=user_id)
    profile = user.userprofile

    profile.role = new_role
    profile.save()

    messages.success(request, f"{user.username}'s role updated to {new_role}.")
    return redirect('admin_user_list')


  
@admin_required
@require_POST  # 🚨 critical
def delete_user(request, user_id):
    user = get_object_or_404(User, id=user_id)

    # 🚫 Prevent deleting yourself
    if user == request.user:
        messages.error(request, "You cannot delete your own account.")
        return redirect('admin_user_list')

    # 🚫 Optional: protect superusers (smart move)
    if user.is_superuser:
        messages.error(request, "You cannot delete a superuser.")
        return redirect('admin_user_list')

    user.delete()
    messages.success(request, "User deleted successfully.")

    return redirect('admin_user_list')


@login_required
@admin_required
def admin_user_create(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '').strip()
        role = request.POST.get('role', 'regular_user')

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already exists.")
        elif User.objects.filter(email=email).exists():
            messages.error(request, "Email already exists.")
        else:
            user = User.objects.create_user(username=username, email=email, password=password)
            user.is_staff = role in ('staff', 'admin')
            user.is_superuser = role == 'admin'
            user.save()
            UserProfile.objects.create(user=user, role=role)
            messages.success(request, f"User '{username}' created successfully.")
            return redirect('admin_user_list')

    return render(request, 'admin/user_create.html', {
        'role_choices': [
            ('regular_user', 'Regular User'),
            ('staff', 'Staff'),
            ('admin', 'Admin'),
        ]
    })
# ─────────────────────────────────────────────────────────────────────────────
# Auth / Registration
# ─────────────────────────────────────────────────────────────────────────────

def _post_submit_redirect(request):
    """After a successful create, send logged-in users to their dashboard,
    anonymous users back to home."""
    return redirect('user_dashboard') if request.user.is_authenticated else redirect('home_view')


def register_view(request):
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']

            if User.objects.filter(email=email).exists():
                messages.error(request, "An account with this email already exists.")
                return render(request, 'register.html', {'form': form})

            user = form.save(commit=False)
            user.set_password(form.cleaned_data['password1'])
            user.is_active = False
            user.save()

            UserProfile.objects.create(user=user, role='regular_user')

            otp_code = str(random.randint(100000, 999999))
            EmailOTP.objects.update_or_create(
                user=user,
                defaults={'code': otp_code}
            )

            html_message = render_to_string('registration/otp_email.html', {
                'user':     user,
                'otp_code': otp_code,
            })
            try:
                send_mail(
                    subject='Your Verification Code – Virtual Idea Hub',
                    message=f'Your verification code is: {otp_code}\n\nIt expires in 10 minutes.',
                    from_email='noreply@yourdomain.com',
                    recipient_list=[user.email],
                    html_message=html_message,
                    fail_silently=False,
                )
            except Exception:
                user.delete()
                messages.error(request, "Could not send verification email. Please try again.")
                return render(request, 'register.html', {'form': form})

            request.session['pending_user_id'] = user.pk
            messages.success(request, f"A 6-digit code was sent to {email}. Please check your inbox.")
            return redirect('verify_otp')
    else:
        form = UserRegistrationForm()

    return render(request, 'register.html', {
        'title':   'Register – Virtual Idea Hub',
        'message': 'Create your account to get started.',
        'form':    form,
    })

def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            auth_login(request, user)

            # Role-based redirect
            try:
                role = user.userprofile.role
                print(f"DEBUG: user={user.username}, role={role}")  # check terminal
                if role == 'admin':
                    return redirect('admin_dashboard')
                elif role == 'staff':
                    return redirect('staff_dashboard')
                else:
                    return redirect('user_dashboard')
            except Exception as e:
                print(f"DEBUG ERROR: {e}")
                return redirect('user_dashboard')
    else:
        form = AuthenticationForm()

    return render(request, 'registration/login.html', {'form': form})



@login_required
def login_redirect(request):
    try:
        role = request.user.userprofile.role
        if role == 'admin':
            return redirect('admin_dashboard')
        elif role == 'staff':
            return redirect('staff_dashboard')
        else:
            return redirect('user_dashboard')
    except Exception:
        return redirect('user_dashboard')

def verify_otp(request):
    user_id = request.session.get('pending_user_id')
    if not user_id:
        messages.error(request, "Session expired. Please register again.")
        return redirect('register')

    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        messages.error(request, "User not found. Please register again.")
        return redirect('register')

    if request.method == 'POST':
        entered_code = request.POST.get('otp_code', '').strip()

        try:
            otp_record = EmailOTP.objects.get(user=user)
        except EmailOTP.DoesNotExist:
            messages.error(request, "No OTP found. Please register again.")
            return redirect('register')

        if otp_record.is_expired():
            otp_record.delete()
            user.delete()
            del request.session['pending_user_id']
            messages.error(request, "Your code has expired. Please register again.")
            return redirect('register')

        if entered_code != otp_record.code:
            messages.error(request, "Incorrect code. Please try again.")
            return render(request, 'registration/verify_otp.html', {'email': user.email})

        user.is_active = True
        user.save(update_fields=['is_active'])
        otp_record.delete()
        del request.session['pending_user_id']

        messages.success(request, "Email verified! Your account is now active. Please log in.")
        return redirect('login')

    return render(request, 'registration/verify_otp.html', {'email': user.email})


def resend_otp(request):
    """Lets the user request a fresh OTP if theirs expired or they didn't receive it."""
    user_id = request.session.get('pending_user_id')
    if not user_id:
        messages.error(request, "Session expired. Please register again.")
        return redirect('register')

    try:
        user = User.objects.get(pk=user_id, is_active=False)
    except User.DoesNotExist:
        return redirect('register')

    new_code = str(random.randint(100000, 999999))
    EmailOTP.objects.update_or_create(
        user=user,
        defaults={'code': new_code}
    )

    html_message = render_to_string('registration/otp_email.html', {
        'user':     user,
        'otp_code': new_code,
    })
    try:
        send_mail(
            subject='New Verification Code – Virtual Idea Hub',
            message=f'Your new verification code is: {new_code}\n\nIt expires in 10 minutes.',
            from_email='noreply@yourdomain.com',
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False,
        )
        messages.success(request, f"A new code was sent to {user.email}.")
    except Exception:
        messages.error(request, "Could not resend email. Please try again.")

    return redirect('verify_otp')


# ─────────────────────────────────────────────────────────────────────────────
# Public / misc views
# ─────────────────────────────────────────────────────────────────────────────

def home_view(request):
    recent_awareness   = PostAwareness.objects.order_by('-created_at')[:3]
    recent_innovations = PostInnovation.objects.order_by('-created_at')[:3]
    recent_suggestions = PostSuggestions.objects.order_by('-created_at')[:3]
    recent_emergencies = PostEmergency.objects.order_by('-created_at')[:3]

    stats = {
        'awareness':       PostAwareness.objects.count(),
        'innovations':     PostInnovation.objects.count(),
        'suggestions':     PostSuggestions.objects.count(),
        'complaints':      PostComplain.objects.count(),
        'emergencies':     PostEmergency.objects.count(),
        'recommendations': PostRecommendations.objects.count(),
        'reports':         Reporting.objects.count(),
        'others':          PostOthers.objects.count(),
        'total_users':     User.objects.count(),
    }
    stats['total_posts'] = sum(stats[k] for k in [
        'awareness', 'innovations', 'suggestions', 'complaints',
        'emergencies', 'recommendations', 'reports', 'others',
    ])

    return render(request, 'home.html', {
        'recent_awareness':   recent_awareness,
        'recent_innovations': recent_innovations,
        'recent_suggestions': recent_suggestions,
        'recent_emergencies': recent_emergencies,
        'stats':              stats,
        'user':               request.user,
    })


def privacy_policy(request):          return render(request, 'privacy_policy.html')
def terms_of_service(request):        return render(request, 'terms_of_service.html')
def about(request):                   return render(request, 'about.html')
def contact(request):                 return render(request, 'contact.html')
def profile(request):                 return render(request, 'profile.html')
def profile_settings_submit(request): return render(request, 'profile_settings_submit.html')
def contact_form_submit(request):     return render(request, 'contact_form_submit.html')

def search_results(request):
    query   = request.GET.get('query', '')
    results = Idea.objects.filter(title__icontains=query)
    return render(request, 'search_results.html', {'results': results, 'query': query})

def idea_list(request):
    return render(request, 'myapp/idea_list.html', {'ideas': Idea.objects.all()})

def idea_detail(request, pk):
    return render(request, 'myapp/idea_detail.html', {'idea': get_object_or_404(Idea, pk=pk)})


# ─────────────────────────────────────────────────────────────────────────────
# User dashboard
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def user_dashboard(request):
    awareness_posts   = PostAwareness.objects.filter(user=request.user).order_by('-created_at')
    innovations       = PostInnovation.objects.filter(user=request.user).order_by('-created_at')
    suggestions       = PostSuggestions.objects.filter(user=request.user).order_by('-created_at')
    emergencies       = PostEmergency.objects.filter(user=request.user).order_by('-created_at')
    submitted_reports = Reporting.objects.filter(user=request.user).order_by('-created_at')
    recommendations   = PostRecommendations.objects.filter(user=request.user).order_by('-created_at')
    complaints        = PostComplain.objects.filter(user=request.user).order_by('-created_at')
    others            = PostOthers.objects.filter(user=request.user).order_by('-created_at')

    ideas_shared = (
        awareness_posts.count() + innovations.count() + suggestions.count() +
        emergencies.count() + recommendations.count() + complaints.count() + others.count()
    )

    return render(request, 'user_dashboard.html', {
        'awareness_posts':   awareness_posts,
        'innovations':       innovations,
        'suggestions':       suggestions,
        'emergencies':       emergencies,
        'submitted_reports': submitted_reports,
        'recommendations':   recommendations,
        'complaints':        complaints,
        'others':            others,
        'ideas':             [],
        'ideas_shared':      ideas_shared,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Awareness
# ─────────────────────────────────────────────────────────────────────────────

def create_awareness(request):
    if request.method == 'POST':
        title     = request.POST.get('title', '').strip()
        content   = request.POST.get('content', '').strip()
        anonymous = request.POST.get('post_as_anonymous') == 'on'
        if title and content:
            PostAwareness.objects.create(
                user         = None if anonymous else (request.user if request.user.is_authenticated else None),
                title        = title,
                content      = content,
                is_anonymous = anonymous or not request.user.is_authenticated,
            )
        return _post_submit_redirect(request)
    return render(request, 'awareness/create.html', {'category': 'Awareness'})

@login_required
def awareness_dashboard(request):
    query = request.GET.get('q', '')
    posts = PostAwareness.objects.filter(user=request.user).order_by('-created_at')
    if query:
        posts = (
            PostAwareness.objects.filter(user=request.user, title__icontains=query) |
            PostAwareness.objects.filter(user=request.user, content__icontains=query)
        ).order_by('-created_at')
    return render(request, 'awareness/dashboard.html', {
        'posts': posts,
        'total': PostAwareness.objects.filter(user=request.user).count(),
        'query': query,
    })

@login_required
def edit_awareness(request, pk):
    post = get_object_or_404(PostAwareness, pk=pk, user=request.user)
    if request.method == 'POST':
        post.title   = request.POST.get('title', post.title).strip()
        post.content = request.POST.get('content', post.content).strip()
        post.save()
        return redirect('user_dashboard')
    return render(request, 'awareness/edit.html', {'post': post})

@login_required
def delete_awareness(request, pk):
    post = get_object_or_404(PostAwareness, pk=pk, user=request.user)
    if request.method == 'POST':
        post.delete()
    return redirect('user_dashboard')

@login_required
def awareness_detail(request, pk):
    post = get_object_or_404(PostAwareness, pk=pk, user=request.user)
    return render(request, 'awareness/detail.html', {'post': post})


# ─────────────────────────────────────────────────────────────────────────────
# Innovation
# ─────────────────────────────────────────────────────────────────────────────

def create_innovation(request):
    if request.method == 'POST':
        title     = request.POST.get('title', '').strip()
        content   = request.POST.get('content', '').strip()
        anonymous = request.POST.get('post_as_anonymous') == 'on'
        if title and content:
            PostInnovation.objects.create(
                user         = None if anonymous else (request.user if request.user.is_authenticated else None),
                title        = title,
                content      = content,
                is_anonymous = anonymous or not request.user.is_authenticated,
            )
        return _post_submit_redirect(request)
    return render(request, 'innovation/create.html', {'category': 'Innovation'})

@login_required
def innovation_dashboard(request):
    query = request.GET.get('q', '')
    posts = PostInnovation.objects.filter(user=request.user).order_by('-created_at')
    if query:
        posts = (
            PostInnovation.objects.filter(user=request.user, title__icontains=query) |
            PostInnovation.objects.filter(user=request.user, content__icontains=query)
        ).order_by('-created_at')
    return render(request, 'innovation/dashboard.html', {
        'posts': posts, 'total': PostInnovation.objects.filter(user=request.user).count(),
        'query': query, 'category': 'Innovation',
    })

@login_required
def edit_innovation(request, pk):
    post = get_object_or_404(PostInnovation, pk=pk, user=request.user)
    if request.method == 'POST':
        post.title   = request.POST.get('title', post.title).strip()
        post.content = request.POST.get('content', post.content).strip()
        post.save()
        return redirect('innovation_dashboard')
    return render(request, 'innovation/edit.html', {'post': post, 'category': 'Innovation'})

@login_required
def delete_innovation(request, pk):
    post = get_object_or_404(PostInnovation, pk=pk, user=request.user)
    if request.method == 'POST':
        post.delete()
    return redirect('innovation_dashboard')

@login_required
def innovation_detail(request, pk):
    post = get_object_or_404(PostInnovation, pk=pk, user=request.user)
    return render(request, 'innovation/detail.html', {'post': post, 'category': 'Innovation'})


# ─────────────────────────────────────────────────────────────────────────────
# Suggestions
# ─────────────────────────────────────────────────────────────────────────────

def create_suggestion(request):
    if request.method == 'POST':
        title     = request.POST.get('title', '').strip()
        content   = request.POST.get('content', '').strip()
        anonymous = request.POST.get('post_as_anonymous') == 'on'
        if title and content:
            PostSuggestions.objects.create(
                user         = None if anonymous else (request.user if request.user.is_authenticated else None),
                title        = title,
                content      = content,
                is_anonymous = anonymous or not request.user.is_authenticated,
            )
        return _post_submit_redirect(request)
    return render(request, 'suggestions/create.html', {'category': 'Suggestions'})

@login_required
def suggestions_dashboard(request):
    query = request.GET.get('q', '')
    posts = PostSuggestions.objects.filter(user=request.user).order_by('-created_at')
    if query:
        posts = (
            PostSuggestions.objects.filter(user=request.user, title__icontains=query) |
            PostSuggestions.objects.filter(user=request.user, content__icontains=query)
        ).order_by('-created_at')
    return render(request, 'suggestions/dashboard.html', {
        'posts': posts, 'total': PostSuggestions.objects.filter(user=request.user).count(),
        'query': query, 'category': 'Suggestions',
    })

@login_required
def edit_suggestion(request, pk):
    post = get_object_or_404(PostSuggestions, pk=pk, user=request.user)
    if request.method == 'POST':
        post.title   = request.POST.get('title', post.title).strip()
        post.content = request.POST.get('content', post.content).strip()
        post.save()
        return redirect('suggestions_dashboard')
    return render(request, 'suggestions/edit.html', {'post': post, 'category': 'Suggestions'})

@login_required
def delete_suggestion(request, pk):
    post = get_object_or_404(PostSuggestions, pk=pk, user=request.user)
    if request.method == 'POST':
        post.delete()
    return redirect('suggestions_dashboard')

@login_required
def suggestion_detail(request, pk):
    post = get_object_or_404(PostSuggestions, pk=pk, user=request.user)
    return render(request, 'suggestions/detail.html', {'post': post, 'category': 'Suggestions'})


# ─────────────────────────────────────────────────────────────────────────────
# Emergency
# ─────────────────────────────────────────────────────────────────────────────

def create_emergency(request):
    if request.method == 'POST':
        title     = request.POST.get('title', '').strip()
        content   = request.POST.get('content', '').strip()
        anonymous = request.POST.get('post_as_anonymous') == 'on'
        if title and content:
            PostEmergency.objects.create(
                user         = None if anonymous else (request.user if request.user.is_authenticated else None),
                title        = title,
                content      = content,
                is_anonymous = anonymous or not request.user.is_authenticated,
            )
        return _post_submit_redirect(request)
    return render(request, 'emergency/create.html', {'category': 'Emergency'})

@login_required
def emergency_dashboard(request):
    query = request.GET.get('q', '')
    posts = PostEmergency.objects.filter(user=request.user).order_by('-created_at')
    if query:
        posts = (
            PostEmergency.objects.filter(user=request.user, title__icontains=query) |
            PostEmergency.objects.filter(user=request.user, content__icontains=query)
        ).order_by('-created_at')
    return render(request, 'emergency/dashboard.html', {
        'posts': posts, 'total': PostEmergency.objects.filter(user=request.user).count(),
        'query': query, 'category': 'Emergency',
    })

@login_required
def edit_emergency(request, pk):
    post = get_object_or_404(PostEmergency, pk=pk, user=request.user)
    if request.method == 'POST':
        post.title   = request.POST.get('title', post.title).strip()
        post.content = request.POST.get('content', post.content).strip()
        post.save()
        return redirect('emergency_dashboard')
    return render(request, 'emergency/edit.html', {'post': post, 'category': 'Emergency'})

@login_required
def delete_emergency(request, pk):
    post = get_object_or_404(PostEmergency, pk=pk, user=request.user)
    if request.method == 'POST':
        post.delete()
    return redirect('emergency_dashboard')

@login_required
def emergency_detail(request, pk):
    post = get_object_or_404(PostEmergency, pk=pk, user=request.user)
    return render(request, 'emergency/detail.html', {'post': post, 'category': 'Emergency'})


# ─────────────────────────────────────────────────────────────────────────────
# Recommendations
# ─────────────────────────────────────────────────────────────────────────────

def create_recommendation(request):
    if request.method == 'POST':
        title     = request.POST.get('title', '').strip()
        content   = request.POST.get('content', '').strip()
        anonymous = request.POST.get('post_as_anonymous') == 'on'
        if title and content:
            PostRecommendations.objects.create(
                user         = None if anonymous else (request.user if request.user.is_authenticated else None),
                title        = title,
                content      = content,
                is_anonymous = anonymous or not request.user.is_authenticated,
            )
        return _post_submit_redirect(request)
    return render(request, 'recommendations/create.html', {'category': 'Recommendations'})

@login_required
def recommendations_dashboard(request):
    query = request.GET.get('q', '')
    posts = PostRecommendations.objects.filter(user=request.user).order_by('-created_at')
    if query:
        posts = (
            PostRecommendations.objects.filter(user=request.user, title__icontains=query) |
            PostRecommendations.objects.filter(user=request.user, content__icontains=query)
        ).order_by('-created_at')
    return render(request, 'recommendations/dashboard.html', {
        'posts': posts, 'total': PostRecommendations.objects.filter(user=request.user).count(),
        'query': query, 'category': 'Recommendations',
    })

@login_required
def edit_recommendation(request, pk):
    post = get_object_or_404(PostRecommendations, pk=pk, user=request.user)
    if request.method == 'POST':
        post.title   = request.POST.get('title', post.title).strip()
        post.content = request.POST.get('content', post.content).strip()
        post.save()
        return redirect('recommendations_dashboard')
    return render(request, 'recommendations/edit.html', {'post': post, 'category': 'Recommendations'})

@login_required
def delete_recommendation(request, pk):
    post = get_object_or_404(PostRecommendations, pk=pk, user=request.user)
    if request.method == 'POST':
        post.delete()
    return redirect('recommendations_dashboard')

@login_required
def recommendation_detail(request, pk):
    post = get_object_or_404(PostRecommendations, pk=pk, user=request.user)
    return render(request, 'recommendations/detail.html', {'post': post, 'category': 'Recommendations'})


# ─────────────────────────────────────────────────────────────────────────────
# Complaints
# ─────────────────────────────────────────────────────────────────────────────

def create_complain(request):
    if request.method == 'POST':
        title     = request.POST.get('title', '').strip()
        content   = request.POST.get('content', '').strip()
        anonymous = request.POST.get('post_as_anonymous') == 'on'
        if title and content:
            PostComplain.objects.create(
                user         = None if anonymous else (request.user if request.user.is_authenticated else None),
                title        = title,
                content      = content,
                is_anonymous = anonymous or not request.user.is_authenticated,
            )
        return _post_submit_redirect(request)
    return render(request, 'complaints/create.html', {'category': 'Complaints'})

@login_required
def complaints_dashboard(request):
    query = request.GET.get('q', '')
    posts = PostComplain.objects.filter(user=request.user).order_by('-created_at')
    if query:
        posts = (
            PostComplain.objects.filter(user=request.user, title__icontains=query) |
            PostComplain.objects.filter(user=request.user, content__icontains=query)
        ).order_by('-created_at')
    return render(request, 'complaints/dashboard.html', {
        'posts': posts, 'total': PostComplain.objects.filter(user=request.user).count(),
        'query': query, 'category': 'Complaints',
    })

@login_required
def edit_complain(request, pk):
    post = get_object_or_404(PostComplain, pk=pk, user=request.user)
    if request.method == 'POST':
        post.title   = request.POST.get('title', post.title).strip()
        post.content = request.POST.get('content', post.content).strip()
        post.save()
        return redirect('complaints_dashboard')
    return render(request, 'complaints/edit.html', {'post': post, 'category': 'Complaints'})

@login_required
def delete_complain(request, pk):
    post = get_object_or_404(PostComplain, pk=pk, user=request.user)
    if request.method == 'POST':
        post.delete()
    return redirect('complaints_dashboard')

@login_required
def complain_detail(request, pk):
    post = get_object_or_404(PostComplain, pk=pk, user=request.user)
    return render(request, 'complaints/detail.html', {'post': post, 'category': 'Complaints'})


# ─────────────────────────────────────────────────────────────────────────────
# Others
# ─────────────────────────────────────────────────────────────────────────────

def create_others(request):
    if request.method == 'POST':
        title     = request.POST.get('title', '').strip()
        content   = request.POST.get('content', '').strip()
        anonymous = request.POST.get('post_as_anonymous') == 'on'
        if title and content:
            PostOthers.objects.create(
                user         = None if anonymous else (request.user if request.user.is_authenticated else None),
                title        = title,
                content      = content,
                is_anonymous = anonymous or not request.user.is_authenticated,
            )
        return _post_submit_redirect(request)
    return render(request, 'others/create.html', {'category': 'Others'})

@login_required
def others_dashboard(request):
    query = request.GET.get('q', '')
    posts = PostOthers.objects.filter(user=request.user).order_by('-created_at')
    if query:
        posts = (
            PostOthers.objects.filter(user=request.user, title__icontains=query) |
            PostOthers.objects.filter(user=request.user, content__icontains=query)
        ).order_by('-created_at')
    return render(request, 'others/dashboard.html', {
        'posts': posts, 'total': PostOthers.objects.filter(user=request.user).count(),
        'query': query, 'category': 'Others',
    })

@login_required
def edit_others(request, pk):
    post = get_object_or_404(PostOthers, pk=pk, user=request.user)
    if request.method == 'POST':
        post.title   = request.POST.get('title', post.title).strip()
        post.content = request.POST.get('content', post.content).strip()
        post.save()
        return redirect('others_dashboard')
    return render(request, 'others/edit.html', {'post': post, 'category': 'Others'})

@login_required
def delete_others(request, pk):
    post = get_object_or_404(PostOthers, pk=pk, user=request.user)
    if request.method == 'POST':
        post.delete()
    return redirect('others_dashboard')

@login_required
def others_detail(request, pk):
    post = get_object_or_404(PostOthers, pk=pk, user=request.user)
    return render(request, 'others/detail.html', {'post': post, 'category': 'Others'})


# ─────────────────────────────────────────────────────────────────────────────
# Reporting
# ─────────────────────────────────────────────────────────────────────────────

def post_reporting(request):
    if request.method == 'POST':
        anonymous = request.POST.get('post_as_anonymous') == 'on'
        Reporting.objects.create(
            user                = None if anonymous else (request.user if request.user.is_authenticated else None),
            is_anonymous        = anonymous or not request.user.is_authenticated,
            report_name         = request.POST.get('report_name', '').strip(),
            location            = request.POST.get('location', '').strip(),
            report_description  = request.POST.get('report_description', '').strip(),
            first_name          = request.POST.get('first_name', '').strip(),
            last_name           = request.POST.get('last_name', '').strip(),
            registration_number = request.POST.get('registration_number', '').strip(),
            department          = request.POST.get('department', '').strip(),
            school              = request.POST.get('school', '').strip(),
            telephone           = request.POST.get('telephone', '').strip(),
            email               = request.POST.get('email', '').strip(),
        )
        return _post_submit_redirect(request)
    return render(request, 'post_reporting.html')

@login_required
def reporting_dashboard(request):
    query   = request.GET.get('q', '')
    reports = Reporting.objects.filter(user=request.user).order_by('-created_at')
    if query:
        reports = (
            Reporting.objects.filter(user=request.user, report_name__icontains=query) |
            Reporting.objects.filter(user=request.user, report_description__icontains=query) |
            Reporting.objects.filter(user=request.user, location__icontains=query)
        ).order_by('-created_at')
    return render(request, 'reporting/dashboard.html', {
        'reports':  reports,
        'total':    Reporting.objects.filter(user=request.user).count(),
        'query':    query,
        'category': 'Reporting',
    })

@login_required
def edit_reporting(request, pk):
    report = get_object_or_404(Reporting, pk=pk, user=request.user)
    if request.method == 'POST':
        report.report_name         = request.POST.get('report_name',         report.report_name).strip()
        report.location            = request.POST.get('location',            report.location).strip()
        report.report_description  = request.POST.get('report_description',  report.report_description).strip()
        report.first_name          = request.POST.get('first_name',          report.first_name).strip()
        report.last_name           = request.POST.get('last_name',           report.last_name).strip()
        report.registration_number = request.POST.get('registration_number', report.registration_number).strip()
        report.department          = request.POST.get('department',          report.department).strip()
        report.school              = request.POST.get('school',              report.school).strip()
        report.telephone           = request.POST.get('telephone',           report.telephone).strip()
        report.email               = request.POST.get('email',               report.email).strip()
        report.save()
        return redirect('reporting_dashboard')
    return render(request, 'reporting/edit.html', {'report': report, 'category': 'Reporting'})

@login_required
def delete_reporting(request, pk):
    report = get_object_or_404(Reporting, pk=pk, user=request.user)
    if request.method == 'POST':
        report.delete()
    return redirect('reporting_dashboard')

@login_required
def reporting_detail(request, pk):
    report = get_object_or_404(Reporting, pk=pk, user=request.user)
    return render(request, 'reporting/detail.html', {'report': report, 'category': 'Reporting'})


@login_required
def analytics_partial(request):
    # Manual role check — avoids redirect on AJAX
    try:
        if request.user.userprofile.role != 'admin':
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden('Forbidden')
    except Exception:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden('Forbidden')

    return render(request, 'admin/partials/analytics.html', {
        'total_users': User.objects.count(),
        'total_posts': (
            PostAwareness.objects.count() +
            PostInnovation.objects.count() +
            PostSuggestions.objects.count() +
            PostEmergency.objects.count() +
            PostRecommendations.objects.count() +
            PostComplain.objects.count() +
            PostOthers.objects.count() +
            Reporting.objects.count()
        ),
        'total_pending': (
            PostAwareness.objects.filter(status='pending').count() +
            PostInnovation.objects.filter(status='pending').count() +
            PostSuggestions.objects.filter(status='pending').count() +
            PostEmergency.objects.filter(status='pending').count() +
            PostRecommendations.objects.filter(status='pending').count() +
            PostComplain.objects.filter(status='pending').count() +
            PostOthers.objects.filter(status='pending').count() +
            Reporting.objects.filter(status='pending').count()
        ),
    })


    # ─────────────────────────────────────────────────────────────────────────────
# ADD THESE VIEWS TO YOUR views.py  (paste after analytics_partial)
# ─────────────────────────────────────────────────────────────────────────────




def _admin_partial_check(request):
    """Returns None if OK, HttpResponseForbidden otherwise."""
    try:
        if request.user.userprofile.role != 'admin':
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden('Forbidden')
    except Exception:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden('Forbidden')
    return None


def _base_admin_ctx():
    """Shared context passed to most admin partials."""
    now      = timezone.now()
    week_ago = now - timedelta(days=7)

    category_stats = [
        {'label': 'Awareness',       'slug': 'awareness',      'total': PostAwareness.objects.count(),       'pending': PostAwareness.objects.filter(status='pending').count(),       'resolved': PostAwareness.objects.filter(status='resolved').count(),       'this_week': PostAwareness.objects.filter(created_at__gte=week_ago).count()},
        {'label': 'Innovation',      'slug': 'innovation',     'total': PostInnovation.objects.count(),      'pending': PostInnovation.objects.filter(status='pending').count(),      'resolved': PostInnovation.objects.filter(status='resolved').count(),      'this_week': PostInnovation.objects.filter(created_at__gte=week_ago).count()},
        {'label': 'Suggestions',     'slug': 'suggestion',     'total': PostSuggestions.objects.count(),     'pending': PostSuggestions.objects.filter(status='pending').count(),     'resolved': PostSuggestions.objects.filter(status='resolved').count(),     'this_week': PostSuggestions.objects.filter(created_at__gte=week_ago).count()},
        {'label': 'Emergency',       'slug': 'emergency',      'total': PostEmergency.objects.count(),       'pending': PostEmergency.objects.filter(status='pending').count(),       'resolved': PostEmergency.objects.filter(status='resolved').count(),       'this_week': PostEmergency.objects.filter(created_at__gte=week_ago).count()},
        {'label': 'Recommendations', 'slug': 'recommendation', 'total': PostRecommendations.objects.count(), 'pending': PostRecommendations.objects.filter(status='pending').count(), 'resolved': PostRecommendations.objects.filter(status='resolved').count(), 'this_week': PostRecommendations.objects.filter(created_at__gte=week_ago).count()},
        {'label': 'Complaints',      'slug': 'complaint',      'total': PostComplain.objects.count(),        'pending': PostComplain.objects.filter(status='pending').count(),        'resolved': PostComplain.objects.filter(status='resolved').count(),        'this_week': PostComplain.objects.filter(created_at__gte=week_ago).count()},
        {'label': 'Others',          'slug': 'others',         'total': PostOthers.objects.count(),          'pending': PostOthers.objects.filter(status='pending').count(),          'resolved': PostOthers.objects.filter(status='resolved').count(),          'this_week': PostOthers.objects.filter(created_at__gte=week_ago).count()},
        {'label': 'Reporting',       'slug': 'reporting',      'total': Reporting.objects.count(),           'pending': Reporting.objects.filter(status='pending').count(),           'resolved': Reporting.objects.filter(status='resolved').count(),           'this_week': Reporting.objects.filter(created_at__gte=week_ago).count()},
    ]
    total_posts    = sum(c['total']     for c in category_stats)
    total_pending  = sum(c['pending']   for c in category_stats)
    total_resolved = sum(c['resolved']  for c in category_stats)
    total_new      = sum(c['this_week'] for c in category_stats)
    staff_count    = UserProfile.objects.filter(role='staff').count()
    admin_count    = UserProfile.objects.filter(role='admin').count()
    total_users    = User.objects.count()
    return {
        'category_stats':  category_stats,
        'total_posts':     total_posts,
        'total_pending':   total_pending,
        'total_resolved':  total_resolved,
        'total_new':       total_new,
        'staff_count':     staff_count,
        'admin_count':     admin_count,
        'total_users':     total_users,
    }


# ── NOTIFICATIONS ──────────────────────────────────────────────────────────────
@login_required
@admin_required
def notifications_partial(request):
    ctx = _base_admin_ctx()
    # Derive simple notification counts from real data
    ctx['unread_count']    = ctx['total_pending']
    ctx['emergency_count'] = PostEmergency.objects.filter(status='pending').count()
    ctx['resolved_today']  = StaffFeedback.objects.filter(
        created_at__date=timezone.now().date()
    ).count()
    ctx['total_notifications'] = ctx['total_pending'] + ctx['resolved_today']
    ctx['notifications'] = []  # Real notification model not yet defined; template shows demo
    return render(request, 'admin/partials/da', ctx)


# ── ACTIVITY TIMELINE ──────────────────────────────────────────────────────────
@login_required
@admin_required
def activity_partial(request):
    now = timezone.now()
    ctx = _base_admin_ctx()
    ctx['events_today']    = StaffFeedback.objects.filter(created_at__date=now.date()).count()
    ctx['resolved_today']  = StaffFeedback.objects.filter(created_at__date=now.date(), new_status='resolved').count()
    ctx['new_users_today'] = User.objects.filter(date_joined__date=now.date()).count()
    ctx['staff_actions']   = StaffFeedback.objects.filter(created_at__date=now.date()).count()
    ctx['activity_log']    = []  # Template shows demo data; plug in a real ActivityLog model later
    return render(request, 'admin/partials/activity.html', ctx)


# ── ALL SUBMISSIONS ────────────────────────────────────────────────────────────
@login_required
@admin_required
def all_submissions_partial(request):
    return render(request, 'admin/partials/all-submissions.html', _base_admin_ctx())


# ── CATEGORY PARTIALS (innovations / suggestions / complaints / emergencies / awareness / anonymous) ──
def _cat_partial(request, slug, label, icon, desc):
    err = _admin_partial_check(request)
    if err: return err
    if slug not in CATEGORY_MAP:
        from django.http import Http404
        raise Http404
    Model, _ = CATEGORY_MAP[slug]
    posts = Model.objects.order_by('-created_at').select_related('user')[:50]
    ctx   = _base_admin_ctx()
    ctx.update({
        'posts':          posts,
        'category_slug':  slug,
        'category_label': label,
        'category_icon':  icon,
        'category_desc':  desc,
        'cat_total':      Model.objects.count(),
        'cat_pending':    Model.objects.filter(status='pending').count(),
        'cat_resolved':   Model.objects.filter(status='resolved').count(),
        'cat_this_week':  Model.objects.filter(created_at__gte=timezone.now()-timedelta(days=7)).count(),
    })
    return render(request, 'admin/partials/category_detail.html', ctx)


@login_required
def innovations_partial(request):
    return _cat_partial(request, 'innovation', 'Innovations', '💡', 'Innovation ideas submitted by users')

@login_required
def suggestions_partial(request):
    return _cat_partial(request, 'suggestion', 'Suggestions', '✦', 'User suggestions awaiting review')

@login_required
def complaints_partial(request):
    return _cat_partial(request, 'complaint', 'Complaints', '⚑', 'Filed complaints and their status')

@login_required
def emergencies_partial(request):
    return _cat_partial(request, 'emergency', 'Emergencies', '⚠', 'High-priority emergency submissions')

@login_required
def awareness_partial(request):
    return _cat_partial(request, 'awareness', 'Awareness', '◎', 'Awareness posts and campaigns')

@login_required
def anonymous_partial(request):
    err = _admin_partial_check(request)
    if err: return err
    # Gather anonymous posts across all categories
    anon_posts = []
    for slug, (Model, label) in CATEGORY_MAP.items():
        qs = Model.objects.filter(is_anonymous=True).order_by('-created_at')[:10]
        for p in qs:
            p.category_slug  = slug
            p.category_label = label
            anon_posts.append(p)
    anon_posts.sort(key=lambda x: x.created_at, reverse=True)
    ctx = _base_admin_ctx()
    ctx['anon_posts']         = anon_posts[:40]
    ctx['category_slug']      = 'anonymous'
    ctx['category_label']     = 'Anonymous'
    ctx['category_icon']      = '◌'
    ctx['category_desc']      = 'Anonymous submissions from all categories'
    ctx['posts']              = anon_posts[:40]
    ctx['cat_total']          = sum(
        CATEGORY_MAP[s][0].objects.filter(is_anonymous=True).count() for s in CATEGORY_MAP
    )
    ctx['cat_pending']        = 0
    ctx['cat_resolved']       = 0
    ctx['cat_this_week']      = 0
    return render(request, 'admin/partials/category_detail.html', ctx)


# ── WORKFLOW: PENDING / ASSIGNED / RESOLVED / ARCHIVED ────────────────────────
def _workflow_partial(request, status_key, title, desc, color):
    err = _admin_partial_check(request)
    if err: return err
    ctx = _base_admin_ctx()
    # Build per-category count for this workflow status
    STATUS_MAP = {
        'pending':  'pending',
        'assigned': 'in_review',
        'resolved': 'resolved',
        'archived': 'rejected',
    }
    db_status = STATUS_MAP.get(status_key, status_key)
    category_workflow = []
    total = 0
    week_ago = timezone.now() - timedelta(days=7)
    week = 0
    for slug, (Model, label) in CATEGORY_MAP.items():
        count = Model.objects.filter(status=db_status).count()
        category_workflow.append({'slug': slug, 'label': label, 'count': count})
        total += count
        week  += Model.objects.filter(status=db_status, created_at__gte=week_ago).count()
    ctx.update({
        'workflow_title':    title,
        'workflow_desc':     desc,
        'workflow_status':   db_status,
        'workflow_total':    total,
        'workflow_week':     week,
        'workflow_sub':      f'Across all categories',
        'stat_color':        color,
        'category_workflow': category_workflow,
    })
    return render(request, 'admin/partials/workflow.html', ctx)

@login_required
def pending_partial(request):
    return _workflow_partial(request, 'pending', 'Pending Review', 'Submissions awaiting admin review', 'orange')

@login_required
def assigned_partial(request):
    return _workflow_partial(request, 'assigned', 'Assigned (In Review)', 'Submissions currently being reviewed by staff', 'blue')

@login_required
def resolved_partial(request):
    return _workflow_partial(request, 'resolved', 'Resolved', 'Successfully resolved submissions', 'green')

@login_required
def archived_partial(request):
    return _workflow_partial(request, 'archived', 'Archived / Rejected', 'Archived and rejected records', 'red')


# ── DEPARTMENTS ────────────────────────────────────────────────────────────────
@login_required
@admin_required
def departments_partial(request):
    return render(request, 'admin/partials/departments.html', _base_admin_ctx())


# ── PERFORMANCE ────────────────────────────────────────────────────────────────
@login_required
@admin_required
def performance_partial(request):
    ctx = _base_admin_ctx()
    # Staff leaderboard: count StaffFeedback by staff
    ctx['staff_leaderboard'] = (
        StaffFeedback.objects
        .values('staff__username')
        .annotate(count=Count('id'))
        .order_by('-count')[:10]
    )
    return render(request, 'admin/partials/performance.html', ctx)


# ── STAFF RESPONSES ────────────────────────────────────────────────────────────
@login_required
@admin_required
def staff_responses_partial(request):
    ctx = _base_admin_ctx()
    ctx['recent_feedback']  = StaffFeedback.objects.select_related('staff').order_by('-created_at')[:50]
    ctx['total_feedback']   = StaffFeedback.objects.count()
    ctx['emails_sent']      = StaffFeedback.objects.filter(email_sent=True).count()
    return render(request, 'admin/partials/staff-responses.html', ctx)


# ── STAFF MANAGEMENT ──────────────────────────────────────────────────────────
@login_required
@admin_required
def staff_management_partial(request):
    staff_users = User.objects.filter(userprofile__role__in=['staff', 'admin']).select_related('userprofile').order_by('-date_joined')
    ctx = _base_admin_ctx()
    ctx['staff_users']     = staff_users
    ctx['staff_feedback']  = StaffFeedback.objects.select_related('staff').order_by('-created_at')[:20]
    return render(request, 'admin/partials/staff-management.html', ctx)


# ── ROLES & PERMISSIONS ───────────────────────────────────────────────────────
@login_required
@admin_required
def roles_partial(request):
    ctx = _base_admin_ctx()
    ctx['regular_count'] = UserProfile.objects.filter(role='regular_user').count()
    return render(request, 'admin/partials/roles.html', ctx)


# ── EXPORT ────────────────────────────────────────────────────────────────────
@login_required
@admin_required
def export_partial(request):
    return render(request, 'admin/partials/export.html', _base_admin_ctx())


# ── MONTHLY REPORTS ───────────────────────────────────────────────────────────
@login_required
@admin_required
def monthly_partial(request):
    ctx = _base_admin_ctx()
    # Build last 6 months breakdown
    import calendar
    months = []
    now = timezone.now()
    for i in range(5, -1, -1):
        d = now.replace(day=1) - timedelta(days=1) * (i * 30)
        start = d.replace(day=1)
        end   = (start + timedelta(days=32)).replace(day=1)
        total = sum(
            CATEGORY_MAP[s][0].objects.filter(created_at__gte=start, created_at__lt=end).count()
            for s in CATEGORY_MAP
        )
        months.append({'label': start.strftime('%b %Y'), 'total': total})
    ctx['months'] = months
    return render(request, 'admin/partials/monthly.html', ctx)


# ── AUDIT LOGS ────────────────────────────────────────────────────────────────
@login_required
@admin_required
def audit_partial(request):
    ctx = _base_admin_ctx()
    ctx['audit_entries'] = StaffFeedback.objects.select_related('staff').order_by('-created_at')[:100]
    return render(request, 'admin/partials/audit.html', ctx)


# ── SETTINGS ──────────────────────────────────────────────────────────────────
@login_required
@admin_required
def settings_partial(request):
    return render(request, 'admin/partials/settings.html', _base_admin_ctx())


# ── EMAIL TEMPLATES ───────────────────────────────────────────────────────────
@login_required
@admin_required
def email_templates_partial(request):
    return render(request, 'admin/partials/email-templates.html', _base_admin_ctx())


# ── SECURITY ──────────────────────────────────────────────────────────────────
@login_required
@admin_required
def security_partial(request):
    ctx = _base_admin_ctx()
    ctx['recent_feedback']   = StaffFeedback.objects.select_related('staff').order_by('-created_at')[:10]
    ctx['active_sessions']   = 1  # Replace with real session count if using django-session
    ctx['failed_logins']     = 0
    return render(request, 'admin/partials/security.html', ctx)