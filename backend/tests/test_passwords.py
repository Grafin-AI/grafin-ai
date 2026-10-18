from grafin_ai_backend.security.passwords import hash_password, verify_password


def test_hash_and_verify():
    h = hash_password("s3cret!")
    assert h != "s3cret!"
    assert h.startswith("$argon2")
    assert verify_password("s3cret!", h) is True
    assert verify_password("wrong", h) is False
