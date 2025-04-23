from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database import AsyncSessionLocal

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency to provide a database session per request.
    Ensures the session is closed afterwards.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit() # Commit changes if no exceptions occurred
        except Exception:
            await session.rollback() # Rollback on error
            raise
        finally:
            await session.close() # Ensure session is closed