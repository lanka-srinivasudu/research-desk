"""Worker that processes jobs through plan -> research -> review pipeline."""

import json
from typing import Optional

from .db import (
    get_job,
    update_job,
    list_jobs,
    increment_retry_count,
    VALID_STAGES,
)
from .llm import get_client


# --- Prompts ---

PLAN_PROMPT = """You are a research planner. Given a user's question, create a concise research plan.

Return ONLY a JSON object with these fields:
- "steps": array of strings, each a concrete search/action step
- "sources": array of strings, suggested source types (e.g., "arXiv", "Wikipedia", "news", "official docs")

Example:
{
  "steps": [
    "Search arXiv for recent papers on transformer scaling laws",
    "Find Wikipedia article on Chinchilla scaling law",
    "Check OpenAI blog for GPT-4 technical details"
  ],
  "sources": ["arXiv", "Wikipedia", "official blogs"]
}

User question: {question}"""

RESEARCH_PROMPT = """You are a researcher. Execute the research plan and produce a cited answer.

Plan:
{plan}

Previous research output (if any): {previous_research}

Review feedback (if rejected): {review_feedback}

Rules:
1. Use ONLY real, publicly accessible sources (Wikipedia, arXiv, official docs, reputable news)
2. Every factual claim MUST have a source citation in [brackets] with a real URL
3. Format: "Claim [https://example.com/source]"
4. If you cannot find a source for a claim, omit the claim
5. Synthesize findings into a coherent answer
6. At the end, list all sources used with full URLs

Return your research output as plain text."""

REVIEW_PROMPT = """You are a reviewer evaluating research quality. Be strict.

Research output:
{research}

Criteria for REJECTION (any one triggers rejection):
- Claims without source citations (no [URL] after factual statements)
- Sources that are not real/publicly accessible (no hallucinated URLs)
- Answer does not address the original question
- Contradictory or hallucinated information
- Less than 3 distinct sources cited
- Sources are not authoritative for the topic

If REJECTING: Return ONLY a JSON object:
{{"decision": "reject", "reason": "Specific reason for rejection"}}

If ACCEPTING: Return ONLY a JSON object:
{{"decision": "accept", "final_answer": "The polished final answer with all citations preserved"}}

Original question: {question}"""


def run_plan(job_id: int) -> bool:
    """Stage 1: Create a research plan."""
    job = get_job(job_id)
    if not job:
        return False

    client = get_client()
    try:
        response = client.chat([
            {"role": "system", "content": "You are a research planner. Output only valid JSON."},
            {"role": "user", "content": PLAN_PROMPT.format(question=job["question"])},
        ])
        plan = json.loads(response)
        update_job(job_id, stage="research", plan_output=json.dumps(plan, indent=2))
        return True
    except Exception as e:
        update_job(job_id, stage="needs_human", review_output=f"Plan failed: {e}")
        return False


def run_research(job_id: int) -> bool:
    """Stage 2: Execute research plan."""
    job = get_job(job_id)
    if not job:
        return False

    plan = job["plan_output"] or "{}"
    previous_research = job["research_output"] or ""
    review_feedback = job["review_output"] or ""

    client = get_client()
    try:
        response = client.chat([
            {"role": "system", "content": "You are a researcher. Cite every claim with a real URL."},
            {"role": "user", "content": RESEARCH_PROMPT.format(
                plan=plan,
                previous_research=previous_research,
                review_feedback=review_feedback,
            )},
        ])
        update_job(job_id, stage="review", research_output=response)
        return True
    except Exception as e:
        update_job(job_id, stage="needs_human", review_output=f"Research failed: {e}")
        return False


def run_review(job_id: int) -> bool:
    """Stage 3: Review research output."""
    job = get_job(job_id)
    if not job:
        return False

    client = get_client()
    try:
        response = client.chat([
            {"role": "system", "content": "You are a strict reviewer. Output only valid JSON."},
            {"role": "user", "content": REVIEW_PROMPT.format(
                research=job["research_output"],
                question=job["question"],
            )},
        ])
        result = json.loads(response)

        if result["decision"] == "accept":
            update_job(job_id, stage="published", review_output=result["final_answer"])
            return True
        else:
            # Rejected - check retry count
            retry_count = job["retry_count"]
            if retry_count == 0:
                # First rejection - go back to research with feedback
                update_job(
                    job_id,
                    stage="research",
                    review_output=result["reason"],
                )
                increment_retry_count(job_id)
                return True
            else:
                # Second rejection - needs human
                update_job(
                    job_id,
                    stage="needs_human",
                    review_output=f"Rejected after retry: {result['reason']}",
                )
                return False
    except Exception as e:
        update_job(job_id, stage="needs_human", review_output=f"Review failed: {e}")
        return False


def process_job(job_id: int) -> bool:
    """Process a single job through the pipeline based on its current stage."""
    job = get_job(job_id)
    if not job:
        return False

    stage = job["stage"]

    if stage == "plan":
        return run_plan(job_id)
    elif stage == "research":
        return run_research(job_id)
    elif stage == "review":
        return run_review(job_id)
    elif stage in ("published", "needs_human"):
        # Already terminal
        return True
    else:
        return False


def process_queued_jobs(limit: int = 10) -> int:
    """Process all jobs that are not in a terminal state."""
    processed = 0
    for stage in ("plan", "research", "review"):
        jobs = list_jobs(stage=stage, limit=limit)
        for job in jobs:
            if process_job(job["id"]):
                processed += 1
    return processed


if __name__ == "__main__":
    # CLI entry point for running the worker
    import sys
    if len(sys.argv) > 1:
        # Process specific job
        job_id = int(sys.argv[1])
        process_job(job_id)
    else:
        # Process all queued
        count = process_queued_jobs()
        print(f"Processed {count} jobs")