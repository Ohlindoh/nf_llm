import os, pathlib
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# PostgreSQL is the only supported database now
url = os.getenv("DATABASE_URL", "postgresql+psycopg2://nf_user@localhost:5432/nf_llm")

# If running in Docker with a secrets-mounted Postgres password, inject it
_pw_file = pathlib.Path("/run/secrets/db_password")
if "postgresql" in url and _pw_file.exists():
    pw = _pw_file.read_text().strip()
    url = url.replace("nf_user@", f"nf_user:{pw}@")

engine = create_engine(url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine)

def init_db():
    from nf_llm import models  # import your SQLAlchemy Base subclasses
    models.Base.metadata.create_all(engine)

def get_conn():
    """Get a raw database connection for testing purposes"""
    return engine.connect()
