# database.py

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
import os

# Get Turso credentials from environment variables
db_url_from_env = os.environ.get("TURSO_DATABASE_URL", "")
auth_token = os.environ.get("TURSO_AUTH_TOKEN")

# **THE FIX IS HERE:**
# The environment variable from Vercel includes "libsql://". We must remove it
# before building the final SQLAlchemy connection string to avoid duplication.
if db_url_from_env.startswith("libsql://"):
    db_hostname = db_url_from_env[len("libsql://"):]
else:
    db_hostname = db_url_from_env

# This now creates the correctly formatted URL
SQLALCHEMY_DATABASE_URL = f"sqlite+libsql://{db_hostname}?authToken={auth_token}&secure=true"


engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
