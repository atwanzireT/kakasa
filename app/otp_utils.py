# app/otp_utils.py
from __future__ import annotations

import random
import re


def normalize_phone(phone: str) -> str:
    """
    Normalize to a consistent format.
    Adjust this to your standard (E.164 recommended).
    Example result: 2567XXXXXXXX
    """
    phone = (phone or "").strip()
    phone = re.sub(r"\s+", "", phone)

    # remove leading +
    if phone.startswith("+"):
        phone = phone[1:]

    # common Uganda local to international (07XXXXXXXX -> 2567XXXXXXXX)
    if phone.startswith("0") and len(phone) >= 10:
        phone = "256" + phone[1:]

    return phone


def generate_otp(length: int = 6) -> str:
    length = max(4, min(int(length), 8))
    start = 10 ** (length - 1)
    end = (10 ** length) - 1
    return str(random.randint(start, end))