# app/models.py
from __future__ import annotations

import secrets
from datetime import timedelta
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Election(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        OPEN = "open", _("Open")
        CLOSED = "closed", _("Closed")

    class AccessMode(models.TextChoices):
        CODE_ONLY = "code_only", _("Code Only")
        PHONE_OTP = "phone_otp", _("Phone OTP")

    name = models.CharField(max_length=200)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)

    access_mode = models.CharField(max_length=20, choices=AccessMode.choices, default=AccessMode.PHONE_OTP)

    start_at = models.DateTimeField(blank=True, null=True)
    end_at = models.DateTimeField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.name

    def is_open_now(self) -> bool:
        if self.status != self.Status.OPEN:
            return False
        now = timezone.now()
        if self.start_at and now < self.start_at:
            return False
        if self.end_at and now > self.end_at:
            return False
        return True


class Position(models.Model):
    election = models.ForeignKey(Election, on_delete=models.CASCADE, related_name="positions")
    name = models.CharField(max_length=120)
    sort_order = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.election.name})"

    def get_name_display(self):
        # For templates that call {{ position.get_name_display }}
        return self.name

class Candidate(models.Model):
    election = models.ForeignKey(Election, on_delete=models.CASCADE, related_name="candidates")
    position = models.ForeignKey(Position, on_delete=models.CASCADE, related_name="candidates")

    full_name = models.CharField(max_length=160)

    # short preview (used on cards)
    bio_short = models.CharField(max_length=220, blank=True, null=True)

    # full bio (used in modal)
    bio = models.TextField(blank=True, null=True)

    # ✅ new fields
    image_url = models.URLField(blank=True, null=True)
    university = models.CharField(max_length=160, blank=True, null=True)
    study_year = models.PositiveSmallIntegerField(blank=True, null=True)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["full_name"]

    def __str__(self) -> str:
        return f"{self.full_name} - {self.position.name}"


class Voter(models.Model):
    """
    Only used for CODE_ONLY elections.
    """
    full_name = models.CharField(max_length=160)
    voter_code = models.CharField(max_length=40, unique=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["full_name"]

    def __str__(self) -> str:
        return f"{self.full_name} ({self.voter_code})"


class PhoneOTP(models.Model):
    """
    OTP sent to a phone number for a specific election.
    """
    election = models.ForeignKey(Election, on_delete=models.CASCADE, related_name="phone_otps")
    phone = models.CharField(max_length=30, db_index=True)

    code = models.CharField(max_length=8)
    is_used = models.BooleanField(default=False)
    expires_at = models.DateTimeField()

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["election", "phone"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.phone} ({self.election.name})"

    def is_valid(self) -> bool:
        return (not self.is_used) and (self.expires_at > timezone.now())


class VotingSession(models.Model):
    """
    Session created after successful login.
    - CODE_ONLY: voter is set
    - PHONE_OTP: phone is set
    """
    election = models.ForeignKey(Election, on_delete=models.CASCADE, related_name="sessions")
    voter = models.ForeignKey(Voter, on_delete=models.CASCADE, related_name="sessions", blank=True, null=True)

    phone = models.CharField(max_length=30, blank=True, null=True, db_index=True)

    token = models.CharField(max_length=64, unique=True, db_index=True)
    expires_at = models.DateTimeField()

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Session {self.token[:10]}... ({self.election.name})"

    @staticmethod
    def create_for_code_voter(*, voter: Voter, election: Election, minutes: int = 15) -> "VotingSession":
        return VotingSession.objects.create(
            election=election,
            voter=voter,
            phone=None,
            token=secrets.token_urlsafe(32),
            expires_at=timezone.now() + timedelta(minutes=minutes),
        )

    @staticmethod
    def create_for_phone(*, phone: str, election: Election, minutes: int = 30) -> "VotingSession":
        return VotingSession.objects.create(
            election=election,
            voter=None,
            phone=(phone or "").strip(),
            token=secrets.token_urlsafe(32),
            expires_at=timezone.now() + timedelta(minutes=minutes),
        )

    def is_valid(self) -> bool:
        return self.expires_at > timezone.now()


class Vote(models.Model):
    election = models.ForeignKey(Election, on_delete=models.CASCADE, related_name="votes")
    position = models.ForeignKey(Position, on_delete=models.CASCADE, related_name="votes")
    candidate = models.ForeignKey(Candidate, on_delete=models.PROTECT, related_name="votes")

    voter = models.ForeignKey(Voter, on_delete=models.CASCADE, related_name="votes", blank=True, null=True)
    voter_phone = models.CharField(max_length=30, blank=True, null=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            # CODE voters: one vote per position
            models.UniqueConstraint(
                fields=["voter", "election", "position"],
                name="uniq_vote_code_voter",
                condition=models.Q(voter__isnull=False),
            ),
            # PHONE voters: one vote per position
            models.UniqueConstraint(
                fields=["voter_phone", "election", "position"],
                name="uniq_vote_phone_voter",
                condition=models.Q(voter_phone__isnull=False),
            ),
        ]

    def __str__(self) -> str:
        who = self.voter.full_name if self.voter_id else (self.voter_phone or "unknown")
        return f"{who} -> {self.candidate.full_name} ({self.position.name})"