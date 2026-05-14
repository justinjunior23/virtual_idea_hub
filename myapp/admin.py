from django.contrib import admin
from .models import UserProfile
from .models import (
    EmailOTP,
    Idea,
    PostAwareness,
    PostComplain,
    PostEmergency,
    PostInnovation,
    PostOthers,
    PostRecommendations,
    PostSuggestions,
    Reporting,
    StaffFeedback,
    UserProfile,
)


# ═══════════════════════════════════════════════════════════════════════════════
# USER / AUTH
# ═══════════════════════════════════════════════════════════════════════════════

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display  = ('user', 'role')
    list_filter   = ('role',)
    search_fields = ('user__username', 'user__email')


@admin.register(EmailOTP)
class EmailOTPAdmin(admin.ModelAdmin):
    list_display  = ('user', 'code', 'created_at')
    search_fields = ('user__username',)
    readonly_fields = ('created_at',)


# ═══════════════════════════════════════════════════════════════════════════════
# IDEA
# ═══════════════════════════════════════════════════════════════════════════════

@admin.register(Idea)
class IdeaAdmin(admin.ModelAdmin):
    list_display  = ('title', 'created_at')
    search_fields = ('title',)


# ═══════════════════════════════════════════════════════════════════════════════
# POST CATEGORIES  (shared config via mixin)
# ═══════════════════════════════════════════════════════════════════════════════

class BasePostAdmin(admin.ModelAdmin):
    list_display  = ('title', 'user', 'status', 'is_anonymous', 'created_at')
    list_filter   = ('status', 'is_anonymous')
    search_fields = ('title', 'content')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(PostAwareness)
class PostAwarenessAdmin(BasePostAdmin):
    pass

@admin.register(PostInnovation)
class PostInnovationAdmin(BasePostAdmin):
    pass

@admin.register(PostSuggestions)
class PostSuggestionsAdmin(BasePostAdmin):
    pass

@admin.register(PostEmergency)
class PostEmergencyAdmin(BasePostAdmin):
    pass

@admin.register(PostRecommendations)
class PostRecommendationsAdmin(BasePostAdmin):
    pass

@admin.register(PostComplain)
class PostComplainAdmin(BasePostAdmin):
    pass

@admin.register(PostOthers)
class PostOthersAdmin(BasePostAdmin):
    pass


# ═══════════════════════════════════════════════════════════════════════════════
# REPORTING
# ═══════════════════════════════════════════════════════════════════════════════

@admin.register(Reporting)
class ReportingAdmin(admin.ModelAdmin):
    list_display  = ('report_name', 'user', 'status', 'location', 'is_anonymous', 'created_at')
    list_filter   = ('status', 'is_anonymous')
    search_fields = ('report_name', 'report_description', 'location', 'email')
    readonly_fields = ('created_at', 'updated_at')


# ═══════════════════════════════════════════════════════════════════════════════
# STAFF FEEDBACK
# ═══════════════════════════════════════════════════════════════════════════════

@admin.register(StaffFeedback)
class StaffFeedbackAdmin(admin.ModelAdmin):
    list_display  = ('staff', 'category', 'post_id', 'new_status', 'email_sent', 'created_at')
    list_filter   = ('category', 'new_status', 'email_sent')
    search_fields = ('message', 'staff__username')
    readonly_fields = ('created_at',)