import asyncio
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from garda_ai_backend.db import _maker
from garda_ai_backend.repositories.users import UserRepository
from garda_ai_backend.security.passwords import hash_password


async def ensure_admin(session: AsyncSession, email: str, password: str):
    repo = UserRepository(session)
    existing = await repo.get_by_email(email)
    if existing is not None:
        return existing
    return await repo.create(
        email=email, password_hash=hash_password(password), role="admin",
        created_at=datetime.now(UTC),
    )


async def _main() -> None:
    async with _maker()() as session:
        await ensure_admin(session, "admin@garda.local", "admin")
        await session.commit()


if __name__ == "__main__":
    asyncio.run(_main())
