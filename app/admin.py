# app/admin.py
from __future__ import annotations

from django.apps import apps
from django.contrib import admin
from django.db.models import Count
from django.utils.html import format_html


def _get_model(name: str):
    """Safely get a model from this Django app without crashing if it doesn't exist."""
    try:
        return apps.get_model("app", name)
    except LookupError:
        return None


Election = _get_model("Election")
Position = _get_model("Position")
Candidate = _get_model("Candidate")
Voter = _get_model("Voter")
VotingSession = _get_model("VotingSession")
Vote = _get_model("Vote")
PhoneOTP = _get_model("PhoneOTP")


class BaseReadOnlyCreatedAdmin(admin.ModelAdmin):
    readonly_fields = ("created_at",)
    list_per_page = 50


# -------------------------
# Actions
# -------------------------
def make_active(modeladmin, request, queryset):
    queryset.update(is_active=True)


def make_inactive(modeladmin, request, queryset):
    queryset.update(is_active=False)


make_active.short_description = "Mark selected as ACTIVE"
make_inactive.short_description = "Mark selected as INACTIVE"


# -------------------------
# Election
# -------------------------
if Election is not None:
    @admin.register(Election)
    class ElectionAdmin(BaseReadOnlyCreatedAdmin):
        list_display = ("id", "name", "status", "access_mode", "start_at", "end_at", "created_at")
        list_filter = ("status", "access_mode")
        search_fields = ("name",)
        ordering = ("-created_at",)

        fieldsets = (
            ("Election", {"fields": ("name", "status", "access_mode")}),
            ("Schedule", {"fields": ("start_at", "end_at")}),
            ("Meta", {"fields": ("created_at",)}),
        )


# -------------------------
# Position
# -------------------------
if Position is not None:
    @admin.register(Position)
    class PositionAdmin(BaseReadOnlyCreatedAdmin):
        list_display = ("id", "election", "name", "sort_order", "created_at")
        list_filter = ("election",)
        search_fields = ("name",)
        ordering = ("election", "sort_order", "name")

        fieldsets = (
            ("Position", {"fields": ("election", "name", "sort_order")}),
            ("Meta", {"fields": ("created_at",)}),
        )


# -------------------------
# Candidate
# -------------------------
if Candidate is not None:
    @admin.register(Candidate)
    class CandidateAdmin(BaseReadOnlyCreatedAdmin):
        actions = (make_active, make_inactive)

        list_display = (
            "id",
            "thumb",
            "full_name",
            "election",
            "position",
            "university",
            "study_year",
            "is_active",
            "vote_count",
            "created_at",
        )
        list_filter = ("election", "position", "is_active", "university")
        search_fields = ("full_name", "bio_short", "bio", "university", "image_url")
        ordering = ("full_name",)

        fieldsets = (
            ("Candidate", {"fields": ("election", "position", "full_name", "is_active")}),
            ("Education", {"fields": ("university", "study_year")}),
            ("Image", {"fields": ("image_url",)}),
            ("Bio (Short)", {"fields": ("bio_short",)}),
            ("Bio (Full)", {"fields": ("bio",)}),
            ("Meta", {"fields": ("created_at",)}),
        )

        def get_queryset(self, request):
            qs = super().get_queryset(request)
            # Vote model uses related_name="votes" on candidate FK
            return qs.annotate(_votes=Count("votes"))

        @admin.display(description="Votes", ordering="_votes")
        def vote_count(self, obj):
            return getattr(obj, "_votes", 0)

        @admin.display(description="Photo")
        def thumb(self, obj):
            url = getattr(obj, "image_url", None)
            if url:
                return format_html(
                    '<img src="{}" style="width:56px;height:40px;object-fit:cover;border-radius:8px;border:1px solid #e5e7eb;" />',
                    url,
                )
            initial = (obj.full_name[:1] if obj.full_name else "-").upper()
            return format_html(
                '<div style="width:56px;height:40px;border-radius:8px;border:1px solid #e5e7eb;background:#f3f4f6;display:flex;align-items:center;justify-content:center;color:#6b7280;font-weight:700;">{}</div>',
                initial,
            )


# -------------------------
# Voter
# -------------------------
if Voter is not None:
    @admin.register(Voter)
    class VoterAdmin(BaseReadOnlyCreatedAdmin):
        list_display = ("id", "full_name", "voter_code", "is_active", "created_at")
        list_filter = ("is_active",)
        search_fields = ("full_name", "voter_code")
        ordering = ("full_name",)

        fieldsets = (
            ("Voter", {"fields": ("full_name", "voter_code", "is_active")}),
            ("Meta", {"fields": ("created_at",)}),
        )


# -------------------------
# VotingSession
# -------------------------
if VotingSession is not None:
    @admin.register(VotingSession)
    class VotingSessionAdmin(BaseReadOnlyCreatedAdmin):
        list_display = ("id", "election", "token", "expires_at", "voter_name", "phone", "created_at")
        list_filter = ("election",)
        search_fields = ("token", "phone")
        ordering = ("-created_at",)

        @admin.display(description="Voter")
        def voter_name(self, obj):
            return getattr(getattr(obj, "voter", None), "full_name", None) or "-"


# -------------------------
# Vote
# -------------------------
if Vote is not None:
    @admin.register(Vote)
    class VoteAdmin(BaseReadOnlyCreatedAdmin):
        list_display = ("id", "election", "position", "candidate", "voter_name", "voter_phone", "created_at")
        list_filter = ("election", "position")
        search_fields = ("voter_phone", "candidate__full_name")
        ordering = ("-created_at",)

        @admin.display(description="Voter")
        def voter_name(self, obj):
            return getattr(getattr(obj, "voter", None), "full_name", None) or "-"


# -------------------------
# Phone OTP
# -------------------------
if PhoneOTP is not None:
    @admin.register(PhoneOTP)
    class PhoneOTPAdmin(BaseReadOnlyCreatedAdmin):
        list_display = ("id", "election", "phone", "code", "is_used", "expires_at", "created_at")
        list_filter = ("election", "is_used")
        search_fields = ("phone", "code")
        ordering = ("-created_at",)