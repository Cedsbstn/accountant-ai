from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database import AsyncSessionLocal

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    session = AsyncSessionLocal()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()