# Job Copilot

A Streamlit web app that turns a resume into a targeted job search: upload your
resume, get live openings ranked against it, then rewrite the resume and draft a
cover letter for whichever posting you pick.

The same scoring and fetching engine also ships as an **MCP server** for use
inside Claude Desktop / Claude Code (see [MCP server](#mcp-server-optional)).

## What it does

| Step | Page | What happens |
|------|------|--------------|
| 1 | **Resume** | Upload PDF/DOCX/TXT/MD (or paste). Text is extracted and left editable. |
| 2 | **Find jobs** | Pulls live openings from public job APIs and ranks them against your resume. |
| 3 | **Tailor resume** | Keyword gap analysis, plus a Claude-rewritten resume targeting one posting. |
| 4 | **Cover letter** | A grounded three-paragraph draft, or a fill-in scaffold with no API key. |
| 5 | **Tracker** | Session log of what you applied to, exportable as CSV. |

Downloads are available as `.md` and `.docx` at every generation step.

### Job sources

Only **public, automation-friendly APIs** — Greenhouse, Lever, Ashby, RemoteOK,
Remotive, The Muse, SmartRecruiters, and Adzuna. LinkedIn and Indeed prohibit
automated access and are deliberately not scraped.

### Ranking

Scoring is local and deterministic (`jobapply_mcp/matching.py`) — no LLM call, no
network. It combines resume↔posting cosine similarity with title-role bonuses,
seniority penalties, salary extraction, and visa-sponsorship signals.

## Privacy

Resumes live in the Streamlit **session** only — never written to disk, never
shared between visitors, cleared when the tab closes. An API key typed into the
sidebar is used for that session and not stored.

## Run it locally

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run streamlit_app.py
```

Then open http://localhost:8501.

### Optional keys

Both are optional — job search, scoring, gap analysis, and the cover-letter
scaffold all work without them.

| Key | Enables |
|-----|---------|
| `ANTHROPIC_API_KEY` | Claude-written resume tailoring and cover letters |
| `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` | Nationwide US aggregation ([free keys](https://developer.adzuna.com)) |

Set them as environment variables, or copy `.streamlit/secrets.toml.example` to
`.streamlit/secrets.toml` and fill it in. Users can also paste their own
Anthropic key into the sidebar at runtime.

## Deploy to Streamlit Community Cloud

1. Push this repo to GitHub.
2. At [share.streamlit.io](https://share.streamlit.io), click **New app** and
   point it at this repo.
3. Set **Main file path** to `streamlit_app.py`.
4. Under **Advanced settings → Secrets**, paste the contents of your
   `.streamlit/secrets.toml` (optional).
5. Deploy.

`requirements.txt` holds only what the web app needs. The heavier MCP and
Playwright dependencies live in `requirements-mcp.txt` so cloud builds stay fast.

## Configuring which companies to watch

`config.json` lists the Greenhouse/Lever/Ashby board tokens to poll — usually the
company slug from their careers URL (e.g. `boards.greenhouse.io/<token>`).

**The committed `config.json` is an example.** Copy it to `config.local.json` and
edit that instead:

```bash
cp config.json config.local.json
```

`config.local.json` is gitignored and takes precedence when present, so your real
target companies, salary floor, and filters stay off GitHub. The **Find jobs**
page and the CLI both pick it up automatically.

Never put real API keys in either file. Keys belong in environment variables or
Streamlit secrets.

## MCP server (optional)

The same engine runs as an MCP server so Claude can search and draft
conversationally.

```bash
pip install -r requirements-mcp.txt
```

| Tool | What it does |
|------|--------------|
| `search_jobs` | Pulls live openings from the configured boards |
| `score_jobs`  | Ranks openings against your resume (local, deterministic) |
| `get_job`     | Returns the full description for one job |
| `save_resume` / `get_resume` | Stores/returns your resume text |
| `save_draft` / `list_drafts` | Writes and lists tailored drafts |
| `mark_applied` | Logs an application and files its draft |

A project-scoped `.mcp.json` is included for Claude Code. For Claude Desktop, add
to `claude_desktop_config.json` (Settings → Developer → Edit Config):

```json
{
  "mcpServers": {
    "jobapply": {
      "command": "python",
      "args": ["-m", "jobapply_mcp.server"],
      "cwd": "/absolute/path/to/this/repo"
    }
  }
}
```

### Assisted apply (Playwright)

Fills a Greenhouse form from `profile.json` plus a saved draft, then **pauses for
you to review and click Submit**. It never submits on its own.

```bash
.venv\Scripts\python.exe -m playwright install chromium
.venv\Scripts\python.exe -m jobapply_mcp.cli apply greenhouse:<company>:<job-id>
```

### CLI

```bash
python -m jobapply_mcp.cli search --query python --remote
```
