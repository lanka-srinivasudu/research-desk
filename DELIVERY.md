# DELIVERY.md — Research Desk

Agent-delivered take-home for Confer Inc.
Repo: https://github.com/lanka-srinivasudu/research-desk

---

## 1. Agent roster

| Agent | Runtime | Role | Model | Tools |
|---|---|---|---|---|
| `coordinator` | OpenClaw 2026.10.9 | Orchestrator | `nvidia/nemotron-3-ultra-550b-a55b:free` (OpenRouter) | shell, file ops, PDF extraction, `gh` CLI, subagent delegation |
| `reviewer` | OpenClaw 2026.10.9 | Reviewer | same | shell, file ops, `gh` CLI |
| `builder1` | Hermes Agent | Builder | same | terminal, file ops, code execution, `gh` CLI |
| `tester` | Hermes Agent | Tester | same | browser automation, web search (ddgs), terminal, `gh` CLI |

Each agent holds its own OpenRouter API key, so token spend is attributable
per agent and the free tier's per-key daily cap is spread across the team.

Configs and prompts are in `agents/`, with secrets removed.

---

## 2. How a ticket moves from idea to merged code

```
          brief (PDF)
               |
               v
      +------------------+
      |   coordinator    |  reads brief, splits into tickets
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
      |     reviewer     |  reads PR against its Issue
      |    (OpenClaw)    |
      +------------------+
            /        \
     reject /          \ approve
           v            v
      back to      human merges
      builder1          |
      with reason       v
                 +------------------+
                 |      tester      |  runs the deployed app,
                 |     (Hermes)     |  files bug Issues
                 +------------------+
```

Tickets live as GitHub Issues and PRs, so every handoff is inspectable in
the repo. Both the review and test steps can send work back.

---

## 3. What each agent actually did

**`coordinator`** — read the brief PDF, produced a ten-line requirements
summary, decomposed it into tickets, and created them as GitHub Issues
#7–#17 with acceptance criteria and per-agent labels. It created the
`builder1` and `tester` labels first. After creating the issues it verified
its own count, noticed it had produced eleven rather than ten, and explained
the discrepancy without being asked.

**`builder1`** — _to be filled in._

**`reviewer`** — _to be filled in._

**`tester`** — _to be filled in._

---

## 4. One thing that broke, and how it was caught

Two are worth recording.

### PDF extraction failed seven times, then recovered

Asked to read the brief, `coordinator` called OpenClaw's built-in `pdf` tool
with malformed arguments and was rejected by the tool's schema validation.
It corrected the argument shape, retried, and hit a second error: no PDF
model was configured on this install. It then fell back to the shell, which
exited 127 (command not found), tried `pdfplumber`, which exited 1 (not
installed), installed `pdfplumber`, and finally extracted the text
successfully.

Seven failed operations, no human intervention, correct output at the end.
It then wrote itself a reusable skill, `parse-brief-and-plan`, recording the
fallback chain so the next PDF does not repeat the discovery.

**Caught by:** the tool layer returning structured validation errors and
non-zero exit codes rather than silently succeeding.

### Free-tier rate limits capped the build

OpenRouter's free tier enforces a per-key daily request cap. Mid-way through
creating issues, `coordinator` hit:

```
429 Rate limit exceeded: free-models-per-day.
Add 10 credits to unlock 1000 free model requests per day
```

The first key was exhausted. Re-running onboarding with a second key
restored service and the remaining issues were created. When `builder1` was
later given its first coding ticket, Hermes retried three times with
exponential backoff (2.7s, 5.0s) before surfacing the error and reporting
the reset time.

**Caught by:** Hermes' built-in retry-with-backoff, which distinguished a
transient throttle from an exhausted daily quota and reported the reset
window rather than failing silently.

**Impact, stated honestly:** this capped how much feature code the agents
could produce within the delivery window. See section 7.

---

## 5. Token and model report

_To be completed._

All agents ran `nvidia/nemotron-3-ultra-550b-a55b:free` via OpenRouter, one
key per agent. Per-agent usage is visible on each key's OpenRouter activity
page.

| Agent | Phase | Requests | Notes |
|---|---|---|---|
| coordinator | planning | — | brief read, summary, ticket decomposition |
| coordinator | orchestration | — | GitHub issue creation |
| builder1 | coding | — | |
| reviewer | review | — | |
| tester | test | — | |

Where the tokens went, in plain words: _to be completed._

---

## 6. Trace excerpts

### Rate limit with retry and backoff (`builder1`, Hermes)

```
Attempt 1/3 failed: HTTP 429: Rate limit exceeded: free-models-per-day
Rate limited. Resets in ~7h 6m. Waiting 2.7s (attempt 2/3)...
Attempt 2/3 failed: HTTP 429: Rate limit exceeded: free-models-per-day
Rate limited. Resets in ~7h 6m. Waiting 5.0s (attempt 3/3)...
Attempt 3/3 failed: HTTP 429: Rate limit exceeded: free-models-per-day
Rate limited after 3 retries (resets in ~7h 6m)
```

### Tool-level failure and self-correction (`coordinator`, OpenClaw)

```
[tools] tool_call failed: Invalid arguments for tool "openclaw:core:pdf":
        pdfs.0: must be string
[tools] tool_call failed: No PDF model configured.
        Extract text from BRIEF.pdf           Exit code 127
        Extract PDF text with pdfplumber      Exit code 1
        Install pdfplumber and extract        Exit code 1
        Install pdfplumber                    (ok)
        Extract PDF text                      (ok)
```

### Orchestrator assigning work (`coordinator`, OpenClaw)

```
$ gh label create builder1 -R lanka-srinivasudu/research-desk --force
Labels ready. Now creating the issues one at a time.
$ gh issue create -R lanka-srinivasudu/research-desk \
    -t "Repo & Terraform skeleton" -l builder1 -b "..."
Issue created: #7
$ gh issue create -R lanka-srinivasudu/research-desk \
    -t "SQLite job schema & migrations" -l builder1 -b "..."
Issue created: #8
```

---

## 7. What I would change

_To be completed._

---

## 8. Reproduce

### Infrastructure

```bash
cd infra/
cp terraform.tfvars.example terraform.tfvars   # fill in your OCI details
terraform init
terraform apply
```

This provisions one Oracle Cloud Always Free `VM.Standard.A1.Flex` instance
(2 OCPU / 12 GB RAM, Ubuntu 24.04 aarch64), a VCN, a public subnet, and
security rules for ports 22, 80 and 443. It stays inside the Always Free
allowance, which Oracle reduced from 4 OCPU / 24 GB to 2 OCPU / 12 GB in
mid-2026.

State files, `terraform.tfvars` and `*.pem` keys are git-ignored.

### Agent runtimes

```bash
curl -fsSL https://openclaw.ai/install.sh | bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
```

Then restore the agent team:

```bash
# OpenClaw: coordinator and reviewer
openclaw onboard                       # choose OpenRouter, supply a key
# config in agents/openclaw.config.json

# Hermes: builder1 and tester
hermes setup                           # choose OpenRouter, supply a key
hermes profile create builder1 --clone
hermes profile create tester --clone
# per-profile keys go in ~/.hermes/profiles/<name>/.env
```
