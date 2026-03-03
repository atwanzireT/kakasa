# app/otp_service.py
from __future__ import annotations

from datetime import timedelta
from django.db import transaction
from django.utils import timezone

from .models import Election, PhoneOTP, Vote, VotingSession
from .otp_utils import normalize_phone, generate_otp
from .sms import send_sms


OTP_MINUTES = 5
SESSION_MINUTES = 30


def phone_already_used_for_election(*, election: Election, phone: str) -> bool:
    phone = normalize_phone(phone)
    return Vote.objects.filter(election=election, voter_phone=phone).exists()


@transaction.atomic
def request_phone_otp(*, election: Election, phone: str) -> tuple[bool, str]:
    """
    Creates and sends OTP unless the phone already voted.
    Returns: (ok, message_for_user)
    """
    phone = normalize_phone(phone)

    if not phone:
        return False, "Phone number is required."

    if not election.is_open_now():
        return False, "Election is not open."

    # ✅ STOP OTP if phone already used (already voted)
    if phone_already_used_for_election(election=election, phone=phone):
        return False, "This phone number has already voted. OTP was not sent."

    # optional: prevent spamming by reusing existing active OTP
    existing = PhoneOTP.objects.filter(
        election=election,
        phone=phone,
        is_used=False,
        expires_at__gt=timezone.now(),
    ).order_by("-created_at").first()

    if existing:
        # reuse the existing OTP (or you can choose to generate a new one)
        code = existing.code
    else:
        code = generate_otp(6)
        PhoneOTP.objects.create(
            election=election,
            phone=phone,
            code=code,
            is_used=False,
            expires_at=timezone.now() + timedelta(minutes=OTP_MINUTES),
        )

    ok, resp = send_sms(phone, f"Your voting OTP is {code}. It expires in {OTP_MINUTES} minutes.")
    if not ok:
        return False, f"Failed to send OTP. {resp}"

    return True, "OTP sent successfully."


@transaction.atomic
def verify_phone_otp(*, election: Election, phone: str, code: str) -> tuple[bool, str, VotingSession | None]:
    """
    Verifies OTP and creates a VotingSession.
    Returns: (ok, message, session_or_none)
    """
    phone = normalize_phone(phone)
    code = (code or "").strip()

    if not phone or not code:
        return False, "Phone and OTP are required.", None

    if not election.is_open_now():
        return False, "Election is not open.", None

    # ✅ if they already voted, don't allow OTP login again
    if phone_already_used_for_election(election=election, phone=phone):
        return False, "This phone number has already voted.", None

    otp = PhoneOTP.objects.filter(
        election=election,
        phone=phone,
        code=code,
        is_used=False,
        expires_at__gt=timezone.now(),
    ).order_by("-created_at").first()

    if not otp:
        return False, "Invalid or expired OTP.", None

    otp.is_used = True
    otp.save(update_fields=["is_used"])

    session = VotingSession.create_for_phone(phone=phone, election=election, minutes=SESSION_MINUTES)
    return True, "OTP verified.", session