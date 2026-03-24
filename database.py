"""
Database configuration and session management.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

# Check if we are in a serverless/vercel environment
IS_VERCEL = os.environ.get("VERCEL") == "1" or os.environ.get("VERCEL_ENV") is not None

# Use DATABASE_URL if available, otherwise fallback to SQLite
# Fallback to /tmp/leads.db if on Vercel for write permissions
SQLALCHEMY_DATABASE_URL = os.environ.get("DATABASE_URL")

if not SQLALCHEMY_DATABASE_URL:
    if IS_VERCEL:
        SQLALCHEMY_DATABASE_URL = "sqlite:////tmp/leads.db"
    else:
        SQLALCHEMY_DATABASE_URL = "sqlite:///./leads.db"

# Fix for Heroku/Render/Vercel Postgres URLs starting with postgres:// instead of postgresql://
if SQLALCHEMY_DATABASE_URL and SQLALCHEMY_DATABASE_URL.startswith("postgres://"):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgres://", "postgresql://", 1)

# check_same_thread is needed only for SQLite.
IS_SQLITE = SQLALCHEMY_DATABASE_URL and "sqlite" in SQLALCHEMY_DATABASE_URL
connect_args = {"check_same_thread": False} if IS_SQLITE else {}

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    """Dependency that provides a database session."""
    database = SessionLocal()
    try:
        yield database
    finally:
        database.close()
