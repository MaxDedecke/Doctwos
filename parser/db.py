import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Environment configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://admin:password@db:5432/doctus")
REPOS_ROOT = "/repos"

# Database initialization
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
