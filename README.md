# UAP Calc Agent Vector

FastAPI + Next.js workspace for an NYC UAP / 485-x development assistant.

## Prerequisites

- Python 3.x
- Node.js 20.9.0 or newer
- npm
- OpenAI and Pinecone API keys

## Environment Setup

Copy the example environment file and fill in the required keys:

```bash
cp .env.example .env
```

The most important variables are `OPENAI_API_KEY`, `PINECONE_API_KEY`, and `NEXT_PUBLIC_API_URL`.

## Install Dependencies

Backend:

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r backend/requirements.txt
```

Frontend:

```bash
cd web
npm install
```

## Run Locally

From the repo root:

```bash
./scripts/run-local.sh
```

The launcher starts the FastAPI backend and the Next.js frontend, then prints the local URLs. If `.venv/bin/python` exists, the script uses it automatically.

To stop the local servers:

```bash
./scripts/run-local.sh stop
```

## Developer Checks

Frontend lint:

```bash
cd web
npm run lint
```

Backend tests:

```bash
python3 -m pytest backend/tests -q
```

If you run the frontend and backend separately, point the frontend at the backend by setting `NEXT_PUBLIC_API_URL`.
