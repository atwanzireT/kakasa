from __future__ import annotations

from django.contrib import admin
from django.db.models import Count
from django.utils import timezone

from .models import (
    Election,
    Position,
    Candidate,
    Voter,
    ElectionEmailWhitelist,
    EmailOTP,
    VotingSession,
    Vote,
)


@admin.register(Election)
class ElectionAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "status",
        "access_mode",
        "require_email_otp",
        "start_at",
        "end_at",
        "is_open_now_admin",
        "created_at",
    )
    list_filter = ("status", "access_mode", "require_email_otp")
    search_fields = ("name",)
    ordering = ("-created_at",)
    date_hierarchy = "created_at"

    fieldsets = (
        ("Election", {"fields": ("name", "status", "start_at", "end_at")}),
        ("Access Control", {"fields": ("access_mode", "allowed_email_domains", "require_email_otp")}),
        ("Meta", {"fields": ("created_at",), "classes": ("collapse",)}),
    )
    readonly_fields = ("created_at",)

    @admin.display(boolean=True, description="Open now?")
    def is_open_now_admin(self, obj: Election) -> bool:
        return obj.is_open_now()


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ("get_name_display", "election", "sort_order", "created_at")
    list_filter = ("election", "name")
    search_fields = ("election__name",)
    ordering = ("election", "sort_order", "name")
    readonly_fields = ("created_at",)


@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    list_display = (
        "full_name",
        "position",
        "election",
        "is_active",
        "photo_url",
        "created_at",
    )
    list_filter = ("election", "position", "is_active")
    search_fields = ("full_name", "election__name")
    ordering = ("election", "position__sort_order", "full_name")

    fieldsets = (
        ("Candidate", {"fields": ("full_name", "photo_url", "bio_short", "bio", "manifesto", "is_active")}),
        ("Election & Position", {"fields": ("election", "position")}),
        ("Meta", {"fields": ("created_at",), "classes": ("collapse",)}),
    )
    readonly_fields = ("created_at",)


@admin.register(Voter)
class VoterAdmin(admin.ModelAdmin):
    list_display = ("full_name", "voter_code", "is_active", "votes_count", "created_at")
    list_filter = ("is_active",)
    search_fields = ("full_name", "voter_code")
    ordering = ("full_name",)
    date_hierarchy = "created_at"
    readonly_fields = ("created_at",)
    actions = ("activate_voters", "deactivate_voters")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(_votes_count=Count("votes"))

    @admin.display(description="Votes")
    def votes_count(self, obj: Voter) -> int:
        return getattr(obj, "_votes_count", 0)

    @admin.action(description="Activate selected voters")
    def activate_voters(self, request, queryset):
        queryset.update(is_active=True)

    @admin.action(description="Deactivate selected voters")
    def deactivate_voters(self, request, queryset):
        queryset.update(is_active=False)


@admin.register(ElectionEmailWhitelist)
class ElectionEmailWhitelistAdmin(admin.ModelAdmin):
    list_display = ("email", "election", "is_active", "created_at")
    list_filter = ("election", "is_active")
    search_fields = ("email", "election__name")
    ordering = ("election", "email")
    readonly_fields = ("created_at",)
    actions = ("activate_emails", "deactivate_emails")

    @admin.action(description="Activate selected emails")
    def activate_emails(self, request, queryset):
        queryset.update(is_active=True)

    @admin.action(description="Deactivate selected emails")
    def deactivate_emails(self, request, queryset):
        queryset.update(is_active=False)


@admin.register(EmailOTP)
class EmailOTPAdmin(admin.ModelAdmin):
    list_display = ("email", "election", "code", "expires_at", "used_at", "is_valid_admin", "created_at")
    list_filter = ("election",)
    search_fields = ("email", "election__name", "code")
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)

    @admin.display(boolean=True, description="Valid?")
    def is_valid_admin(self, obj: EmailOTP) -> bool:
        return obj.is_valid()


@admin.register(VotingSession)
class VotingSessionAdmin(admin.ModelAdmin):
    list_display = (
        "election",
        "identity",
        "short_token",
        "expires_at",
        "is_valid_admin",
        "created_at",
    )
    list_filter = ("election",)
    search_fields = ("token", "email", "voter__full_name", "voter__voter_code", "election__name")
    ordering = ("-created_at",)
    readonly_fields = ("token", "created_at")

    @admin.display(description="Identity")
    def identity(self, obj: VotingSession) -> str:
        if obj.voter_id:
            return f"{obj.voter.full_name} ({obj.voter.voter_code})"
        return obj.email or "-"

    @admin.display(description="Token")
    def short_token(self, obj: VotingSession) -> str:
        return f"{obj.token[:10]}…"

    @admin.display(boolean=True, description="Valid?")
    def is_valid_admin(self, obj: VotingSession) -> bool:
        return obj.expires_at > timezone.now()


@admin.register(Vote)
class VoteAdmin(admin.ModelAdmin):
    list_display = ("election", "position", "candidate", "who_voted", "created_at")
    list_filter = ("election", "position")
    search_fields = ("candidate__full_name", "voter__full_name", "voter__voter_code", "voter_email", "election__name")
    ordering = ("-created_at",)
    date_hierarchy = "created_at"

    autocomplete_fields = ("election", "position", "candidate", "voter")

    @admin.display(description="Voter")
    def who_voted(self, obj: Vote) -> str:
        if obj.voter_id:
            return f"{obj.voter.full_name} ({obj.voter.voter_code})"
        return obj.voter_email or "-"