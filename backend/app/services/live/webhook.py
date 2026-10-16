"""LiveKit webhook verification with the official SDK.

LiveKit signs every webhook: the Authorization header is a JWT signed with our API
secret that contains the SHA-256 of the body. `WebhookReceiver` checks the signature,
the expiry and the body hash, so a forged or modified request is rejected.
This is independent of the provider choice: without LIVEKIT_API_KEY/SECRET every
webhook is rejected.
"""

from livekit import api as lk

from app.core.config import get_settings


class InvalidWebhook(Exception):
    pass


def verify_livekit_webhook(body: str, authorization: str | None) -> lk.WebhookEvent:
    settings = get_settings()
    if not (settings.livekit_api_key and settings.livekit_api_secret and authorization):
        raise InvalidWebhook("not configured or no Authorization header")
    token = authorization.removeprefix("Bearer ").strip()
    receiver = lk.WebhookReceiver(lk.TokenVerifier(settings.livekit_api_key, settings.livekit_api_secret))
    try:
        return receiver.receive(body, token)
    except Exception as e:  # the SDK raises plain Exception / jwt errors / protobuf ParseError
        raise InvalidWebhook(e.__class__.__name__) from e
