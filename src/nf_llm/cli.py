"""
CLI for the nf_llm project.
"""
import os
import typer
from pathlib import Path
from typing import Optional

from nf_llm import db

app = typer.Typer()
db_app = typer.Typer()
app.add_typer(db_app, name="db", help="Database operations")


@db_app.command("init")
def db_init() -> None:
    """Initialize the database with the schema."""
    conn = db.get_conn()
    
    # Get the path to the schema file
    base_dir = Path(__file__).resolve().parents[2]
    schema_path = base_dir / "migrations" / "schema.sql"
    
    if not schema_path.exists():
        typer.echo(f"Schema file not found at {schema_path}")
        raise typer.Exit(code=1)
    
    # Read the schema file
    with open(schema_path, "r") as f:
        schema_sql = f.read()
    
    # Execute the schema
    try:
        db.exec_sql(schema_sql)
        typer.echo("Database initialized successfully")
    except Exception as e:
        typer.echo(f"Error initializing database: {e}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
