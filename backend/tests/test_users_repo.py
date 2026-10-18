from datetime import UTC, datetime

from grafin_ai_backend.repositories.users import UserRepository


async def test_create_and_fetch_user(session):
    repo = UserRepository(session)
    user = await repo.create(
        email="a@example.com",
        password_hash="$argon2id$hash",
        role="analyst",
        created_at=datetime.now(UTC),
    )
    await session.commit()
    assert user.id is not None

    by_email = await repo.get_by_email("a@example.com")
    assert by_email is not None
    assert by_email.role == "analyst"

    by_id = await repo.get_by_id(user.id)
    assert by_id is not None
    assert by_id.email == "a@example.com"

    missing = await repo.get_by_email("none@example.com")
    assert missing is None
