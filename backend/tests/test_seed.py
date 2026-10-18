from grafin_ai_backend.repositories.users import UserRepository
from grafin_ai_backend.seed import ensure_admin


async def test_ensure_admin_is_idempotent(session):
    u1 = await ensure_admin(session, "admin@example.com", "pw")
    await session.commit()
    u2 = await ensure_admin(session, "admin@example.com", "pw")
    await session.commit()
    assert u1.id == u2.id  # not duplicated
    assert u1.role == "admin"
    found = await UserRepository(session).get_by_email("admin@example.com")
    assert found is not None
