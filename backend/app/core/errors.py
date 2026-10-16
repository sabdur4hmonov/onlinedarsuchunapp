from fastapi import HTTPException


def api_error(status_code: int, code: str, message: str, **extra) -> HTTPException:
    """Errors carry a stable machine-readable `code` the mobile app can switch on,
    plus a human-readable `message` (Uzbek) it can show to the user.

    Response body: {"detail": {"code": "...", "message": "...", ...extra}}
    """
    headers = {"WWW-Authenticate": "Bearer"} if status_code == 401 else None
    return HTTPException(status_code=status_code, detail={"code": code, "message": message, **extra}, headers=headers)
