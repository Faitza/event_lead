from django.conf import settings


def site_settings(request):
    return {
        "CONTACT_EMAIL": settings.CONTACT_EMAIL,
        "CONTACT_PHONE": settings.CONTACT_PHONE,
        "CONTACT_WHATSAPP": settings.CONTACT_WHATSAPP,
        "CONTACT_ADDRESS": settings.CONTACT_ADDRESS,
        "GOOGLE_LOGIN_ENABLED": bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET),
        "PAYMENT_DEMO_MODE": settings.PAYMENT_DEMO_MODE,
    }
