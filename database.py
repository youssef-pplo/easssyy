# database.py

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
import os

# Get Turso credentials from environment variables
db_url = os.environ.get("TURSO_DATABASE_URL")
auth_token = os.environ.get("TURSO_AUTH_TOKEN")

# Create the full connection string for Turso
# The 'libsql' scheme tells SQLAlchemy to use the Turso driver
SQLALCHEMY_DATABASE_URL = f"sqlite+{db_url}/?authToken={auth_token}&secure=true"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    future=True
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
