"""FastAPI app for research-desk: submit questions, view job board."""

import asyncio
import os
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .db import init_db, create_job, get_job, list_jobs, VALID_STAGES
from .worker import process_job, process_queued_jobs


# --- Setup ---

BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
TEMPLATES_DIR.mkdir(exist_ok=True)
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    
    # Background worker task
    async def background_worker():
        while True:
            try:
                process_queued_jobs(limit=10)
            except Exception:
                pass  # Log in production
            await asyncio.sleep(5)
    
    worker_task = asyncio.create_task(background_worker())
    yield
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Research Desk", lifespan=lifespan)


# --- HTML Templates ---

INDEX_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Research Desk</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 720px; margin: 2rem auto; padding: 0 1rem; line-height: 1.6; }
        h1 { color: #1a1a2e; margin-bottom: 0.5rem; }
        .subtitle { color: #666; margin-bottom: 2rem; }
        form { display: flex; flex-direction: column; gap: 1rem; }
        textarea { width: 100%; min-height: 120px; padding: 0.75rem; border: 1px solid #ddd; border-radius: 8px; font-family: inherit; font-size: 1rem; resize: vertical; }
        textarea:focus { outline: none; border-color: #3b82f6; box-shadow: 0 0 0 3px rgba(59,130,246,0.1); }
        button { background: #3b82f6; color: white; border: none; padding: 0.75rem 1.5rem; border-radius: 8px; font-size: 1rem; font-weight: 600; cursor: pointer; align-self: flex-start; }
        button:hover { background: #2563eb; }
        .flash { background: #dcfce7; color: #166534; padding: 1rem; border-radius: 8px; margin-bottom: 1rem; }
        .error { background: #fee2e2; color: #991b1b; }
        a { color: #3b82f6; text-decoration: none; }
        a:hover { text-decoration: underline; }
        .footer { margin-top: 3rem; color: #999; font-size: 0.875rem; }
    </style>
</head>
<body>
    <h1>Research Desk</h1>
    <p class="subtitle">Submit a research question. We'll plan, research, and review the answer.</p>

    {% if flash %}
    <div class="flash {{ 'error' if flash_type == 'error' else '' }}">{{ flash }}</div>
    {% endif %}

    <form method="post" action="/submit">
        <textarea name="question" placeholder="What do you want researched? Be specific..." required></textarea>
        <button type="submit">Submit Question</button>
    </form>

    <p class="footer"><a href="/board">View job board &rarr;</a></p>
</body>
</html>
"""

BOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Job Board - Research Desk</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 1000px; margin: 2rem auto; padding: 0 1rem; line-height: 1.6; }
        h1 { color: #1a1a2e; margin-bottom: 0.5rem; }
        .subtitle { color: #666; margin-bottom: 2rem; }
        .section { margin-bottom: 3rem; }
        .section h2 { color: #1a1a2e; border-bottom: 2px solid #e5e7eb; padding-bottom: 0.5rem; margin-bottom: 1rem; }
        .section.needs-human h2 { border-color: #fca5a5; color: #991b1b; }
        .job-card { background: #fafafa; border: 1px solid #e5e7eb; border-radius: 12px; padding: 1.25rem; margin-bottom: 1rem; }
        .job-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.75rem; gap: 1rem; }
        .job-question { font-weight: 600; color: #1a1a2e; flex: 1; }
        .job-stage { padding: 0.25rem 0.75rem; border-radius: 9999px; font-size: 0.75rem; font-weight: 600; text-transform: uppercase; white-space: nowrap; }
        .stage-plan { background: #dbeafe; color: #1e40af; }
        .stage-research { background: #fef3c7; color: #92400e; }
        .stage-review { background: #e0e7ff; color: #3730a3; }
        .stage-published { background: #dcfce7; color: #166534; }
        .stage-needs-human { background: #fee2e2; color: #991b1b; }
        .job-meta { font-size: 0.875rem; color: #666; margin-bottom: 1rem; }
        .job-answer { background: white; border: 1px solid #e5e7eb; border-radius: 8px; padding: 1rem; white-space: pre-wrap; font-size: 0.9375rem; line-height: 1.7; }
        .job-answer a { color: #3b82f6; text-decoration: underline; }
        .empty { color: #999; font-style: italic; padding: 2rem; text-align: center; }
        .nav { margin-bottom: 2rem; }
        .nav a { color: #3b82f6; text-decoration: none; }
        .nav a:hover { text-decoration: underline; }
        .retry-info { font-size: 0.8125rem; color: #f59e0b; background: #fef3c7; padding: 0.5rem 0.75rem; border-radius: 6px; margin-top: 0.5rem; }
    </style>
</head>
<body>
    <div class="nav"><a href="/">&larr; Back to submit</a></div>
    <h1>Job Board</h1>
    <p class="subtitle">All research jobs and their current status</p>

    {% for stage_name, stage_label, jobs in active_sections %}
    <div class="section">
        <h2>{{ stage_label }} ({{ jobs|length }})</h2>
        {% if jobs %}
            {% for job in jobs %}
            <div class="job-card">
                <div class="job-header">
                    <span class="job-question">{{ job.question }}</span>
                    <span class="job-stage stage-{{ job.stage }}">{{ job.stage.replace('_', ' ') }}</span>
                </div>
                <div class="job-meta">ID: {{ job.id }} | Created: {{ job.created_at }} | Updated: {{ job.updated_at }}</div>
                {% if job.retry_count > 0 %}
                <div class="retry-info">Retry count: {{ job.retry_count }}</div>
                {% endif %}
                {% if job.review_output and job.stage in ['published', 'needs_human'] %}
                <div class="job-answer">{{ job.review_output }}</div>
                {% elif job.research_output %}
                <div class="job-answer">{{ job.research_output }}</div>
                {% elif job.plan_output %}
                <div class="job-answer"><em>Plan:</em>\n{{ job.plan_output }}</div>
                {% else %}
                <div class="job-answer"><em>Processing...</em></div>
                {% endif %}
            </div>
            {% endfor %}
        {% else %}
            <div class="empty">No jobs in this stage</div>
        {% endif %}
    </div>
    {% endfor %}

    {% if needs_human_jobs %}
    <div class="section needs-human">
        <h2>Needs Human Review ({{ needs_human_jobs|length }})</h2>
        {% for job in needs_human_jobs %}
        <div class="job-card">
            <div class="job-header">
                <span class="job-question">{{ job.question }}</span>
                <span class="job-stage stage-needs-human">Needs Human</span>
            </div>
            <div class="job-meta">ID: {{ job.id }} | Created: {{ job.created_at }} | Updated: {{ job.updated_at }}</div>
            <div class="retry-info">Failed review: {{ job.review_output or 'No reason recorded' }}</div>
            {% if job.research_output %}
            <div class="job-answer"><strong>Last research output:</strong>\n{{ job.research_output }}</div>
            {% endif %}
        </div>
        {% endfor %}
    </div>
    {% endif %}
</body>
</html>
"""

# Write templates to files
(TEMPLATES_DIR / "index.html").write_text(INDEX_HTML)
(TEMPLATES_DIR / "board.html").write_text(BOARD_HTML)


# --- Routes ---

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {"request": request})


@app.post("/submit")
async def submit_question(request: Request, question: str = Form(...)):
    question = question.strip()
    if not question:
        return templates.TemplateResponse(request, "index.html", {
            "request": request,
            "flash": "Question cannot be empty",
            "flash_type": "error",
        })

    job_id = create_job(question, stage="plan")
    # Process synchronously for now (plan stage)
    process_job(job_id)

    return RedirectResponse(url="/board", status_code=303)


@app.get("/board", response_class=HTMLResponse)
async def board(request: Request):
    # Group jobs by stage
    stage_order = ["plan", "research", "review", "published"]
    stage_labels = {
        "plan": "Planning",
        "research": "Researching",
        "review": "In Review",
        "published": "Published",
    }

    active_sections = []
    for stage in stage_order:
        jobs = list_jobs(stage=stage, limit=50)
        active_sections.append((stage, stage_labels[stage], jobs))

    needs_human_jobs = list_jobs(stage="needs_human", limit=50)

    return templates.TemplateResponse(request, "board.html", {
        "request": request,
        "active_sections": active_sections,
        "needs_human_jobs": needs_human_jobs,
    })


@app.post("/board/process/{job_id}")
async def process_job_endpoint(job_id: int):
    """Manually trigger processing for a job (useful for testing)."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    process_job(job_id)
    return RedirectResponse(url="/board", status_code=303)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)