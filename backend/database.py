import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv() # Load variables from .env file

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set.")

# Create Async Engine
# echo=True is useful for debugging SQL statements, disable in production if needed
engine = create_async_engine(DATABASE_URL, echo=False, future=True)

# Create Async Session Maker
# expire_on_commit=False prevents attributes from being expired after commit,
# useful when returning ORM objects directly in FastAPI (though converting to Pydantic is often better)
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Base class for declarative models
Base = declarative_base()