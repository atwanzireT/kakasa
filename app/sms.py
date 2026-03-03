# app/sms.py
from django.conf import settings
import requests
import json

YOOLA_SMS_URL = "https://yoolasms.com/api/v1/send"


def send_sms(phone: str, message: str):
    payload = json.dumps({
        "phone": phone,
        "message": message,
        "api_key": settings.YOOLA_SMS_API_KEY,
    })

    headers = {"Content-Type": "application/json"}

    response = requests.post(YOOLA_SMS_URL, headers=headers, data=payload)
    return response.ok, response.text