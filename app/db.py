import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./talegaon_fresh.db")

# SQLAlchemy 2.1 defaults to the psycopg (v3) driver for a plain
# postgresql:// URL. Render uses psycopg2-binary in this project, so
# explicitly select the psycopg2 dialect while keeping the Render URL
# format unchanged.
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

is_sqlite = DATABASE_URL.startswith("sqlite")
connect_args = {"check_same_thread": False} if is_sqlite else {}
engine_options = {"connect_args": connect_args}
if not is_sqlite:
    # Detect and replace dead pooled connections before a request uses them.
    # Recycling periodically also avoids provider-side idle connection timeouts.
    engine_options.update(
        pool_pre_ping=True,
        pool_recycle=max(30, int(os.getenv("DB_POOL_RECYCLE_SECONDS", "300"))),
    )
engine = create_engine(DATABASE_URL, **engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass
