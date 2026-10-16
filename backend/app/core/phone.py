import re

_UZ_PHONE = re.compile(r"^\+998\d{9}$")


def normalize_phone(raw: str) -> str:
    """Brings Uzbek numbers to one format: +998XXXXXXXXX.

    Accepts "+998 90 123-45-67", "998901234567", "90 123 45 67" etc.
    Raises ValueError for anything else. The same function will be used by SMS OTP later.
    """
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 9:
        digits = "998" + digits
    phone = "+" + digits
    if not _UZ_PHONE.match(phone):
        raise ValueError("Telefon raqam +998XXXXXXXXX formatida bo'lishi kerak")
    return phone
