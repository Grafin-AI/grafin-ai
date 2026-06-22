from datetime import UTC, datetime

from sqlalchemy import select

from garda_ai_backend.repositories.users import UserRepository
from garda_ai_backend.schema import SimState
from garda_ai_backend.seed import ensure_admin, ensure_sim_state


async def test_ensure_admin_is_idempotent(session):
    u1 = await ensure_admin(session, "admin@example.com", "pw")
    await session.commit()
    u2 = await ensure_admin(session, "admin@example.com", "pw")
    await session.commit()
    assert u1.id == u2.id  # not duplicated
    assert u1.role == "admin"
    found = await UserRepository(session).get_by_email("admin@example.com")
    assert found is not None


async def test_ensure_sim_state_singleton(session):
    s1 = await ensure_sim_state(session, start=datetime(2025, 9, 1, tzinfo=UTC), speed=60.0)
    await session.commit()
    await ensure_sim_state(session, start=datetime(2025, 9, 1, tzinfo=UTC), speed=60.0)
    await session.commit()
    rows = (await session.execute(select(SimState))).scalars().all()
    assert len(rows) == 1
    assert rows[0].id == 1
    assert s1.id == 1
