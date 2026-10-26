# Free hosting guide

This puts Work OS Lite online for free, with a link you can put on a resume. It takes about 40 minutes the first time.

| Part | Service | Why this one |
| --- | --- | --- |
| Code and CI | GitHub | Free. Every push runs the tests. |
| Database | Neon | Free Postgres with pgvector that does not expire. |
| API | Render | Free Docker hosting, deploys on every push. |
| Frontend | Vercel | Free static hosting, deploys on every push. |
| AI | Groq | Free API key with a daily request allowance. Gemini also works. |

Limits checked on 27 Oct 2026. Free plans change, so check each service's pricing page before you rely on a number.

## What "free" means here

**Render** puts a free web service to sleep after 15 minutes with no traffic. The next request wakes it, which takes about a minute. Each workspace gets 750 free instance hours per month. Render's own free Postgres is deleted 30 days after you create it, so this guide does not use it. ([Render](https://render.com/articles/platforms-with-a-real-free-tier-for-developers-in-2026))

**Neon** gives 100 compute hours per project per month and 1 GB of storage per project. The database suspends after 5 minutes without queries and wakes on the next one. pgvector is included on the free plan. ([limits](https://neon.com/faqs/free-plan-limits-and-quotas), [pgvector](https://neon.com/faqs/best-postgres-services-retrieval-augmented-generation))

**Groq** needs no credit card. On the free tier, `llama-3.3-70b-versatile` allows 30 requests per minute, 12,000 tokens per minute and 1,000 requests per day. ([eesel.ai, June 2026](https://eesel.ai/blog/groq-pricing)) The app adds its own limits on top (20 questions and 6 plans per user per minute), so one visitor cannot use up the whole day.

**The app itself** stores everything in the database, including uploaded documents. Render's disk is not used, so nothing is lost when the service sleeps or redeploys.

## Before you start

You need:

- A GitHub account
- Git installed on your laptop
- The project folder (`work-os-lite`)

Sign up for Neon, Render and Vercel with "Continue with GitHub". It saves time later because they can read your repo directly.

## Step 1. Put the code on GitHub

1. On GitHub, click **New repository**. Name it `work-os-lite`, set it to **Public**, and do not add a README (the project has one).
2. In a terminal, inside the project folder:

   ```bash
   git init
   git add .
   git commit -m "Work OS Lite"
   git branch -M main
   git remote add origin https://github.com/<your-username>/work-os-lite.git
   git push -u origin main
   ```

3. Run `git status`. It must not list `.env`. If it does, your keys are about to go public: remove it with `git rm --cached .env` and commit again.
4. Open the **Actions** tab on GitHub. The CI run should finish green in about 3 minutes. It runs 55 tests on SQLite, the same 55 on Postgres with pgvector, the retrieval eval, and the frontend build.

## Step 2. Create the database on Neon

1. Go to [neon.com](https://neon.com) and sign up.
2. Create a project:
   - Name: `work-os-lite`
   - Postgres version: the default
   - Region: the one closest to your Render region. For India, pick **Singapore** on both.
3. On the project dashboard, click **Connect**.
4. Turn **Connection pooling** off, so you get the direct connection string. The app already keeps its own small pool of connections.
5. Copy the string. It looks like this:

   ```
   postgresql://neondb_owner:abc123@ep-cool-name-123456.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require
   ```

   Keep it somewhere private. It contains the database password.

You do not need to create tables or enable pgvector. On its first start, the API runs `CREATE EXTENSION IF NOT EXISTS vector` and creates every table.

## Step 3. Get a free AI key from Groq

1. Go to [console.groq.com/keys](https://console.groq.com/keys) and sign in.
2. Click **Create API Key**, name it `work-os-lite`, and copy it. It starts with `gsk_` and is shown only once.

**Using Gemini instead:** create a key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey). In Step 4 set `LLM_PROVIDER=gemini` and put the Gemini key in `LLM_API_KEY`. The app calls Gemini through Google's OpenAI-compatible endpoint (`https://generativelanguage.googleapis.com/v1beta/openai/`). The default model is `gemini-3.8-flash`, taken from [Google's docs](https://ai.google.dev/gemini-api/docs/openai). If Google renames it, set `LLM_MODEL` to a model listed in AI Studio.

**Skipping AI for now:** leave `LLM_API_KEY` empty. Projects, tasks, the board, uploads and the demo all still work. The app shows a notice that AI answers and plans are off.

## Step 4. Deploy the API on Render

### Option A: Blueprint (fastest)

The repo has a `render.yaml` that sets up the service for you.

1. In Render, click **New** and choose **Blueprint**.
2. Connect your `work-os-lite` repo. Render reads `render.yaml` and shows one service, `work-os-lite-api`, on the **Free** plan.
3. Render asks for the values marked as secret:

   | Key | Value |
   | --- | --- |
   | `DATABASE_URL` | the Neon string from Step 2 |
   | `LLM_API_KEY` | the Groq key from Step 3 |
   | `CORS_ORIGINS` | put `http://localhost:5173` for now. You change it in Step 6. |

   `JWT_SECRET` is generated for you. `LLM_PROVIDER=groq`, `EMBEDDING_PROVIDER=hash` and `DEMO_MODE=true` are already set.

4. Click **Apply**. The first build takes 3 to 5 minutes.

### Option B: by hand

1. **New**, then **Web Service**, then pick the repo.
2. Settings:

   | Setting | Value |
   | --- | --- |
   | Language | Docker |
   | Branch | main |
   | Dockerfile path | `./backend/Dockerfile` |
   | Docker build context | `./backend` |
   | Instance type | Free |
   | Health check path | `/ping` |

3. Environment variables:

   | Key | Value |
   | --- | --- |
   | `DATABASE_URL` | the Neon string |
   | `JWT_SECRET` | run `python -c "import secrets; print(secrets.token_hex(32))"` and paste the output |
   | `LLM_PROVIDER` | `groq` |
   | `LLM_API_KEY` | the Groq key |
   | `EMBEDDING_PROVIDER` | `hash` |
   | `DEMO_MODE` | `true` |
   | `CORS_ORIGINS` | `http://localhost:5173` for now |

4. Click **Deploy Web Service**.

### Check it

Your API URL looks like `https://work-os-lite-api.onrender.com`. Open these in a browser:

| URL | You should see |
| --- | --- |
| `/ping` | `{"status":"ok"}` |
| `/health` | `{"status":"ok","database":"ok"}`. This one proves Neon is connected. |
| `/meta` | `"llm_configured": true` if the Groq key is set |
| `/docs` | the interactive API docs |

If `/health` says `"database":"unreachable"`, the `DATABASE_URL` is wrong. See Troubleshooting.

Why the health check uses `/ping` and not `/health`: Render checks the health path every few seconds. `/health` runs a database query, which would keep Neon awake all month and spend the 100 free compute hours. `/ping` answers without touching the database.

## Step 5. Deploy the frontend on Vercel

1. In Vercel, click **Add New**, then **Project**, and import `work-os-lite`.
2. Set **Root Directory** to `frontend`. Vercel detects Vite. Leave the build command (`npm run build`) and output directory (`dist`) as they are.
3. Under **Environment Variables**, add:

   | Key | Value |
   | --- | --- |
   | `VITE_API_URL` | your Render URL, for example `https://work-os-lite-api.onrender.com`, with no slash at the end |

4. Click **Deploy**. It takes about a minute. Copy the production URL, for example `https://work-os-lite.vercel.app`.

`VITE_API_URL` is baked into the frontend when it builds. If you change it later, redeploy the frontend for the change to take effect.

## Step 6. Let the frontend talk to the API

Browsers block calls from one site to another unless the API allows it. That is the CORS setting.

1. In Render, open the service, then **Environment**.
2. Set `CORS_ORIGINS` to your Vercel URL, exactly as the browser shows it, with no slash at the end:

   ```
   https://work-os-lite.vercel.app
   ```

   To allow both the live site and local development, separate them with a comma:

   ```
   https://work-os-lite.vercel.app,http://localhost:5173
   ```

3. Optional: Vercel gives every pull request its own preview URL. To allow all of them, add `CORS_ORIGIN_REGEX` with a value such as `https://work-os-lite-.*\.vercel\.app`.
4. Save. Render redeploys on its own.

## Step 7. Test the live site

Open your Vercel URL and go through this list:

- [ ] **Open a demo workspace** loads the overview with 2 projects and an AI plan waiting for review
- [ ] On the board, dragging **Build auth service** to Done removes "Waiting on" from the cards after it
- [ ] Ask docs: "How many days of paid leave do we get?" answers 18 days and names `leave_policy.md`
- [ ] Ask docs: "What is the office wifi password?" says it is not in your documents
- [ ] AI planner: **Use an example brief**, then **Draft a plan**, returns dashed draft tasks
- [ ] **Approve** turns the plan solid and the tasks appear on the board
- [ ] Team: the audit log shows each question and plan; clicking a row shows the model output
- [ ] Log out, then **Create a team** with your own email works
- [ ] The site works on your phone

The first visit after a quiet period can take about a minute while Render wakes up. If a request fails during that wake-up, the app says the server is waking up and asks the visitor to try again in 30 seconds.

## Step 8 (optional). Keep the API awake

If a recruiter opens your link while the API sleeps, they wait about a minute. A free pinger fixes that.

1. Sign up at [cron-job.org](https://cron-job.org).
2. Create a cron job:
   - URL: `https://<your-render-url>/ping`
   - Schedule: every 10 minutes
3. Save.

One service running all month uses at most 744 hours (31 days of 24 hours), which fits inside Render's 750. Point the pinger at `/ping`, not `/health`, so the database still sleeps between real visits.

## Updating the site

Commit and push to `main`. GitHub runs the tests, Render rebuilds the API, and Vercel rebuilds the frontend. Nothing else to do.

## Troubleshooting

| What you see | Cause | Fix |
| --- | --- | --- |
| Browser console: "blocked by CORS policy" | `CORS_ORIGINS` does not match the site URL | Copy the URL from the address bar, remove any trailing `/`, paste it into `CORS_ORIGINS` on Render. Check `http` vs `https`. |
| "Cannot reach the server" on the login page | Render is waking up, or `VITE_API_URL` is wrong | Wait a minute and retry. If it keeps failing, check `VITE_API_URL` in Vercel and redeploy. |
| `/health` shows `"database":"unreachable"` | Wrong `DATABASE_URL`, or Neon compute is suspended for going over quota | Copy the connection string from Neon again. Check the Neon dashboard for a quota warning. |
| Render build fails with "Dockerfile not found" | Dockerfile path is relative to the wrong folder | Dockerfile path `./backend/Dockerfile`, build context `./backend`. |
| "AI is not set up on this server" | `LLM_API_KEY` is empty | Add the key in Render. The service restarts by itself. |
| "groq rate limit reached" | Groq's per-minute or per-day limit | Wait a minute. If it is the daily limit, it resets the next day. |
| "groq rejected the API key" | Key copied wrong or deleted | Create a new key in the Groq console and update `LLM_API_KEY`. |
| "Too many requests. Try again in N seconds." | The app's own limit (10 logins per minute per IP, 5 demo workspaces per hour per IP) | Wait for the time shown. |
| Everyone gets logged out after a deploy | `JWT_SECRET` changed | Set it once and leave it. With the Blueprint, Render keeps the generated value. |
| Uploaded PDF says "no readable text" | It is a scanned image, not text | Use a PDF with selectable text, or a .txt or .md file. |
| You switched `EMBEDDING_PROVIDER` and search broke | Vectors from the old model have a different size | Start with a fresh Neon branch or database and upload the documents again. |

## Free plan safety

- Never commit `.env`. Every secret lives in Render's environment settings.
- `DEMO_MODE=true` lets anyone create a sandbox workspace. Each one is a separate team and cannot see the others. Set it to `false` if you only want real sign-ups.
- Neon's dashboard shows compute hours used this month. Check it once a week for the first month.

## For the resume

Once the checklist passes, add both links:

```
Work OS Lite | live: https://<your-vercel-url> | code: https://github.com/<you>/work-os-lite
```

The live link opens a working demo with no sign-up, which is the fastest way for a reviewer to see the project.
