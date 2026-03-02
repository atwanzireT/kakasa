from __future__ import annotations

import random
import secrets
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Election(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"

    class AccessMode(models.TextChoices):
        CODE_ONLY = "code_only", "Code only (Name + Code)"
        WHITELIST_EMAIL = "whitelist_email", "Protected (Email whitelist + OTP)"
        ANY_EMAIL_DOMAIN = "any_email_domain", "Open (Allowed domains + OTP)"
        ANY_EMAIL = "any_email", "Open (Any email + OTP)"

    name = models.CharField(max_length=200)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    start_at = models.DateTimeField(blank=True, null=True)
    end_at = models.DateTimeField(blank=True, null=True)

    access_mode = models.CharField(max_length=30, choices=AccessMode.choices, default=AccessMode.CODE_ONLY)
    allowed_email_domains = models.CharField(
        max_length=300, blank=True, null=True,
        help_text="Comma-separated domains e.g. gmail.com,yahoo.com"
    )
    require_email_otp = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

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

    def domain_allowed(self, email: str) -> bool:
        if not self.allowed_email_domains:
            return False
        domain = (email.split("@")[-1] or "").strip().lower()
        allowed = [d.strip().lower() for d in self.allowed_email_domains.split(",") if d.strip()]
        return domain in allowed


class Position(models.Model):
    class Name(models.TextChoices):
        PRESIDENT = "president", "President"
        VICE_PRESIDENT = "vice_president", "Vice President"
        FINANCE = "finance", "Finance Secretary"

    election = models.ForeignKey(Election, on_delete=models.CASCADE, related_name="positions")
    name = models.CharField(max_length=20, choices=Name.choices)
    sort_order = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["election", "sort_order", "name"]
        constraints = [
            models.UniqueConstraint(fields=["election", "name"], name="uniq_position_per_election"),
        ]

    def __str__(self) -> str:
        return f"{self.get_name_display()} ({self.election.name})"


class Candidate(models.Model):
    election = models.ForeignKey(Election, on_delete=models.CASCADE, related_name="candidates")
    position = models.ForeignKey(Position, on_delete=models.CASCADE, related_name="candidates")

    full_name = models.CharField(max_length=120)

    # ✅ New biography fields
    bio_short = models.CharField(max_length=240, blank=True, null=True)
    bio = models.TextField(blank=True, null=True)

    # optional manifesto
    manifesto = models.TextField(blank=True, null=True)

    # ✅ photo as URL (no server storage)
    photo_url = models.URLField(blank=True, null=True)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["election", "position__sort_order", "full_name"]
        constraints = [
            models.UniqueConstraint(fields=["election", "position", "full_name"], name="uniq_candidate_name_per_position"),
        ]

    def __str__(self) -> str:
        return f"{self.full_name} — {self.position.get_name_display()}"

    def clean(self):
        if self.position_id and self.election_id and self.position.election_id != self.election_id:
            raise ValidationError({"position": "Position must belong to the same election."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class Voter(models.Model):
    """
    Used for CODE_ONLY elections.
    """
    full_name = models.CharField(max_length=120)
    voter_code = models.CharField(max_length=40, unique=True, db_index=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["full_name"]

    def __str__(self) -> str:
        return f"{self.full_name} ({self.voter_code})"


class ElectionEmailWhitelist(models.Model):
    """
    Used for protected elections (WHITELIST_EMAIL).
    """
    election = models.ForeignKey(Election, on_delete=models.CASCADE, related_name="email_whitelist")
    email = models.EmailField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["email"]
        constraints = [
            models.UniqueConstraint(fields=["election", "email"], name="uniq_email_whitelist"),
        ]

    def save(self, *args, **kwargs):
        self.email = (self.email or "").strip().lower()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.email} ({self.election.name})"


class EmailOTP(models.Model):
    """
    Email OTP verification for email-based elections.
    """
    election = models.ForeignKey(Election, on_delete=models.CASCADE, related_name="otps")
    email = models.EmailField()
    code = models.CharField(max_length=6)

    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["election", "email"]),
            models.Index(fields=["expires_at"]),
        ]

    def save(self, *args, **kwargs):
        self.email = (self.email or "").strip().lower()
        return super().save(*args, **kwargs)

    def is_valid(self) -> bool:
        return self.used_at is None and self.expires_at > timezone.now()

    @staticmethod
    def generate_code() -> str:
        return f"{random.randint(0, 999999):06d}"


class VotingSession(models.Model):
    """
    After verification, create a short session token.
    - CODE_ONLY: voter is set
    - EMAIL elections: voter is null, email is set
    """
    election = models.ForeignKey(Election, on_delete=models.CASCADE, related_name="sessions")
    voter = models.ForeignKey(Voter, on_delete=models.CASCADE, related_name="sessions", blank=True, null=True)
    email = models.EmailField(blank=True, null=True)

    token = models.CharField(max_length=64, unique=True, db_index=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["token"]), models.Index(fields=["expires_at"])]

    def __str__(self) -> str:
        who = self.voter_id or self.email
        return f"Session({self.election_id}, {who})"

    @staticmethod
    def create_for_code_voter(voter: Voter, election: Election, minutes: int = 15) -> "VotingSession":
        return VotingSession.objects.create(
            election=election,
            voter=voter,
            email=None,
            token=secrets.token_urlsafe(32),
            expires_at=timezone.now() + timedelta(minutes=minutes),
        )

    @staticmethod
    def create_for_email(email: str, election: Election, minutes: int = 15) -> "VotingSession":
        return VotingSession.objects.create(
            election=election,
            voter=None,
            email=(email or "").strip().lower(),
            token=secrets.token_urlsafe(32),
            expires_at=timezone.now() + timedelta(minutes=minutes),
        )

    def is_valid(self) -> bool:
        return self.expires_at > timezone.now()


class Vote(models.Model):
    election = models.ForeignKey(Election, on_delete=models.CASCADE, related_name="votes")
    position = models.ForeignKey(Position, on_delete=models.CASCADE, related_name="votes")
    candidate = models.ForeignKey(Candidate, on_delete=models.PROTECT, related_name="votes")

    # identity (either code voter OR email voter)
    voter = models.ForeignKey(Voter, on_delete=models.CASCADE, related_name="votes", blank=True, null=True)
    voter_email = models.EmailField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["voter", "election", "position"],
                name="uniq_vote_code_voter",
                condition=models.Q(voter__isnull=False),
            ),
            models.UniqueConstraint(
                fields=["voter_email", "election", "position"],
                name="uniq_vote_email_voter",
                condition=models.Q(voter_email__isnull=False),
            ),
        ]

    def __str__(self) -> str:
        who = self.voter.full_name if self.voter_id else (self.voter_email or "Unknown")
        return f"{who} -> {self.candidate.full_name} ({self.position.get_name_display()})"

    def clean(self):
        if self.position_id and self.election_id and self.position.election_id != self.election_id:
            raise ValidationError({"position": "Position must belong to the selected election."})

        if self.candidate_id and self.election_id and self.position_id:
            if self.candidate.election_id != self.election_id:
                raise ValidationError({"candidate": "Candidate must belong to the selected election."})
            if self.candidate.position_id != self.position_id:
                raise ValidationError({"candidate": "Candidate must match the selected position."})

        if not self.voter_id and not self.voter_email:
            raise ValidationError("Vote must belong to a voter or an email.")
        if self.voter_id and self.voter_email:
            raise ValidationError("Vote cannot have both voter and voter_email.")

        if self.voter_email:
            self.voter_email = self.voter_email.strip().lower()

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)