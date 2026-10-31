# DELIVERY.md — Research Desk

Agent-delivered take-home for Confer Inc.

- **Live UI:** https://look-listening-salary-visitors.trycloudflare.com
- **Repo:** https://github.com/lanka-srinivasudu/research-desk

> The live link is served from my own machine through a Cloudflare Quick Tunnel.
> See section 8 for why, and for the Terraform that provisions the Oracle VM.
> If the link is down when you open it, email me and I will restart the tunnel.

---

## 1. Agent roster

| Agent | Runtime | Role | Model | Tools |
|---|---|---|---|---|
| `coordinator` | OpenClaw 2026.10.9 | Orchestrator | `nvidia/nemotron-3-ultra-550b-a55b:free` (OpenRouter) | shell, file ops, PDF extraction, `gh` CLI, subagent delegation |
| `reviewer2` | OpenClaw 2026.10.9 | Reviewer | same | shell, file ops, `gh` CLI |
| `builder1` | Hermes Agent | Builder | same | terminal, file ops, code execution, `gh` CLI, browser |
| `tester` | Hermes Agent | Tester | same | browser automation, web search (ddgs), terminal, `gh` CLI |

Two runtimes, four agents, four distinct roles. Each agent holds its own
OpenRouter API key so token spend is attributable per agent.

Configs, prompts and personas are in `agents/`, with secrets removed.

**A note on naming.** The reviewer is called `reviewer2` because the first
reviewer agent inherited an auth profile that stopped resolving mid-session.
Rather than debug OpenClaw's credential store against a deadline, I created a
replacement agent with known-good auth and moved on. `reviewer2` holds the
reviewer role throughout.

---

## 2. How a ticket moves from idea to merged code

```
          brief (PDF)
               |
               v
      +------------------+
      |   coordinator    |  reads brief, splits into tickets,
      |    (OpenClaw)    |  opens GitHub Issues, labels by agent
      +------------------+
               |
               |  Issue #N, labelled builder1
               v
      +------------------+
      |     builder1     |  branch ticket-N-*, commits as
      |     (Hermes)     |  "builder1 (Hermes)", opens PR "Closes #N"
      +------------------+
               |
               |  Pull Request
               v
      +------------------+
      |    reviewer2     |  reads PR against its Issue
      |    (OpenClaw)    |
      +------------------+
            /        \
     reject /          \ approve
           v            v
      back to      human merges
      builder1          |
      with reason       v
            ^    +------------------+
            |    |      tester      |  runs the deployed app,
            +----|     (Hermes)     |  files bug Issues
                 +------------------+
```

Tickets live as GitHub Issues and PRs, so every handoff is inspectable in the
repo. Both the review and the test step can send work back, and both did.

---

## 3. What each agent actually did

### `coordinator` (OpenClaw) — orchestrator

Read the brief PDF, produced a ten-line requirements summary, decomposed it
into tickets, created the `builder1` and `tester` labels, then opened
**Issues #7–#17** one at a time with acceptance criteria and per-agent labels.

After creating them it verified its own count without being asked, noticed it
had produced eleven rather than the ten it planned, explained exactly where the
extra one came from, and offered to merge two. It then updated its own stored
skill to add a count-verification step for next time.

### `builder1` (Hermes) — builder

Delivered four PRs, all merged:

