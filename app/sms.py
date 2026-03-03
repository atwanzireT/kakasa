# app/sms.py
from __future__ import annotations

import json
from django.conf import settings
import requests

YOOLA_SMS_URL = "https://yoolasms.com/api/v1/send"


def send_sms(phone: str, message: str) -> tuple[bool, str]:
    """
    Sends SMS via YoolaSMS.
    Returns: (ok, response_text)
    """
    payload = {
        "phone": (phone or "").strip(),
        "message": message,
        "api_key": settings.YOOLA_SMS_API_KEY,
    }

    headers = {"Content-Type": "application/json"}

    try:
        resp = requests.post(
            YOOLA_SMS_URL,
            headers=headers,
            data=json.dumps(payload),
            timeout=20,
        )
        return resp.ok, resp.text
    except requests.RequestException as e:
        return False, str(e)