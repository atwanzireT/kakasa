# app/forms.py
from __future__ import annotations

import random
from datetime import timedelta
from django import forms
from django.utils import timezone

from .models import (
    Election,
    Voter,
    PhoneOTP,
    Position,
    Candidate,
    Vote,
    VotingSession,
)


# -----------------------------
# CODE-ONLY LOGIN FORM
# -----------------------------
class CodeLoginForm(forms.Form):
    full_name = forms.CharField(max_length=120)
    voter_code = forms.CharField(max_length=40)

    def __init__(self, *args, election: Election, **kwargs):
        super().__init__(*args, **kwargs)
        self.election = election
        self.voter: Voter | None = None

    def clean(self):
        cleaned = super().clean()

        if not self.election.is_open_now():
            raise forms.ValidationError("Voting is not open.")

        full_name = (cleaned.get("full_name") or "").strip()
        voter_code = (cleaned.get("voter_code") or "").strip()

        if not full_name or not voter_code:
            return cleaned

        try:
            voter = Voter.objects.get(voter_code=voter_code, is_active=True)
        except Voter.DoesNotExist:
            raise forms.ValidationError("Invalid voter code.")

        if voter.full_name.strip().lower() != full_name.lower():
            raise forms.ValidationError("Name and voter code do not match.")

        self.voter = voter
        return cleaned


# -----------------------------
# PHONE OTP LOGIN
# -----------------------------
def normalize_phone(raw: str) -> str:
    p = (raw or "").strip().replace(" ", "")
    if p.startswith("07") and len(p) >= 10:
        return "+256" + p[1:]
    if p.startswith("256"):
        return "+" + p
    return p


class PhoneStartForm(forms.Form):
    phone = forms.CharField(max_length=30)

    def __init__(self, *args, election: Election, **kwargs):
        super().__init__(*args, **kwargs)
        self.election = election
        self.cleaned_phone = None

    def clean_phone(self):
        phone = normalize_phone(self.cleaned_data.get("phone"))
        if not phone:
            raise forms.ValidationError("Phone number required.")
        self.cleaned_phone = phone
        return phone

    def create_otp(self) -> PhoneOTP:
        code = f"{random.randint(100000, 999999)}"
        return PhoneOTP.objects.create(
            election=self.election,
            phone=self.cleaned_phone,
            code=code,
            expires_at=timezone.now() + timedelta(minutes=5),
        )


class OTPVerifyForm(forms.Form):
    phone = forms.CharField(max_length=30)
    code = forms.CharField(max_length=8)

    def __init__(self, *args, election: Election, **kwargs):
        super().__init__(*args, **kwargs)
        self.election = election
        self.otp_obj: PhoneOTP | None = None

    def clean(self):
        cleaned = super().clean()

        phone = normalize_phone(cleaned.get("phone"))
        code = (cleaned.get("code") or "").strip()

        if not phone or not code:
            return cleaned

        otp = PhoneOTP.objects.filter(
            election=self.election,
            phone=phone,
            code=code,
            is_used=False,
            expires_at__gt=timezone.now(),
        ).order_by("-created_at").first()

        if not otp:
            raise forms.ValidationError("Invalid or expired OTP.")

        self.otp_obj = otp
        return cleaned


# -----------------------------
# BALLOT SUBMISSION
# -----------------------------
class SubmitBallotHelper:
    def __init__(self, *, session: VotingSession):
        self.session = session
        self.election = session.election

    def save_votes(self, post_data):
        positions = Position.objects.filter(election=self.election)

        created = 0
        already = 0
        errors = 0

        for pos in positions:
            key = f"choice_{pos.id}"
            candidate_id = (post_data.get(key) or "").strip()
            if not candidate_id:
                continue

            candidate = Candidate.objects.filter(
                id=candidate_id,
                election=self.election,
                position=pos,
                is_active=True,
            ).first()

            if not candidate:
                errors += 1
                continue

            try:
                if self.session.voter_id:
                    Vote.objects.create(
                        election=self.election,
                        position=pos,
                        candidate=candidate,
                        voter=self.session.voter,
                        voter_phone=None,
                    )
                else:
                    Vote.objects.create(
                        election=self.election,
                        position=pos,
                        candidate=candidate,
                        voter=None,
                        voter_phone=self.session.phone,
                    )
                created += 1
            except Exception:
                already += 1

        return created, already, errors