# app/admin.py
from __future__ import annotations

from django.contrib import admin
from django.apps import apps
from django.db import models


def _get_model(name: str):
    """
    Safely get a model from this Django app without crashing if it doesn't exist.
    """
    try:
        return apps.get_model("app", name)
    except LookupError:
        return None


# Try to load models that may or may not exist depending on your current models.py
Election = _get_model("Election")
Position = _get_model("Position")
Candidate = _get_model("Candidate")
Voter = _get_model("Voter")
VotingSession = _get_model("VotingSession")
Vote = _get_model("Vote")
ElectionEmailWhitelist = _get_model("ElectionEmailWhitelist")
PhoneOTP = _get_model("PhoneOTP")


def _register(model_cls, admin_cls=None):
    if model_cls is None:
        return
    try:
        admin.site.register(model_cls, admin_cls or admin.ModelAdmin)
    except admin.sites.AlreadyRegistered:
        pass


# --- Admin classes (only used if the model exists) ---

class BaseReadOnlyCreatedAdmin(admin.ModelAdmin):
    readonly_fields = ("created_at",)
    search_fields = ()
    list_filter = ()
    list_display = ()

    def has_delete_permission(self, request, obj=None):
        # allow delete by default (change if you want)
        return super().has_delete_permission(request, obj)


if Election is not None:
    class ElectionAdmin(BaseReadOnlyCreatedAdmin):
        list_display = ("id", "name", "status", "access_mode", "start_at", "end_at", "created_at")
        list_filter = ("status", "access_mode")
        search_fields = ("name",)

    _register(Election, ElectionAdmin)


if Position is not None:
    class PositionAdmin(BaseReadOnlyCreatedAdmin):
        list_display = ("id", "election", "name", "sort_order", "created_at")
        list_filter = ("election",)
        search_fields = ("name",)

    _register(Position, PositionAdmin)


if Candidate is not None:
    class CandidateAdmin(BaseReadOnlyCreatedAdmin):
        list_display = ("id", "election", "position", "full_name", "is_active", "created_at")
        list_filter = ("election", "position", "is_active")
        search_fields = ("full_name",)

    _register(Candidate, CandidateAdmin)


if Voter is not None:
    class VoterAdmin(BaseReadOnlyCreatedAdmin):
        list_display = ("id", "full_name", "voter_code", "is_active", "created_at")
        list_filter = ("is_active",)
        search_fields = ("full_name", "voter_code")

    _register(Voter, VoterAdmin)


if VotingSession is not None:
    class VotingSessionAdmin(BaseReadOnlyCreatedAdmin):
        list_display = ("id", "election", "token", "expires_at", "voter", "phone", "created_at")
        list_filter = ("election",)
        search_fields = ("token", "phone")

    _register(VotingSession, VotingSessionAdmin)


if Vote is not None:
    class VoteAdmin(BaseReadOnlyCreatedAdmin):
        list_display = ("id", "election", "position", "candidate", "voter", "voter_phone", "created_at")
        list_filter = ("election", "position")
        search_fields = ("voter_phone",)

    _register(Vote, VoteAdmin)


if ElectionEmailWhitelist is not None:
    class ElectionEmailWhitelistAdmin(BaseReadOnlyCreatedAdmin):
        list_display = ("id", "election", "email", "is_active", "created_at")
        list_filter = ("election", "is_active")
        search_fields = ("email",)

    _register(ElectionEmailWhitelist, ElectionEmailWhitelistAdmin)


if PhoneOTP is not None:
    class PhoneOTPAdmin(BaseReadOnlyCreatedAdmin):
        list_display = ("id", "election", "phone", "code", "is_used", "expires_at", "created_at")
        list_filter = ("election", "is_used")
        search_fields = ("phone", "code")

    _register(PhoneOTP, PhoneOTPAdmin)