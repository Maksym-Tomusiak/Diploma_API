from typing import Annotated, Generator
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi import Depends

from common.app_settings import settings

engine = create_engine(
    settings.DB_CONNECTION_STRING.replace("asyncpg", "psycopg2"),
    pool_pre_ping=True,
    pool_recycle=300
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# FastAPI-style dependency (no contextmanager needed)
async def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Typed annotation
SessionDep = Annotated[Session, Depends(get_db)]
