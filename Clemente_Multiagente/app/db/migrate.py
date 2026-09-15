"""
Applies pending SQL migrations from `migrations/`, in filename order.

Each file runs once: `schema_migrations` tracks what already ran, so restarts
and multiple app instances converge on the same schema without stepping on
each other. Add a new migration as the next numbered `.sql` file; never edit
an already-applied one.
"""

from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

_TRACKING_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def apply_pending(conn) -> list[str]:
    """Runs every migration not yet recorded. Returns the filenames it applied."""
    applied = []
    with conn.cursor() as cur:
        cur.execute(_TRACKING_TABLE)
        cur.execute("SELECT filename FROM schema_migrations")
        already_applied = {row[0] for row in cur.fetchall()}

        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.name in already_applied:
                continue
            cur.execute(path.read_text(encoding="utf-8"))
            cur.execute("INSERT INTO schema_migrations (filename) VALUES (%s)", (path.name,))
            applied.append(path.name)
    conn.commit()
    return applied


if __name__ == "__main__":
    # python -m app.db.migrate  -> applies pending migrations against CLEMENTE_DATABASE_URL.
    import os

    import psycopg2
    from dotenv import load_dotenv

    load_dotenv()
    database_url = os.getenv("CLEMENTE_DATABASE_URL", "")
    if not database_url:
        raise SystemExit("CLEMENTE_DATABASE_URL is not set")

    connection = psycopg2.connect(database_url)
    try:
        applied = apply_pending(connection)
    finally:
        connection.close()
    print(f"Applied: {applied}" if applied else "Nothing to apply, schema is up to date.")
