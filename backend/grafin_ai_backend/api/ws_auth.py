from grafin_ai_backend.api.deps import CurrentUser
from grafin_ai_backend.security.tokens import InvalidToken, decode_token


def authenticate_ws_token(token: str, secret: str) -> CurrentUser | None:
    """Validate a WS access token (passed as ?token=). Returns the user or None."""
    if not token:
        return None
    try:
        claims = decode_token(token, secret=secret)
    except InvalidToken:
        return None
    if claims.get("type") != "access":
        return None
    return CurrentUser(id=int(claims["sub"]), role=claims["role"])
