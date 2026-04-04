"""
MAKTech Financial Flow — Production Credential Seeder
======================================================
Seeds the four role-based system accounts required to bootstrap the platform.

Roles seeded:
  • CEO       — ceo.maktech@finflow.com
  • DIRECTOR  — director.maktech@finflow.com
  • HR        — hr.maktech@finflow.com
  • BDEV      — bdev.maktech@finflow.com

Behaviour:
  ▶ Idempotent  — upserts by e-mail; safe to re-run without duplicate errors
  ▶ No hard reset — only touches the users table; all other data is preserved
  ▶ Passwords are bcrypt-hashed at runtime; plaintext never touches the DB

Run:
  poetry run python scripts/seed.py
  poetry run python -m scripts.seed
"""

import asyncio
import os
import sys
from dataclasses import dataclass
from typing import Final

# ── Path bootstrap (script or module invocation) ─────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prisma import Prisma
from app.core.security import hash_password


# ══════════════════════════════════════════════════════════════════════════════
#  CREDENTIAL MANIFEST
#  All four system accounts are declared here and nowhere else.
#  To rotate a password: change it in this block and re-run the seeder.
# ══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True, slots=True)
class _Credential:
    role:     str
    name:     str
    email:    str
    password: str


_CREDENTIALS: Final[tuple[_Credential, ...]] = (
    _Credential(
        role     = "CEO",
        name     = "CEO — MAKTech",
        email    = "ceo.maktech@finflow.com",
        password = "__C30-f!n@m4kt3ch__",
    ),
    _Credential(
        role     = "DIRECTOR",
        name     = "Director — MAKTech",
        email    = "director.maktech@finflow.com",
        password = "__d!r3ctor-f!n@m4kt3ch__",
    ),
    _Credential(
        role     = "HR",
        name     = "HR — MAKTech",
        email    = "hr.maktech@finflow.com",
        password = "__6r-f!n@m4kt3ch__",
    ),
    _Credential(
        role     = "BDEV",
        name     = "BDev — MAKTech",
        email    = "bdev.maktech@finflow.com",
        password = "__bd3v-f!n@m4kt3ch__",
    ),
)


# ══════════════════════════════════════════════════════════════════════════════
#  CONSOLE HELPERS
# ══════════════════════════════════════════════════════════════════════════════

_BAR: Final[str] = "─" * 56

def _header(title: str) -> None:
    print(f"\n┌{_BAR}┐")
    print(f"│  {title:<54}│")
    print(f"└{_BAR}┘")

def _row(action: str, role: str, email: str) -> None:
    tag = f"[{action}]"
    print(f"  {tag:<10}  {role:<10}  {email}")


# ══════════════════════════════════════════════════════════════════════════════
#  SEEDER
# ══════════════════════════════════════════════════════════════════════════════

async def seed_credentials(db: Prisma) -> None:
    """
    Upsert all four role-based system accounts.

    Strategy — upsert (create-or-update) keyed on e-mail:
      • If the account does not exist → created fresh.
      • If it already exists → name, role, passwordHash and isActive are
        refreshed to match this manifest (safe for credential rotation).

    No existing non-user data is ever deleted.
    """
    _header("🔐 Seeding Role-Based Credentials")

    created = updated = 0

    for cred in _CREDENTIALS:
        hashed = hash_password(cred.password)

        payload = {
            "name":         cred.name,
            "email":        cred.email,
            "passwordHash": hashed,
            "role":         cred.role,
            "isActive":     True,
        }

        existing = await db.user.find_unique(where={"email": cred.email})

        if existing is None:
            await db.user.create(data=payload)
            _row("CREATED", cred.role, cred.email)
            created += 1
        else:
            await db.user.update(
                where={"email": cred.email},
                data={k: v for k, v in payload.items() if k != "email"},
            )
            _row("UPDATED", cred.role, cred.email)
            updated += 1

    print(f"\n  Summary → {created} created  ·  {updated} updated  "
          f"·  {created + updated} total")


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

async def main() -> None:
    print()
    print("╔════════════════════════════════════════════════════════╗")
    print("║    MAKTech Financial Flow — Production Seeder          ║")
    print("╠════════════════════════════════════════════════════════╣")
    print("║  MODE : Idempotent upsert — no data ever wiped         ║")
    print("║  SCOPE: users table only (credentials)                 ║")
    print("╚════════════════════════════════════════════════════════╝")

    db = Prisma()
    await db.connect()

    try:
        await seed_credentials(db)

        print()
        print("╔════════════════════════════════════════════════════════╗")
        print("║  ✅  Credentials seeded — platform is ready.           ║")
        print("╠════════════════════════════════════════════════════════╣")
        print("║  CEO      →  ceo.maktech@finflow.com                   ║")
        print("║  Director →  director.maktech@finflow.com              ║")
        print("║  HR       →  hr.maktech@finflow.com                    ║")
        print("║  BDEV     →  bdev.maktech@finflow.com                  ║")
        print("╚════════════════════════════════════════════════════════╝")
        print()

    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())