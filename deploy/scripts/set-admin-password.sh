#!/usr/bin/env bash
# Change a dashboard user's password in the RUNNING local stack.
#
#   ./scripts/set-admin-password.sh                    # admin@grafin.local
#   ./scripts/set-admin-password.sh someone@example.com
#
# The password is read silently and handed to the container on stdin, so it never
# appears in shell history, `ps` output, or the container's command line.
#
# It persists across restarts: the backend's seed only CREATES the admin when it is
# missing and never resets an existing password. It reverts to admin/admin only if
# you wipe the database (`docker compose down -v`).
set -euo pipefail

EMAIL="${1:-admin@grafin.local}"
cd "$(dirname "${BASH_SOURCE[0]}")/.."

docker compose ps --status running --services 2>/dev/null | grep -qx backend \
  || { echo "ERROR: backend is not running (start it with: make up)"; exit 1; }

read -r -s -p "New password for ${EMAIL}: " PW1; echo
read -r -s -p "Repeat: " PW2; echo
[ "$PW1" = "$PW2" ] || { echo "ERROR: passwords do not match"; exit 1; }
[ "${#PW1}" -ge 12 ] || { echo "ERROR: use at least 12 characters (this will face the internet)"; exit 1; }

printf '%s' "$PW1" | docker compose exec -T -e TARGET_EMAIL="$EMAIL" backend \
  uv run --no-sync python -c '
import asyncio, os, sys
from sqlalchemy import update
from grafin_ai_backend.db import _maker
from grafin_ai_backend.schema.users import User
from grafin_ai_backend.security.passwords import hash_password

async def main() -> None:
    password = sys.stdin.read()
    email = os.environ["TARGET_EMAIL"]
    async with _maker()() as session:
        result = await session.execute(
            update(User).where(User.email == email).values(password_hash=hash_password(password))
        )
        await session.commit()
    if result.rowcount != 1:
        sys.exit(f"ERROR: no user with email {email}")
    print(f"password updated for {email}")

asyncio.run(main())
'
