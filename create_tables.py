#!/usr/bin/env python
"""
Script to explicitly create database tables.
"""
import os
import pathlib
from sqlalchemy import create_engine, text

# PostgreSQL is the only supported database now
url = os.getenv("DATABASE_URL", "postgresql+psycopg://nf_user@localhost:5432/nf_llm")

# If running in Docker with a secrets-mounted Postgres password, inject it
# Using the same approach as in db.py
_pw_file = pathlib.Path("/run/secrets/db_password")
if "postgresql" in url and _pw_file.exists():
    pw = _pw_file.read_text().strip()
    url = url.replace("nf_user@", f"nf_user:{pw}@")

# Create engine
engine = create_engine(url, pool_pre_ping=True, future=True)

def create_tables():
    """Create all tables defined in models.py"""
    print(f"Creating tables using engine: {engine}")
    
    # Import models the same way init_db does
    from nf_llm import models
    print(f"Available models: {dir(models)}")
    print(f"Base metadata tables: {models.Base.metadata.tables.keys()}")
    
    # Create all tables
    models.Base.metadata.create_all(engine)
    
    # Verify tables were created
    with engine.connect() as conn:
        result = conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'"))
        tables = [row[0] for row in result]
        print(f"Tables in database: {tables}")
        
        # Check if lineup table exists
        lineup_exists = 'lineup' in tables
        print(f"Lineup table exists: {lineup_exists}")

if __name__ == "__main__":
    create_tables()
