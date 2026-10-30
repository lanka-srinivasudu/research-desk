# Agent delivery team

Four agents across two runtimes, as the brief requires.

| Agent | Runtime | Role | Model | Key tools |
|---|---|---|---|---|
| `coordinator` | OpenClaw | Orchestrator | `nvidia/nemotron-3-ultra-550b-a55b:free` via OpenRouter | shell, file, PDF read, `gh` CLI, subagent delegation |
| `reviewer` | OpenClaw | Reviewer | same | shell, file, `gh` CLI |
| `builder1` | Hermes Agent | Builder | same | terminal, file ops, code execution, `gh` CLI |
| `tester` | Hermes Agent | Tester | same | browser automation, web search (ddgs), terminal, `gh` CLI |

## How tickets flow

GitHub Issues and Pull Requests are the shared ticket board, so every
handoff is inspectable in the repo itself.

1. `coordinator` reads the brief, splits it into tickets, and opens them
   as GitHub Issues labelled `builder1` or `tester`.
2. `builder1` picks up an issue, works on a `ticket-N-*` branch, commits
   under its own git identity, and opens a PR saying `Closes #N`.
3. `reviewer` reads the PR against its issue and either approves it or
   rejects it with a written reason, sending the work back.
4. `tester` runs the deployed app with real questions and files bug
   issues when something slips through.

The review and test steps can both send work back, so the gates can
genuinely block bad work rather than just commenting on it.

## Model choice

All four agents run the same free Nemotron Ultra model through
OpenRouter, each on its own API key so token usage can be attributed per
agent. One key per agent also spreads the free tier's per-key daily
request cap across the team.

## Files here

- `openclaw.config.json` — the OpenClaw config for `coordinator` and
  `reviewer`, with the gateway auth token stripped.
- `coordinator/`, `reviewer/` — identity and persona files.
- `builder1/`, `tester/` — Hermes profile configs and personas.

No API keys or tokens are committed. Credentials live in `.env` files
outside the repo and in each Hermes profile's own home directory.
