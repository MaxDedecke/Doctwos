"""Shared SQLAlchemy registry for the main schema and bounded feature modules."""

from sqlalchemy.orm import declarative_base

Base = declarative_base()
