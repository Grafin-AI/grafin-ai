from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_ph = PasswordHasher()

# Fixed hash used to equalize verify timing when the account does not exist,
# so an attacker cannot distinguish unknown emails by response latency.
_DUMMY_HASH = _ph.hash("grafin-timing-equalization-placeholder")


def hash_password(plain: str) -> str:
    return _ph.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, plain)
    except VerifyMismatchError:
        return False


def dummy_verify() -> None:
    """Run a verify against a fixed hash to match the cost of a real verify."""
    verify_password("x", _DUMMY_HASH)
