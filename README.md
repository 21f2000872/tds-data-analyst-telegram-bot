# Data Analyst Telegram Bot

A deployable FastAPI bot that answers Telegram data-analysis questions with exactly
one JSON object:

```json
{"answer":"<requested answer shape>","log_url":"https://public-host/runs/id.jsonl"}
```

The application—not the model—adds `log_url` and serializes the final reply. Public
run logs and private multi-turn state are stored in separate Google Cloud Storage
buckets.

Assigned Telegram bot: **[@marutendradatabot](https://t.me/marutendradatabot)**

## Milestone 1: create the Telegram bot

1. Open Telegram and start a chat with the verified **@BotFather** account.
2. Send `/newbot`.
3. Choose a display name, such as `Marutendra Data Analyst`.
4. Choose a unique username ending in `bot`, such as
   `marutendra_data_analyst_bot`.
5. Copy the token into a password manager. Do not paste it into chat, source code,
   screenshots, or GitHub.
6. You will later store the token in Google Secret Manager as
   `TELEGRAM_BOT_TOKEN`.

This milestone creates only the bot identity. It does not make the bot work yet;
the webhook will connect it to this application after deployment.

Project status: this milestone is complete for `@marutendradatabot`.

## Local setup

Python 3.11 or 3.12 is recommended.

If `python --version` says the command is not recognized, install Python 3.12 from
python.org, enable **Add Python to PATH** in the installer, close the terminal, and
open a new one before continuing.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
pytest
```

Copy `.env.example` to `.env` and fill in secrets only when you want to run the
real integration. `.env` is ignored by Git.

Run locally:

```powershell
uvicorn app.main:app --reload --port 8080
```

Check `http://localhost:8080/healthz`. A `503` response lists missing settings; a
`200` response means the runtime configuration is present.

## Architecture and assignment guarantees

- `app/main.py`: validates Telegram's webhook secret, deduplicates updates,
  preserves private chat history, publishes the log, and sends one reply.
- `app/contracts.py`: enforces the exact reply structure.
- `app/agent.py`: uses the OpenAI Responses API, web search, and dataset tools.
- `app/data_tools.py`: validates public URLs, downloads bounded datasets, supports
  CSV/TSV/JSON/JSONL/Excel/HTML/Parquet, and runs guarded pandas analysis.
- `app/storage.py`: keeps public logs and private conversation state separate.
- `tests/`: verifies exact JSON, webhook authentication, deduplication, logs,
  dataset analysis, and multi-turn state.

The analysis runner has practical guardrails but is not a hardened hostile-code
sandbox. Keep the bot private during grading, set Cloud Run to one instance, and
monitor API usage.

## Create a public GitHub repository

Create an empty **public** repository, for example
`tds-data-analyst-telegram-bot`. Do not add another README or `.gitignore`.

From this folder:

```powershell
git init
git add .
git commit -m "Build data analyst Telegram bot"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/tds-data-analyst-telegram-bot.git
git push -u origin main
```

Before pushing, run:

```powershell
git status
git grep -n -I -E "sk-[A-Za-z0-9_-]{20,}|[0-9]{8,}:[A-Za-z0-9_-]{20,}"
```

The second command should print nothing. Never commit `.env`.

## Google Cloud deployment

Choose one project and set these names. Bucket names must be globally unique:

```powershell
$PROJECT_ID="YOUR_PROJECT_ID"
$REGION="asia-south1"
$LOG_BUCKET="tds-agent-logs-YOUR_ROLL-RANDOM"
$STATE_BUCKET="tds-agent-state-YOUR_ROLL-RANDOM"
$SERVICE_ACCOUNT="telegram-analyst"
gcloud config set project $PROJECT_ID
```

Enable required services:

```powershell
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com storage.googleapis.com
```

Create buckets. Only the log bucket becomes public:

```powershell
gcloud storage buckets create "gs://$LOG_BUCKET" --location=$REGION --uniform-bucket-level-access
gcloud storage buckets create "gs://$STATE_BUCKET" --location=$REGION --uniform-bucket-level-access
gcloud storage buckets add-iam-policy-binding "gs://$LOG_BUCKET" --member=allUsers --role=roles/storage.objectViewer
```

If public access prevention is enforced by your organization, use a project where
you are permitted to publish the assignment logs.

Create the runtime identity:

```powershell
gcloud iam service-accounts create $SERVICE_ACCOUNT --display-name="Telegram analyst runtime"
$SA_EMAIL="$SERVICE_ACCOUNT@$PROJECT_ID.iam.gserviceaccount.com"
gcloud storage buckets add-iam-policy-binding "gs://$LOG_BUCKET" --member="serviceAccount:$SA_EMAIL" --role=roles/storage.objectCreator
gcloud storage buckets add-iam-policy-binding "gs://$STATE_BUCKET" --member="serviceAccount:$SA_EMAIL" --role=roles/storage.objectAdmin
```

Create secrets without placing values in shell history. Run each command and type
or paste the value when prompted, then press `Ctrl+Z` followed by Enter on Windows:

```powershell
gcloud secrets create TELEGRAM_BOT_TOKEN --replication-policy=automatic --data-file=-
gcloud secrets create TELEGRAM_WEBHOOK_SECRET --replication-policy=automatic --data-file=-
gcloud secrets create OPENAI_API_KEY --replication-policy=automatic --data-file=-
```

Allow the runtime identity to read them:

```powershell
gcloud secrets add-iam-policy-binding TELEGRAM_BOT_TOKEN --member="serviceAccount:$SA_EMAIL" --role=roles/secretmanager.secretAccessor
gcloud secrets add-iam-policy-binding TELEGRAM_WEBHOOK_SECRET --member="serviceAccount:$SA_EMAIL" --role=roles/secretmanager.secretAccessor
gcloud secrets add-iam-policy-binding OPENAI_API_KEY --member="serviceAccount:$SA_EMAIL" --role=roles/secretmanager.secretAccessor
```

Deploy from the repository root:

```powershell
gcloud run deploy tds-data-analyst-bot --source . --region=$REGION --allow-unauthenticated --service-account=$SA_EMAIL --max-instances=1 --concurrency=1 --timeout=300 --set-env-vars="OPENAI_MODEL=gpt-5.6-terra,LOG_BUCKET=$LOG_BUCKET,STATE_BUCKET=$STATE_BUCKET,MAX_HISTORY_MESSAGES=12" --set-secrets="TELEGRAM_BOT_TOKEN=TELEGRAM_BOT_TOKEN:latest,TELEGRAM_WEBHOOK_SECRET=TELEGRAM_WEBHOOK_SECRET:latest,OPENAI_API_KEY=OPENAI_API_KEY:latest"
```

Copy the returned Cloud Run HTTPS URL into `$SERVICE_URL`, update the service, and
set the webhook:

```powershell
$SERVICE_URL="https://YOUR-SERVICE-URL"
gcloud run services update tds-data-analyst-bot --region=$REGION --set-env-vars="PUBLIC_BASE_URL=$SERVICE_URL"
$TOKEN=(gcloud secrets versions access latest --secret=TELEGRAM_BOT_TOKEN)
$WEBHOOK_SECRET=(gcloud secrets versions access latest --secret=TELEGRAM_WEBHOOK_SECRET)
Invoke-RestMethod -Method Post -Uri "https://api.telegram.org/bot$TOKEN/setWebhook" -ContentType "application/json" -Body (@{url="$SERVICE_URL/telegram/webhook"; secret_token=$WEBHOOK_SECRET; drop_pending_updates=$true} | ConvertTo-Json)
Remove-Variable TOKEN,WEBHOOK_SECRET
```

Verify:

```powershell
Invoke-RestMethod "$SERVICE_URL/healthz"
```

Then send the bot:

```text
What is 17 multiplied by 23?
Return the answer as {"value": <number>}.
```

Its Telegram message must be one JSON object with `answer` and a reachable
`log_url`.

## Submission checklist

- GitHub repository is public and contains no secrets.
- Telegram reply contains exactly `answer` and `log_url`.
- `log_url` opens without authentication and contains JSONL events.
- The state bucket is not public.
- Multi-turn follow-ups retain recent context.
- Public dataset URLs are downloaded without changing their source.
- Tests pass before every deployment.
- Cloud Run health check is ready and the Telegram webhook is set.

## Current machine prerequisites

For deployment, Docker Desktop must be open with its Linux engine running, and the
Google Cloud CLI (`gcloud`) must be installed and initialized. Neither is needed
for the local unit tests. GitHub Actions repeats the test suite on every push to
`main` and on every pull request.
