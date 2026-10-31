"""SQLite database schema and migrations for research-desk jobs."""

import sqlite3
from pathlib import Path
from contextlib import contextmanager
from typing import Optional, List, Dict, Any


DB_PATH = Path(__file__).parent / "jobs.db"
SCHEMA_VERSION = 1


def get_connection() -> sqlite3.Connection:
    """Get a database connection with row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def transaction():
    """Context manager for database transactions."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Initialize the database with schema and run migrations idempotently."""
    with transaction() as conn:
        _create_schema_version_table(conn)
        current_version = _get_schema_version(conn)
        if current_version < SCHEMA_VERSION:
            _run_migrations(conn, current_version)
            _set_schema_version(conn, SCHEMA_VERSION)


def _create_schema_version_table(conn: sqlite3.Connection) -> None:
    """Create the schema_version table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)


def _get_schema_version(conn: sqlite3.Connection) -> int:
    """Get the current schema version."""
    row = conn.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1").fetchone()
    return row["version"] if row else 0


def _set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    """Set the schema version."""
    conn.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))


def _run_migrations(conn: sqlite3.Connection, from_version: int) -> None:
    """Run migrations from the given version to current."""
    if from_version < 1:
        _migration_001_create_jobs_table(conn)


def _migration_001_create_jobs_table(conn: sqlite3.Connection) -> None:
    """Create the jobs table with all required columns."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            stage TEXT NOT NULL CHECK (stage IN ('plan', 'research', 'review', 'needs_human', 'published')),
            plan_output TEXT,
            research_output TEXT,
            review_output TEXT,
            retry_count INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_jobs_stage ON jobs(stage)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at)
    """)


# --- Job CRUD operations ---

VALID_STAGES = {"plan", "research", "review", "needs_human", "published"}


def create_job(question: str, stage: str = "plan") -> int:
    """Create a new job and return its ID."""
    if stage not in VALID_STAGES:
        raise ValueError(f"Invalid stage: {stage}. Must be one of {VALID_STAGES}")
    with transaction() as conn:
        cursor = conn.execute(
            "INSERT INTO jobs (question, stage) VALUES (?, ?)",
            (question, stage)
        )
        job_id = cursor.lastrowid
        if job_id is None:
            raise RuntimeError("Failed to create job: no lastrowid returned")
        return job_id


def get_job(job_id: int) -> Optional[Dict[str, Any]]:
    """Fetch a job by ID."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None


def update_job(job_id: int, **fields) -> bool:
    """Update job fields. Returns True if job was found and updated."""
    if not fields:
        return False
    
    # Validate stage if present
    if "stage" in fields and fields["stage"] not in VALID_STAGES:
        raise ValueError(f"Invalid stage: {fields['stage']}. Must be one of {VALID_STAGES}")
    
    # Always update updated_at
    fields["updated_at"] = "CURRENT_TIMESTAMP"
    
    set_clause = ", ".join(f"{k} = ?" for k in fields.keys())
    values = list(fields.values()) + [job_id]
    
    with transaction() as conn:
        cursor = conn.execute(f"UPDATE jobs SET {set_clause} WHERE id = ?", values)
        return cursor.rowcount > 0


def list_jobs(stage: Optional[str] = None, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    """List jobs, optionally filtered by stage."""
    with get_connection() as conn:
        if stage:
            if stage not in VALID_STAGES:
                raise ValueError(f"Invalid stage: {stage}. Must be one of {VALID_STAGES}")
            rows = conn.execute(
                "SELECT * FROM jobs WHERE stage = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (stage, limit, offset)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset)
            ).fetchall()
        return [dict(row) for row in rows]


def increment_retry_count(job_id: int) -> bool:
    """Increment the retry count for a job."""
    with transaction() as conn:
        cursor = conn.execute(
            "UPDATE jobs SET retry_count = retry_count + 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (job_id,)
        )
        return cursor.rowcount > 0