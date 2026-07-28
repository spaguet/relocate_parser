"""Apply idempotent reference data seed to the configured database."""

from __future__ import annotations

import asyncio

from relocate_helper.db.seed import seed_reference_data
from relocate_helper.db.session import create_engine, create_session_factory, session_scope


async def main() -> None:
    engine = create_engine()
    factory = create_session_factory(engine)
    async with session_scope(factory) as session:
        await seed_reference_data(session)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
