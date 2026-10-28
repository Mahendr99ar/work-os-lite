# Work OS Lite

[![CI](https://github.com/Mahendr99ar/work-os-lite/actions/workflows/ci.yml/badge.svg)](https://github.com/Mahendr99ar/work-os-lite/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11-3776ab)
![FastAPI](https://img.shields.io/badge/FastAPI-backend-009688)
![React](https://img.shields.io/badge/react-18-61dafb)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-pgvector-336791)

**Live:** [work-os-lite-8crz.vercel.app](https://work-os-lite-8crz.vercel.app) (click "Open a demo workspace", no sign-up)

**API:** [health](https://work-os-lite.onrender.com/health) | [interactive docs](https://work-os-lite.onrender.com/docs)

**Author:** [Mahendra Meena](https://github.com/Mahendr99ar)

> The API is on Render's free plan, which sleeps after 15 minutes with no traffic. If the site can't reach the server, wait about a minute and refresh.

Work OS Lite is a task board for small teams with two AI features:

1. **Ask your documents.** Upload PDFs or notes and ask questions about them. The answer only uses those files and says which file it came from. If none of the files cover the question, the app says that instead of guessing.
2. **AI task planner.** Paste a rough project brief and the AI turns it into a list of tasks with dependencies. Nothing goes on the board until an admin approves the plan.

Every AI call and every approval is written to an audit log. All teams share one database, but each team only ever sees its own data.

![Overview](docs/screenshots/overview.png)

## Live deployment

| Part | Hosted on | Link |
| --- | --- | --- |
| Frontend | Vercel | [work-os-lite-8crz.vercel.app](https://work-os-lite-8crz.vercel.app) |
| API | Render (Docker, free plan) | [work-os-lite.onrender.com](https://work-os-lite.onrender.com) |
| Health check | Render | [/health](https://work-os-lite.onrender.com/health) (also pings the database) |
| API docs | Render | [/docs](https://work-os-lite.onrender.com/docs) (FastAPI's Swagger UI) |
| Database | Neon (PostgreSQL + pgvector) | not public |

To try it, open the site and click **Open a demo workspace**. You get your own sandbox team with two projects, eight tasks, three policy documents and one AI plan waiting for review.

Some things to try:

- drag a task to another column on the board
- ask "How many days of paid leave do we get?" in Ask docs
- approve the waiting plan in the AI planner and check the board

## What you can do

| Page | What it does |
| --- | --- |
| Overview | Shows what needs attention: plans waiting for review, blocked tasks and why they're blocked, late tasks. Also shows each project's progress by status. |
| Board | Kanban with drag and drop. A task can depend on another task, and its card shows "Waiting on X" until that task is done. Click a card to edit it. |
| Ask docs | Upload PDF, .txt or .md files and ask questions in a chat. Answers name the file they came from. Questions the files don't cover get refused. |
| AI planner | Paste a brief and get a draft plan. Drafts have a dashed border; once approved they turn solid and the tasks show up on the board. |
| Team | Members and roles. Admins can see the AI audit log and open any row to read what the model returned. |

Every visitor who clicks the demo button gets a separate sandbox team, so the demo also shows the team isolation working.

## Stack

| Part | Choice |
| --- | --- |
| Backend | Python 3.11, FastAPI, SQLAlchemy, Pydantic |
| Database | PostgreSQL with pgvector (tasks and embeddings in the same database) |
| AI | Groq, Gemini, OpenAI or Anthropic over plain HTTP, no LangChain |
| Frontend | React with Vite, plain JavaScript, no UI library |
| Tests | pytest, 66 tests, run on both SQLite and Postgres |
| CI | GitHub Actions: tests on both databases, retrieval eval, frontend build |
| Hosting | Neon (database), Render (API), Vercel (frontend), all free plans |

## Architecture

```mermaid
flowchart LR
    UI[React app on Vercel] -->|JWT in header| API[FastAPI on Render]
    API --> AUTH[get_current_user<br/>reads team_id and role from JWT]
    AUTH --> SCOPE[TeamScope<br/>adds WHERE team_id = ? to every query]
    SCOPE --> DB[(Neon Postgres + pgvector)]

    API --> RAG[/ask/]
    RAG -->|embed question| EMB[Embeddings]
    RAG -->|top 4 chunks for this team| DB
    RAG -->|best score below 0.15| REFUSE[Refuse, no AI call]
    RAG -->|excerpts + question| LLM[LLM API]

    API --> PLAN[/planner/plans/]
    PLAN --> LLM
    PLAN -->|Pydantic check, one retry| PENDING[Plan saved as pending]
    PENDING -->|admin approves| TASKS[Real tasks created]

    RAG --> AUDIT[(audit_log)]
    PLAN --> AUDIT
```

## How it works

### Team isolation

Every table has a `team_id` column, and the JWT carries the user's `team_id` and role. Endpoints don't write the team filter themselves. They go through `TeamScope` in `app/deps.py`, which adds `WHERE team_id = ...` to every query and sets `team_id` on every insert. Asking for another team's row returns 404 instead of 403, so you can't even tell the row exists. `tests/test_isolation.py` tries to read, edit, delete and link to another team's rows, and checks that search never returns another team's documents.

### Answering from documents

Uploaded files are split into chunks of about 500 tokens (375 words), with 50 words of overlap so a sentence cut at a boundary still shows up whole in one chunk. Each chunk is embedded and stored in a pgvector column. A question gets embedded the same way and compared against the team's chunks by cosine distance. If the best match scores below `MIN_SIMILARITY`, the app refuses and the AI is never called. Otherwise the top 4 chunks go to the model inside `<excerpt>` tags, and the prompt tells it to treat excerpt text as data, not instructions.

### AI planner

The model has to return JSON that matches `TaskPlan` in `app/schemas.py`. A task can only depend on a task listed before it, which also means there can't be cycles. If the reply fails validation, the exact error is sent back to the model for one retry. If that fails too, the request returns 502 and the failure is logged.

Approving a plan is one conditional `UPDATE ... WHERE status = 'pending'` plus the new tasks, in a single transaction. If two approvals come in at the same time, only one gets through and the other gets 409, so tasks are never created twice. There's a test for this that sends two approvals at once on Postgres.

### One code path for four AI providers

Groq, Gemini and OpenAI all accept the OpenAI chat format, so `app/services/llm.py` sends the same request to whichever base URL is set. Anthropic has its own small function. Switching providers means changing two environment variables.

### Free hosting

Free plans sleep and have usage limits, so a few things are there because of that:

- `/ping` answers without touching the database. Render's health check hits `/ping`, so Neon can still sleep between visits and the free compute hours last the whole month.
- The database pool checks each connection before using it and recycles connections every 5 minutes, because Neon drops idle connections when it suspends.
- Logins, demo creation, questions and plans are rate limited, so one visitor can't use up the AI key's daily quota.
- Unexpected errors return JSON with CORS headers. Without that, the browser shows a CORS error and hides the real one.
- If the server has no AI key, everything except the two AI features still works, and the app tells you why they're off.

## Run it locally

You need Docker and Node 20.

```bash
cp .env.example .env          # add LLM_API_KEY (a free Groq key works)
docker compose up --build     # API on http://localhost:8000, docs at /docs

cd frontend
cp .env.example .env
npm install
npm run dev                   # app on http://localhost:5173
```

The backend also runs on SQLite without Docker:

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Hosting it yourself for free

[docs/HOSTING.md](docs/HOSTING.md) goes through it step by step, with every field to fill in and a table of common problems.

## Tests

```bash
cd backend
pytest                                    # 65 tests on SQLite (1 needs Postgres and is skipped)
TEST_DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/workos_test pytest   # all 66 tests on Postgres
```

The tests swap the AI for a fake that returns queued replies, so they run offline and cost nothing. They cover:

- login, wrong passwords, admin-only actions
- task dependencies, cycle checks, the blocked list
- chunk overlap, refusing unrelated questions, prompt-injection wrapping
- the planner retry path, approval and rejection
- team isolation
- each demo visitor getting a separate team
- rate limits
- the request format for each AI provider
- provider errors (rate limit, bad key, no network)
- CORS headers on server errors
- `/ping` never touching the database

## Evaluation

`backend/eval/questions.json` has 15 questions about the 3 policy documents in `backend/app/demo_docs/`. The documents answer 12 of them. The other 3 (wifi password, cafeteria vendor, stock price) aren't in the documents at all.

```bash
python eval/run_eval.py --mode retrieval   # no API key needed
python eval/run_eval.py --mode full        # calls the real AI
```

Retrieval mode checks that the right document ranks first and that off-topic questions get refused. Full mode also checks that the answer has the expected fact and names the right file.

## Results

Measured on 27 Oct 2026 with the default offline `hash` embeddings and `MIN_SIMILARITY=0.15`:

| Eval | Result |
| --- | --- |
| Retrieval, answerable questions | 11/12 right document ranked first |
| Retrieval, off-topic questions | 3/3 refused |
| Overall | 14/15 |
| Full answer eval with the AI | Not run yet (needs an API key and calls the real model) |

The first run also scored 14/15, but missed a different question. "On which days do production deploys happen?" scored 0.137 because the hash embedding saw "deploys" and "deploy" as different words. Adding basic plural handling fixed that one.

The question that still fails is "Within how many days must the security awareness training be completed?" (0.137). The document says "complete" and the question says "completed", and hash embeddings can't match the two. The proper fix is `EMBEDDING_PROVIDER=openai`. I didn't lower the threshold to make it pass, because tuning on the same 15 questions would just inflate the score on this set.

CI fails the build if the retrieval score drops below 13/15.

## Design decisions

- **One shared database with `team_id`, not a schema per team.** Easy to run and enough for a small SaaS. The risk is someone forgetting the filter, so the filter lives in one place (`TeamScope`) and isolation has its own test file.
- **pgvector instead of a separate vector database.** Tasks, documents and embeddings are all in one Postgres. That's one backup and one connection, and chunks get filtered by `team_id` in the same query that ranks them.
- **No LangChain.** Two plain HTTP calls are easier to read, debug and explain than a framework.
- **Refuse before calling the AI.** If search finds nothing close, the question never reaches the model. It saves a call and the model can't make up an answer.
- **Plans need an admin.** Plans stay pending until an admin approves them. Members can create plans but can't approve them. Drafts are drawn dashed and approved work is solid.
- **Model output is checked like user input.** The planner's JSON goes through the same Pydantic validation as any request body, with one retry that includes the exact error.
- **Offline `hash` embeddings by default.** The project runs and passes its tests without any paid API. The downside is weaker matching, which shows up in the results above.

## Limitations

- Hash embeddings miss synonyms and word forms ("leave" vs "vacation", "complete" vs "completed").
- Tables in PDFs lose their structure when the text is extracted. Scanned PDFs have no text to extract.
- Rate limits are stored in memory, so they reset on restart and would need Redis with more than one server.
- Tables are created at startup with `create_all`. A bigger deployment would use migrations (Alembic).
- Changing the embedding provider changes the vector size, so existing documents have to be uploaded again.
- Drag and drop on the board needs a mouse. On a phone, open a card and change its status there.

## Checking the AI-written code

I used an AI coding assistant for parts of this project, so I went back through the code afterwards. For each bug I wrote a failing test first, then fixed it. What I found:

- **Double approval created duplicate tasks.** The approve endpoint checked the plan's status in Python and then created the tasks. Two approvals at the same moment both passed the check, so a plan with 2 tasks ended up creating 4. A test that sends two approvals at once on Postgres caught it. Now it's a single `UPDATE ... WHERE status = 'pending'`, so only one approval goes through and the other gets 409.
- **Audit rows were being edited.** Approving a plan changed the status on the earlier "plan generated" row. An audit log should only ever grow, so a review now adds its own row.
- **Login rate limit could be bypassed.** The limit was keyed only on the `X-Forwarded-For` header, which the client controls. A test that sent a different fake address with each wrong password never got blocked. Login is now limited per account too.
- **Default JWT secret.** If `JWT_SECRET` was left at the default, the app only logged a warning. On Postgres it now refuses to start.

The regression tests for all of these are in `backend/tests/test_audit_regressions.py`.

## Project layout

```
backend/
  app/
    main.py            app setup, /ping, /health, /meta, error handling
    config.py          settings from environment variables, AI providers
    deps.py            current user, admin check, TeamScope
    ratelimit.py       in-memory rate limits
    models.py          tables
    schemas.py         request and response shapes, TaskPlan
    routers/           auth (and demo), team, projects, tasks, documents, planner, audit
    services/          llm, embeddings, chunking, ingest, rag, planner, demo, audit
    demo_docs/         the 3 sample policy documents
  tests/               66 pytest tests
  eval/                15 questions and run_eval.py
frontend/src/
  api.js               every backend call
  ui.jsx               icons, toasts, drawer, avatars, date helpers
  pages/               Login, Overview, Board, Docs, Planner, Team
docs/HOSTING.md        free hosting guide
render.yaml            Render Blueprint for the API
```

## Screenshots

| Board | Ask docs |
| --- | --- |
| ![Board](docs/screenshots/board.png) | ![Docs](docs/screenshots/docs.png) |

| AI planner | Audit log |
| --- | --- |
| ![Planner](docs/screenshots/planner.png) | ![Team](docs/screenshots/team.png) |

| Dark theme | Phone |
| --- | --- |
| ![Dark board](docs/screenshots/board-dark.png) | ![Mobile](docs/screenshots/mobile.png) |
