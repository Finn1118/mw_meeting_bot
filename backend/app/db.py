import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DEFAULT_DATABASE_URL = "sqlite+aiosqlite:///./data/meetings.db"

engine = create_async_engine(os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL))
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
