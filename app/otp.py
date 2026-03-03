# app/otp.py
from __future__ import annotations

def normalize_phone(phone: str) -> str:
    # adjust to your preferred format (E.164 recommended)
    return (phone or "").strip().replace(" ", "")

def phone_already_used(*, election_id: int, phone: str) -> bool:
    from .models import Vote  # local import to avoid circular imports
    phone = normalize_phone(phone)
    return Vote.objects.filter(election_id=election_id, voter_phone=phone).exists()