- **PR #18** — SQLite jobs schema, migrations, 14 unit tests (Issue #8)
- **PR #19** — the whole core product: FastAPI app, submit form, board page,
  plan/research/review worker, OpenRouter client with retry/backoff
  (Issues #13, #14)
- **PR #21, #22** — fixes for the pipeline bug the tester found (Issue #20)

Every commit is authored `builder1 (Hermes) <builder1@agents.local>`, so the
git history separates agent work from mine. I only reviewed and merged.

### `reviewer2` (OpenClaw) — reviewer

Reviewed every PR against its ticket and **rejected two of them** with specific,
correct, written reasons:

- On **PR #18** it found a genuine data-corruption bug: `update_job()` passed
  the string `'CURRENT_TIMESTAMP'` as a SQL *parameter*, so SQLite stored the
  literal text instead of a timestamp. It quoted the file and line, explained
  the mechanism, gave the fix, and listed what was already correct.
- On **PR #19** it found five issues including the one that mattered most —
  jobs stalled at the plan stage because there was no background worker.

Both rejections were followed by a fix from `builder1` and a re-review. It
approved only after re-reading the diff.

### `tester` (Hermes) — tester

Ran the deployed app with real questions, found that every job failed at the
plan stage, read `app/worker.py` to work out why, and filed **Issue #20** with
the error text, what it observed, a root-cause diagnosis and a suggested patch.

Its diagnosis was wrong — see section 4 — but the bug report was accurate and
actionable, and it is what got the defect fixed.

---

## 4. What broke, and how it was caught

Three incidents are worth recording. The third is the one I learned most from.

### a) PDF extraction failed seven times, then recovered on its own

Asked to read the brief, `coordinator` called OpenClaw's built-in `pdf` tool
with malformed arguments and was rejected by schema validation. It corrected the
argument shape, retried, and hit a second error: no PDF model was configured on
this install. It fell back to the shell, which exited 127 (command not found),
tried `pdfplumber`, which exited 1 (not installed), installed `pdfplumber`, and
finally extracted the text.

Seven failed operations, no human intervention, correct output at the end. It
then wrote itself a reusable skill, `parse-brief-and-plan`, recording the
fallback chain.

**Caught by:** the tool layer returning structured validation errors and
non-zero exit codes rather than failing silently.

### b) Free-tier rate limits stopped the build twice

OpenRouter's free tier caps requests per key per day. Mid-way through creating
issues, `coordinator` hit:

```
429 Rate limit exceeded: free-models-per-day.
Add 10 credits to unlock 1000 free model requests per day
```

I re-ran onboarding with a second key and the remaining issues were created.
The next day `builder1` hit the same wall on its first coding ticket; Hermes
retried three times with exponential backoff (2.7s, 5.0s) before surfacing the
error and reporting the reset window.

**Caught by:** Hermes' built-in retry-with-backoff, which distinguished a
transient throttle from an exhausted daily quota.

**What I did:** purchased $10 of OpenRouter credit, which raises the free-model
limit from 200 to 1,000 requests per day. No paid models were used at any point
— every agent stayed pinned to `nemotron-3-ultra-550b-a55b:free`, and total
spend across the whole project was $0.02.

### c) The reviewer caught a real bug; the tester misdiagnosed a different one

This is the most interesting failure, because it shows both where the gates
worked and where they did not.

**The gate working.** On PR #18, `reviewer2` found the `updated_at` bug
described in section 3. That is a silent data-corruption defect that unit tests
passed straight over — all 14 tests were green. The reviewer caught what the
tests could not.

**The gate failing.** Every job in the deployed app was landing in *Needs
human* with `Plan failed: '\n  "steps"'`. The `tester` agent diagnosed it as a
JSON parsing failure caused by markdown code fences, filed Issue #20, and
`builder1` shipped PR #21 implementing exactly that fix. It merged, and the bug
persisted unchanged.

The real cause was different. `PLAN_PROMPT` contained an example JSON block with
literal `{` and `}` braces. When the code called `.format(question=...)` on it,
Python read those braces as format placeholders and raised
`KeyError: '\n  "steps"'` — a format-string error that merely *looked* like a
JSON error. The plan stage was dying before it ever reached the model.

I spotted it by reading the error class rather than the error text, pointed
`builder1` at the actual mechanism, and PR #22 fixed it by escaping the braces.
That agent then verified the fix by running both prompts through `.format()`
locally *before* committing — which is what PR #21 should have done.

**What this cost:** two agents, one issue, one PR and roughly forty minutes
spent confidently fixing the wrong thing. Neither the reviewer nor the tester
caught it, because both were reasoning about the error *message* rather than
reproducing the failure. The lesson I took is in section 7.

---

## 5. Token and model report

All four agents ran `nvidia/nemotron-3-ultra-550b-a55b:free` via OpenRouter,
one API key each, so the figures below are measured per agent rather than
estimated. Source: OpenRouter Activity dashboard.

**Totals:** 285 requests · 7.44M tokens · 62.6% cache hit rate · **$0.02 spend**

| Agent | Key | Tokens | Share | Phase |
|---|---|---|---|---|
| `builder1` | `sk-or-v1-7da…d67` | 4.33M | 58% | coding |
| `coordinator` | `sk-or-v1-246…3bc` | 2.39M | 32% | planning + orchestration |
| `reviewer2` | `sk-or-v1-a5d…3ee` | 503K | 7% | review |
| `tester` | `sk-or-v1-a0d…fe8` | 220K | 3% | test |

By runtime: Hermes Agent 4.53M, OpenClaw 2.89M.

### Where the tokens went, in plain words

**Coding dominates.** `builder1` burned 58% of all tokens. Writing code means
reading existing files, holding them in context, generating diffs and
re-reading to verify — every turn carries the codebase with it. The four
feature PRs account for nearly all of it.

**Planning is cheaper than it looks, but front-loaded.** `coordinator` used
32%, and almost all of that went on two things: extracting and reasoning about
the brief PDF (including the seven failed attempts, each of which still cost
tokens), and creating eleven GitHub issues one at a time. Orchestration itself —
deciding what the tickets are — was a small fraction.

**Review is remarkably cheap for its value.** `reviewer2` used 7% of tokens and
produced the single most valuable output in the project: a data-corruption bug
that 14 passing unit tests missed. Reading a diff is far cheaper than writing
one, which makes a review gate the best token-per-point-of-quality trade in the
whole pipeline.

**Testing is cheapest of all.** `tester` used 3%, mostly on browser interaction
and reading one file.

**Retries are invisible in this table but real.** The failed PDF attempts, the
429s, and the forty minutes spent on the misdiagnosed Issue #20 are all folded
into the coordinator and builder figures. A rough read of the session logs puts
retry and rework at 15–20% of total spend — the single biggest avoidable cost.

**Cache hit rate of 62.6% matters.** Without prompt caching the latency and
token volume would have been substantially higher, since each agent re-sends a
large system prompt and tool catalogue on every turn.

### Model choice

The brief suggests a strong model for planning and review, cheaper for routine
work. I ended up running the same free model everywhere, for an honest reason:
the free tier's genuinely strong option was Nemotron 3 Ultra 550B, and the
alternatives (`inkling-small`, `laguna-xs`, `nemotron-3.5-lightning`) were small
enough that I expected them to produce code the reviewer would reject — costing
more tokens in rework than they saved. With a budget I would put a cheap model
on `tester` and keep the strong one for coordinator, builder and reviewer.

---

## 6. Trace excerpts

### Orchestrator assigning work (`coordinator`, OpenClaw)

```
$ gh auth status && gh repo view lanka-srinivasudu/research-desk
Authenticated. Creating the two labels first, then the issues one at a time.
$ gh label create builder1 -R lanka-srinivasudu/research-desk --force \
    -d "Assigned to builder1 agent"
Labels ready. Now creating the issues one at a time.
$ gh issue create -R lanka-srinivasudu/research-desk \
    -t "Repo & Terraform skeleton" -l builder1 -b "..."
Issue created: #7
$ gh issue create -R lanka-srinivasudu/research-desk \
    -t "SQLite job schema & migrations" -l builder1 -b "..."
Issue created: #8
```

### Review rejection (`reviewer2`, OpenClaw → PR #18)

```
Verdict: NEEDS FIX — meets the three acceptance criteria in principle
but has a critical bug in update_job.

Bug: updated_at stores literal string 'CURRENT_TIMESTAMP'
In app/db.py:107:
    fields["updated_at"] = "CURRENT_TIMESTAMP"
This passes the string as a parameter, so SQLite stores the text
'CURRENT_TIMESTAMP' instead of the actual timestamp. The fix: include
updated_at = CURRENT_TIMESTAMP directly in the SQL SET clause.

What's correct:
  [x] Jobs table with all required columns
  [x] Migration runs idempotently via schema_version table
  [x] Unit tests covering CRUD, filtering, retries, idempotent init
```

### Handoff: fix pushed, re-review, approval (`builder1` → `reviewer2`)

```
builder1: Done. The fix has been pushed to the ticket-8-schema branch and
          the PR is updated.
          - update_job() was storing the literal string in updated_at
          - Fixed by including updated_at = CURRENT_TIMESTAMP in the SET clause
          - All 14 unit tests pass

reviewer2: Verdict: APPROVED — the updated_at bug is fixed. update_job now
           correctly builds updated_at = CURRENT_TIMESTAMP into the SQL SET
           clause inline, so SQLite evaluates it as a function and stores the
           actual timestamp. All three acceptance criteria are satisfied.
```

### Rate limit with retry and backoff (`builder1`, Hermes)

```
Attempt 1/3 failed: HTTP 429: Rate limit exceeded: free-models-per-day
Rate limited. Resets in ~7h 6m. Waiting 2.7s (attempt 2/3)...
Attempt 2/3 failed: HTTP 429: Rate limit exceeded: free-models-per-day
Rate limited. Resets in ~7h 6m. Waiting 5.0s (attempt 3/3)...
Attempt 3/3 failed: HTTP 429: Rate limit exceeded: free-models-per-day
Rate limited after 3 retries (resets in ~7h 6m)
```

### Tool failure and self-recovery (`coordinator`, OpenClaw)

```
[tools] tool_call failed: Invalid arguments for tool "openclaw:core:pdf":
        pdfs.0: must be string
[tools] tool_call failed: No PDF model configured.
        Extract text from BRIEF.pdf           Exit code 127
        Extract PDF text with pdfplumber      Exit code 1
        Install pdfplumber and extract        Exit code 1
        Install pdfplumber                    (ok)
        Extract PDF text                      (ok)
Learned: created skill parse-brief-and-plan
```

---

## 7. What I would change

**Make agents reproduce before they diagnose.** The single biggest waste was
Issue #20: the tester produced a confident, well-written, wrong root cause from
reading an error string, and the builder implemented it without reproducing the
failure first. Both agents behaved reasonably and the system still shipped the
wrong fix. I would add one line to the tester and builder prompts — *reproduce
the failure locally and paste the actual traceback before proposing a cause* —
and I would have the reviewer reject any fix PR whose body does not show a
before/after reproduction. PR #22 did exactly this voluntarily and was correct
first time.

**Give the reviewer the power to block, not just comment.** GitHub refuses a
formal `--request-changes` review when the reviewer authenticates as the PR
author, which both my agents did. The rejections are therefore comments, and
merging stayed a manual decision by me. With separate GitHub accounts (or a bot
token) per agent, the review gate would mechanically block the merge rather than
relying on me reading the comment. That is the difference between a gate and a
suggestion.

**Budget the rate limit as a first-class design constraint.** I planned the
agent team before understanding that the free tier caps *requests per key per
day*, not per minute. Four agents sharing a small daily budget ran dry twice and
cost me most of an evening. Knowing this, I would have started with one key per
agent, pinned explicit `:free` models from the outset instead of
`openrouter/auto`, and set a per-ticket request budget so the orchestrator could
schedule work against a known allowance.

**Stop conversing with agents; hand them whole tickets.** My early turns were
chatty — summarise this, now propose that — and each exchange cost a request
against a scarce budget. The work got dramatically more efficient once every
message was a complete, self-contained ticket ending in a concrete artifact (a
PR number, an issue number). Same with model pinning: `openrouter/auto` silently
routed toward paid models and produced confusing auth errors until I pinned
every agent explicitly.

**Test the product's own pipeline the way the delivery pipeline is tested.**
The delivery team had a review gate from the start. The product's
plan → research → review pipeline had no equivalent check until the tester ran
it against the deployed app and found every job dying at stage one. An
end-to-end smoke test in CI, running one question through all three stages,
would have caught that in minutes rather than hours.

---

## 8. Infrastructure, and an honest note on Oracle

`infra/` contains Terraform that provisions the Oracle Cloud Always Free stack:

- One `VM.Standard.A1.Flex` instance, 2 OCPU / 12 GB RAM, Ubuntu 24.04 aarch64
- A VCN, public subnet, internet gateway and route table
- Security rules for ports 22, 80 and 443
- Availability domain chosen by index, with no fault domain pinned, so Oracle
  can place the instance wherever Always Free capacity exists

It stays inside the allowance Oracle reduced from 4 OCPU / 24 GB to 2 OCPU /
12 GB in mid-2026 — several guides online are still stale on this.

**It is written and validated, but not applied.** Oracle requires a payment card
at signup for identity verification, which I did not have when I started. The
brief names the fallback for exactly this case, so I took it: the app runs on my
own machine behind a Cloudflare Quick Tunnel, and I am telling you plainly
rather than implying a VM exists.

Secrets stay out of git: `.gitignore` covers `*.tfstate`, `*.tfstate.*`,
`.terraform/`, `terraform.tfvars`, `*.pem` and `.env`. A
`terraform.tfvars.example` shows the shape without the values. I verified before
each push that no `sk-or-v1-` string appears anywhere in the repo.

---

## 9. Reproduce

### Infrastructure

```bash
cd infra/
cp terraform.tfvars.example terraform.tfvars   # fill in your OCI details
terraform init
terraform apply
```

Outputs the VM's public IP, an SSH command and the board URL. If Oracle returns
"Out of host capacity", change `availability_domain_index` or drop to 1 OCPU /
6 GB rather than pinning a fault domain.

### Agent runtimes

```bash
curl -fsSL https://openclaw.ai/install.sh | bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
```

Then restore the team:

```bash
# OpenClaw: coordinator and reviewer2
openclaw onboard                       # choose OpenRouter, supply a key
openclaw agents add                    # name: reviewer2
# config reference: agents/openclaw.config.json

# Hermes: builder1 and tester
hermes setup                           # choose OpenRouter, supply a key
hermes profile create builder1 --clone
hermes profile create tester  --clone
# per-agent keys go in ~/.hermes/profiles/<name>/.env
```

Pin every agent to `openrouter/nvidia/nemotron-3-ultra-550b-a55b:free`. The
`openrouter/` prefix matters — without it OpenClaw reads `nvidia` as the
provider and fails auth.

### The app

```bash
pip install -r requirements.txt
export OPENROUTER_API_KEY=sk-or-v1-...
python3 -m uvicorn app.main:app --port 8000
```

Then either serve it on the VM behind Caddy or nginx, or expose it with:

```bash
cloudflared tunnel --url http://localhost:8000
```

### Verify it works

Submit *"What are the trade-offs of running small language models on-device?"*
It should reach **Published** in two to three minutes with a source link on
every claim. Then submit something no public source can answer — *"What did my
neighbour have for breakfast on 14 March 2019?"* — and watch it retry once and
land in **Needs human** instead of being published.
