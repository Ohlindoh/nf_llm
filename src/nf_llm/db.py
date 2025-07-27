import os, pathlib
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DEFAULT_SQLITE = "sqlite:///data/nf_llm.db"
url = os.getenv("DATABASE_URL", DEFAULT_SQLITE)

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
