# Work OS Lite

[![CI](https://github.com/Mahendr99ar/work-os-lite/actions/workflows/ci.yml/badge.svg)](https://github.com/Mahendr99ar/work-os-lite/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11-3776ab)
![FastAPI](https://img.shields.io/badge/FastAPI-backend-009688)
![React](https://img.shields.io/badge/react-18-61dafb)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-pgvector-336791)

**Live:** [work-os-lite-8crz.vercel.app](https://work-os-lite-8crz.vercel.app) (click "Open a demo workspace", no sign-up)

**API:** [health](https://work-os-lite.onrender.com/health) | [interactive docs](https://work-os-lite.onrender.com/docs)

**Author:** [Mahendra Meena](https://github.com/Mahendr99ar)

> The API runs on Render's free plan and sleeps after 15 minutes without traffic. If the site says it cannot reach the server, give it about a minute and try again.

A team workspace for projects and tasks, with two AI features that never act on their own:

1. **Ask your documents.** Upload team PDFs or notes and ask questions. Answers come only from those documents and name the source file. If the documents do not cover the question, the app says so instead of guessing.
2. **AI task planner.** Paste a messy project brief. The AI drafts a task plan with dependencies. The draft stays off the board until an admin approves it.

Every AI call and every approval goes into an audit log. Each team's data is kept apart in one shared database.

![Overview](docs/screenshots/overview.png)

## Live deployment

| Part | Where | Link |
| --- | --- | --- |
| Frontend | Vercel | [work-os-lite-8crz.vercel.app](https://work-os-lite-8crz.vercel.app) |
| API | Render (Docker, free plan) | [work-os-lite.onrender.com](https://work-os-lite.onrender.com) |
| API health check | Render | [/health](https://work-os-lite.onrender.com/health) (also checks the database) |
| API docs | Render | [/docs](https://work-os-lite.onrender.com/docs) (Swagger UI from FastAPI) |
| Database | Neon (PostgreSQL + pgvector) | Private |

The fastest way to try it: open the live site and click **Open a demo workspace**. You get a private sandbox team with two projects, eight tasks, three policy documents and one AI plan waiting for review. Try dragging a task on the board, asking "How many days of paid leave do we get?" in Ask docs, and approving the plan in the AI planner.

## What you can do

| Page | What it does |
| --- | --- |
| Overview | Lists what needs attention: AI plans waiting for review, blocked tasks with the reason, late tasks. Shows each project's progress by status. |
| Board | Kanban with drag and drop. A task can wait on another task; its card says "Waiting on X" until that task is done. Click a card to edit it. |
| Ask docs | Upload PDF, .txt or .md files. Ask questions in a chat. Answers name their source file; questions the documents do not cover are refused. |
| AI planner | Paste a brief and get a draft plan. Drafts are drawn dashed; approved plans turn solid and their tasks land on the board. |
| Team | Members and roles. Admins see the AI audit log and can open any row to read what the model returned. |

The demo button creates a private sandbox team with two projects, eight tasks, three policy documents and one plan waiting for review. Every visitor gets their own sandbox, which also shows the team isolation working.

## Stack

| Part | Choice |
| --- | --- |
| Backend | Python 3.11, FastAPI, SQLAlchemy, Pydantic |
| Database | PostgreSQL with pgvector (tasks and embeddings in one database) |
| AI | Groq, Gemini, OpenAI or Anthropic over plain HTTP, no LangChain |
| Frontend | React with Vite, plain JavaScript, no UI library |
| Tests | pytest, 66 tests, run on both SQLite and Postgres |
| CI | GitHub Actions: tests twice, retrieval eval, frontend build |
| Hosting | Neon (database), Render (API), Vercel (frontend), all on free plans |

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

## How the important parts work

**Keeping teams apart.** Every table has a `team_id` column. The JWT carries the user's `team_id` and role. Endpoints never write the team filter themselves; they read data through `TeamScope` in `app/deps.py`, which adds `WHERE team_id = ...` to every query and stamps `team_id` on every insert. A row from another team returns 404, not 403, so a caller cannot even learn that it exists. `tests/test_isolation.py` tries to read, edit, delete and link to another team's rows, and checks that search never returns another team's documents.

**Answering from documents.** Uploads are split into chunks of about 500 tokens (375 words) with a 50-word overlap, so a sentence cut at a boundary still appears whole in one chunk. Each chunk is embedded and stored in a pgvector column. A question is embedded the same way and compared with the team's chunks by cosine distance. If the best match scores below `MIN_SIMILARITY`, the app refuses without calling the AI. Otherwise the top 4 chunks go to the model inside `<excerpt>` tags, with an instruction that excerpt text is data and not instructions.

**AI planner.** The model must return JSON matching `TaskPlan` in `app/schemas.py`. A task may only depend on a task listed before it, which also rules out cycles. If the reply fails validation, the exact error goes back to the model for one retry. If the second reply also fails, the request returns 502 and the failure is logged. Approval is one conditional `UPDATE ... WHERE status = 'pending'` plus the new tasks, in a single transaction. If two approvals arrive together, the database lets exactly one through and the other gets 409, so tasks are never created twice (tested with two concurrent requests on Postgres).

**One code path for four AI providers.** Groq, Gemini and OpenAI all accept the OpenAI chat format, so `app/services/llm.py` sends one request shape to whichever base URL is configured. Anthropic gets its own small function. Switching provider is two environment variables.

**Built for free hosting.** Free hosts sleep and have quotas, so the app plans for it:

- `/ping` answers without touching the database. Render's health check uses it, so Neon's database can still sleep between visits and the free compute hours last the month.
- The database pool checks connections before use and recycles them every 5 minutes, because Neon drops idle connections when it suspends.
- Logins, demo creation, questions and plans are rate limited, so one visitor cannot spend the AI key's daily allowance.
- Unexpected errors return JSON with CORS headers, so the browser shows the real error rather than a misleading CORS message.
- If the server has no AI key, everything except the two AI features still works, and the app says why those are off.

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

Without Docker, the backend also runs on SQLite:

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Put it online for free

Step by step, with every field to fill in and a troubleshooting table: [docs/HOSTING.md](docs/HOSTING.md).

## Tests

```bash
cd backend
pytest                                    # 65 tests on SQLite (1 needs Postgres and is skipped)
TEST_DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/workos_test pytest   # all 66 tests on Postgres
```

Tests replace the AI with a fake that returns queued replies, so they run offline and cost nothing. They cover:

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

`backend/eval/questions.json` holds 15 questions about the 3 policy documents in `backend/app/demo_docs/`: 12 that the documents answer, and 3 they do not (wifi password, cafeteria vendor, stock price).

```bash
python eval/run_eval.py --mode retrieval   # no API key needed
python eval/run_eval.py --mode full        # calls the real AI
```

Retrieval mode checks that the right document ranks first and that off-topic questions are refused. Full mode also checks that the answer contains the expected fact and names the right file.

## Results

Measured on 27 Oct 2026 with the default offline `hash` embeddings and `MIN_SIMILARITY=0.15`:

| Eval | Result |
| --- | --- |
| Retrieval, answerable questions | 11/12 right document ranked first |
| Retrieval, off-topic questions | 3/3 refused |
| Overall | 14/15 |
| Full answer eval with the AI | Not run yet; it needs a live API key and calls the real model |

The first run also scored 14/15, but on a different question. "On which days do production deploys happen?" scored 0.137, because the hash embedding treated "deploys" and "deploy" as different words. Adding basic plural handling fixed it. The question that still fails is "Within how many days must the security awareness training be completed?" (0.137): the document says "complete", the question says "completed", and the hash embedding cannot tell they are the same word. Switching to `EMBEDDING_PROVIDER=openai` is the real fix. The threshold was not lowered to make it pass, because tuning on the same 15 questions would only flatter the score on this set.

CI fails the build if the retrieval score drops below 13/15.

## Design decisions

- **One shared database with `team_id`, not a schema per team.** Simple to run and enough for a small SaaS. The risk is a forgotten filter, which is why the filter lives in one place (`TeamScope`) and why isolation has its own test file.
- **pgvector instead of a separate vector database.** Tasks, documents and embeddings sit in one Postgres: one backup, one connection, and chunks are filtered by `team_id` in the same query that ranks them.
- **No LangChain.** Two plain HTTP calls are easier to read, debug and explain than a framework.
- **Refuse before calling the AI.** If search finds nothing close, the model never sees the question. That costs nothing and removes the chance of a made-up answer.
- **The AI proposes, a person decides.** Plans stay pending until an admin approves. Members can draft plans but cannot approve them. The interface draws drafts dashed and approved work solid, so the difference is visible at a glance.
- **Validate model output like user input.** The planner's JSON goes through the same Pydantic checks as any request body, with one retry that includes the exact error.
- **Offline `hash` embeddings by default.** The project runs and passes its tests with no paid API. The trade-off is weaker matching, shown in the results above.

## Limitations

- Hash embeddings miss synonyms and word forms ("leave" vs "vacation", "complete" vs "completed").
- Tables in PDFs lose their structure when text is extracted. Scanned PDFs have no text to extract.
- Rate limits are kept in memory, so they reset when the server restarts and would need Redis with more than one server.
- Tables are created at startup with `create_all`; a larger deployment would use migrations (Alembic).
- Changing the embedding provider changes the vector size, so existing documents must be uploaded again.
- Drag and drop on the board needs a mouse. On phones, open a card and change its status there.

## Checking the AI-written code

Parts of this code were written with an AI coding assistant, so the code was audited afterwards instead of being trusted as written. The audit reproduced each suspected bug with a failing test before fixing it. The main finds:

- **Duplicate tasks on double approval.** Approval checked the plan's status in Python and then created the tasks. Two approvals arriving at the same moment both passed the check, so a 2-task plan created 4 tasks. A test that sends two approvals at once on Postgres showed it. The fix is a single `UPDATE ... WHERE status = 'pending'`, so the database lets exactly one approval through and the other gets 409.
- **Audit rows being edited.** Approving a plan changed the status of the earlier "plan generated" audit row. An audit log should only grow, so reviews now add their own row.
- **Login rate limit bypass.** The limit was keyed only by the `X-Forwarded-For` header, which a client can fake. A test that sent a different fake address with each wrong password never got blocked. Login is now also limited per account.
- **Default JWT secret.** The app only logged a warning when `JWT_SECRET` was left at its default. It now refuses to start on Postgres with the default value.

All fixes have regression tests in `backend/tests/test_audit_regressions.py`.

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
