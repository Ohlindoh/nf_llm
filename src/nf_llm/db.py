import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from nf_llm.models import Base

DATABASE_URL = os.getenv("DATABASE_URL", "duckdb:////app/data/nf_llm.duckdb")

engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

def init_db():
    Base.metadata.create_all(bind=engine)
