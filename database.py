# database.py

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
import os

# Get Turso credentials from environment variables
db_url = "libsql://easybio-vercel-icfg-763wtqln43yqganotgaqmrpf.aws-us-east-1.turso.io"
auth_token = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJpYXQiOjE3NTUxOTQ1MzQsImlkIjoiODdhMjhmYTItNWE5ZC00MmE3LTg3N2ItYzU1M2M5MzRjZmE1IiwicmlkIjoiMWI4MDA1ZWEtNzMzNi00MjczLWIzYTMtZDE1ZmZhMTdlNTE0In0.vZiUrhjGV7X_4YCDzKlFFGoQCcd4W-x6pMv9V6wDBuTfldK_ERkesNmI0DXbKN6C36ueTwhiTqzH69GJI6rNCw"

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
