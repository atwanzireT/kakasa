from __future__ import annotations

from datetime import timedelta

from django import forms
from django.core.mail import send_mail
from django.utils import timezone

from .models import (
    Election, Position, Candidate, Voter,
    VotingSession, ElectionEmailWhitelist, EmailOTP, Vote
)


class CodeLoginForm(forms.Form):
    full_name = forms.CharField(max_length=120)
    voter_code = forms.CharField(max_length=40)

    def __init__(self, *args, election: Election, **kwargs):
        super().__init__(*args, **kwargs)
        self.election = election
        self.voter: Voter | None = None

    def clean_full_name(self):
        return (self.cleaned_data.get("full_name") or "").strip()

    def clean_voter_code(self):
        return (self.cleaned_data.get("voter_code") or "").strip()

    def clean(self):
        cleaned = super().clean()

        if not self.election.is_open_now():
            raise forms.ValidationError("Voting is not open for this election.")

        full_name = cleaned.get("full_name")
        voter_code = cleaned.get("voter_code")
        if not full_name or not voter_code:
            return cleaned

        try:
            voter = Voter.objects.get(voter_code=voter_code, is_active=True)
        except Voter.DoesNotExist:
            raise forms.ValidationError("Invalid voter code or voter is not active.")

        if voter.full_name.strip().lower() != full_name.lower():
            raise forms.ValidationError("Name and voter code do not match.")

        self.voter = voter
        return cleaned


class EmailStartForm(forms.Form):
    email = forms.EmailField()

    def __init__(self, *args, election: Election, **kwargs):
        super().__init__(*args, **kwargs)
        self.election = election

    def clean_email(self):
        return (self.cleaned_data.get("email") or "").strip().lower()

    def clean(self):
        cleaned = super().clean()

        if not self.election.is_open_now():
            raise forms.ValidationError("Voting is not open for this election.")

        email = cleaned.get("email")
        if not email:
            return cleaned

        mode = self.election.access_mode

        if mode == Election.AccessMode.WHITELIST_EMAIL:
            ok = ElectionEmailWhitelist.objects.filter(election=self.election, email=email, is_active=True).exists()
            if not ok:
                raise forms.ValidationError("This email is not allowed for this protected election.")

        if mode == Election.AccessMode.ANY_EMAIL_DOMAIN:
            if not self.election.domain_allowed(email):
                raise forms.ValidationError("This email domain is not allowed for this election.")

        return cleaned

    def send_otp(self) -> EmailOTP:
        email = self.cleaned_data["email"]
        code = EmailOTP.generate_code()

        otp = EmailOTP.objects.create(
            election=self.election,
            email=email,
            code=code,
            expires_at=timezone.now() + timedelta(minutes=10),
        )

        send_mail(
            subject=f"Kakasa Voting OTP — {self.election.name}",
            message=f"Your OTP code is {code}. It expires in 10 minutes.",
            from_email=None,
            recipient_list=[email],
            fail_silently=False,
        )
        return otp


class OTPVerifyForm(forms.Form):
    email = forms.EmailField()
    code = forms.CharField(max_length=6)

    def __init__(self, *args, election: Election, **kwargs):
        super().__init__(*args, **kwargs)
        self.election = election
        self.otp_obj: EmailOTP | None = None

    def clean_email(self):
        return (self.cleaned_data.get("email") or "").strip().lower()

    def clean_code(self):
        return (self.cleaned_data.get("code") or "").strip()

    def clean(self):
        cleaned = super().clean()
        email = cleaned.get("email")
        code = cleaned.get("code")
        if not email or not code:
            return cleaned

        otp = EmailOTP.objects.filter(election=self.election, email=email, code=code).order_by("-created_at").first()
        if not otp or not otp.is_valid():
            raise forms.ValidationError("Invalid or expired OTP code.")

        self.otp_obj = otp
        return cleaned

    def mark_used(self):
        if self.otp_obj:
            self.otp_obj.used_at = timezone.now()
            self.otp_obj.save(update_fields=["used_at"])


class SubmitBallotHelper:
    def __init__(self, *, session: VotingSession):
        self.session = session
        self.election = session.election

    def save_votes(self, post_data) -> tuple[int, int, int]:
        positions = Position.objects.filter(election=self.election).order_by("sort_order", "name")

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
                        voter_email=None,
                    )
                else:
                    Vote.objects.create(
                        election=self.election,
                        position=pos,
                        candidate=candidate,
                        voter=None,
                        voter_email=self.session.email,
                    )
                created += 1
            except Exception:
                already += 1

        return created, already, errors