"""Unit tests for the jobs database module."""

import os
import tempfile
import unittest
from pathlib import Path

# Set test database path before importing db module
TEST_DB = Path(tempfile.gettempdir()) / "test_jobs.db"
os.environ["JOBS_DB_PATH"] = str(TEST_DB)

import sys
sys.path.insert(0, str(Path(__file__).parent))

from db import (
    init_db,
    create_job,
    get_job,
    update_job,
    list_jobs,
    increment_retry_count,
    VALID_STAGES,
    DB_PATH,
)


class TestJobsDatabase(unittest.TestCase):
    """Test cases for jobs database operations."""

    def setUp(self):
        """Set up a fresh database for each test."""
        # Override DB_PATH for testing
        import db
        db.DB_PATH = TEST_DB
        # Remove any existing test database
        if TEST_DB.exists():
            TEST_DB.unlink()
        init_db()

    def tearDown(self):
        """Clean up test database."""
        if TEST_DB.exists():
            TEST_DB.unlink()

    def test_init_db_creates_jobs_table(self):
        """Test that init_db creates the jobs table with all columns."""
        job_id = create_job("Test question")
        job = get_job(job_id)
        
        self.assertIsNotNone(job)
        if job is None:
            return
        self.assertEqual(job["question"], "Test question")
        self.assertEqual(job["stage"], "plan")
        self.assertEqual(job["plan_output"], None)
        self.assertEqual(job["research_output"], None)
        self.assertEqual(job["review_output"], None)
        self.assertEqual(job["retry_count"], 0)
        self.assertIsNotNone(job["created_at"])
        self.assertIsNotNone(job["updated_at"])

    def test_create_job_with_custom_stage(self):
        """Test creating a job with a specific stage."""
        job_id = create_job("Research question", "research")
        job = get_job(job_id)
        
        self.assertIsNotNone(job)
        if job is None:
            return
        self.assertEqual(job["stage"], "research")

    def test_create_job_invalid_stage_raises(self):
        """Test that creating a job with invalid stage raises ValueError."""
        with self.assertRaises(ValueError):
            create_job("Test", "invalid_stage")

    def test_get_job_returns_none_for_missing(self):
        """Test that get_job returns None for non-existent job."""
        job = get_job(999)
        self.assertIsNone(job)

    def test_update_job_updates_fields(self):
        """Test updating job fields."""
        job_id = create_job("Original question")
        
        result = update_job(job_id, question="Updated question", stage="research", plan_output="Plan done")
        self.assertTrue(result)
        
        job = get_job(job_id)
        self.assertIsNotNone(job)
        if job is None:
            return
        self.assertEqual(job["question"], "Updated question")
        self.assertEqual(job["stage"], "research")
        self.assertEqual(job["plan_output"], "Plan done")

    def test_update_job_invalid_stage_raises(self):
        """Test that updating with invalid stage raises ValueError."""
        job_id = create_job("Test")
        with self.assertRaises(ValueError):
            update_job(job_id, stage="invalid")

    def test_update_job_returns_false_for_missing(self):
        """Test that updating non-existent job returns False."""
        result = update_job(999, question="Test")
        self.assertFalse(result)

    def test_list_jobs_returns_all(self):
        """Test listing all jobs."""
        create_job("Job 1")
        create_job("Job 2")
        create_job("Job 3")
        
        jobs = list_jobs()
        self.assertEqual(len(jobs), 3)

    def test_list_jobs_filters_by_stage(self):
        """Test listing jobs filtered by stage."""
        create_job("Plan job", "plan")
        create_job("Research job", "research")
        create_job("Another plan", "plan")
        
        plan_jobs = list_jobs(stage="plan")
        self.assertEqual(len(plan_jobs), 2)
        for job in plan_jobs:
            self.assertEqual(job["stage"], "plan")

    def test_list_jobs_invalid_stage_raises(self):
        """Test that listing with invalid stage raises ValueError."""
        with self.assertRaises(ValueError):
            list_jobs(stage="invalid")

    def test_increment_retry_count(self):
        """Test incrementing retry count."""
        job_id = create_job("Test")
        
        job = get_job(job_id)
        self.assertIsNotNone(job)
        if job is None:
            return
        self.assertEqual(job["retry_count"], 0)
        
        result = increment_retry_count(job_id)
        self.assertTrue(result)
        
        job = get_job(job_id)
        self.assertIsNotNone(job)
        if job is None:
            return
        self.assertEqual(job["retry_count"], 1)
        
        increment_retry_count(job_id)
        job = get_job(job_id)
        self.assertIsNotNone(job)
        if job is None:
            return
        self.assertEqual(job["retry_count"], 2)

    def test_increment_retry_count_missing_job(self):
        """Test incrementing retry count for missing job returns False."""
        result = increment_retry_count(999)
        self.assertFalse(result)

    def test_migration_runs_idempotently(self):
        """Test that init_db can be called multiple times without error."""
        init_db()
        init_db()
        init_db()
        
        # Should still work normally
        job_id = create_job("Test after re-init")
        job = get_job(job_id)
        self.assertIsNotNone(job)

    def test_all_valid_stages_accepted(self):
        """Test that all valid stages can be used."""
        for stage in VALID_STAGES:
            job_id = create_job(f"Question for {stage}", stage)
            job = get_job(job_id)
            self.assertIsNotNone(job)
            if job is None:
                return
            self.assertEqual(job["stage"], stage)


if __name__ == "__main__":
    unittest.main()