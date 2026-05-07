from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('regular_user', 'Regular User'),
        ('staff',        'Staff'),
        ('admin',        'Admin'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='regular_user')

    def __str__(self):
        return f"{self.user.username} ({self.role})"


class EmailOTP(models.Model):
    user       = models.OneToOneField(User, on_delete=models.CASCADE)
    code       = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_expired(self):
        return timezone.now() > self.created_at + timezone.timedelta(minutes=10)

    def __str__(self):
        return f"OTP for {self.user.username}"



class BasePost(models.Model):
    STATUS_CHOICES = [
        ('pending',   'Pending'),
        ('in_review', 'In Review'),
        ('resolved',  'Resolved'),
        ('rejected',  'Rejected'),
    ]

    user         = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    title        = models.CharField(max_length=255)
    content      = models.TextField()
    is_anonymous = models.BooleanField(default=False)
    status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def __str__(self):
        return self.title



class PostAwareness(BasePost):
    class Meta:
        verbose_name        = 'Awareness Post'
        verbose_name_plural = 'Awareness Posts'
        ordering            = ['-created_at']


class PostInnovation(BasePost):
    class Meta:
        verbose_name        = 'Innovation Post'
        verbose_name_plural = 'Innovation Posts'
        ordering            = ['-created_at']


class PostSuggestions(BasePost):
    class Meta:
        verbose_name        = 'Suggestion'
        verbose_name_plural = 'Suggestions'
        ordering            = ['-created_at']


class PostEmergency(BasePost):
    class Meta:
        verbose_name        = 'Emergency Post'
        verbose_name_plural = 'Emergency Posts'
        ordering            = ['-created_at']


class PostRecommendations(BasePost):
    class Meta:
        verbose_name        = 'Recommendation'
        verbose_name_plural = 'Recommendations'
        ordering            = ['-created_at']


class PostComplain(BasePost):
    class Meta:
        verbose_name        = 'Complaint'
        verbose_name_plural = 'Complaints'
        ordering            = ['-created_at']


class PostOthers(BasePost):
    class Meta:
        verbose_name        = 'Other Post'
        verbose_name_plural = 'Other Posts'
        ordering            = ['-created_at']




class Reporting(models.Model):
    STATUS_CHOICES = [
        ('pending',   'Pending'),
        ('in_review', 'In Review'),
        ('resolved',  'Resolved'),
        ('rejected',  'Rejected'),
    ]

    user                = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    is_anonymous        = models.BooleanField(default=False)
    status              = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    report_name         = models.CharField(max_length=255)
    location            = models.CharField(max_length=255, blank=True)
    report_description  = models.TextField()

    # Reporter contact info (used when anonymous or no linked user)
    first_name          = models.CharField(max_length=100, blank=True)
    last_name           = models.CharField(max_length=100, blank=True)
    registration_number = models.CharField(max_length=100, blank=True)
    department          = models.CharField(max_length=100, blank=True)
    school              = models.CharField(max_length=100, blank=True)
    telephone           = models.CharField(max_length=30,  blank=True)
    email               = models.EmailField(blank=True)

    created_at          = models.DateTimeField(auto_now_add=True)
    updated_at          = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Report'
        verbose_name_plural = 'Reports'
        ordering            = ['-created_at']

    def __str__(self):
        return self.report_name



class StaffFeedback(models.Model):
    staff      = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='feedbacks_given')
    category   = models.CharField(max_length=50)   # matches CATEGORY_MAP slug
    post_id    = models.PositiveIntegerField()      # generic FK — works across all post models
    message    = models.TextField()
    new_status = models.CharField(max_length=20)
    email_sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Staff Feedback'
        verbose_name_plural = 'Staff Feedback'
        ordering            = ['-created_at']

    def __str__(self):
        return f"{self.staff} → {self.category}#{self.post_id} ({self.new_status})"



class Idea(models.Model):
    title      = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title