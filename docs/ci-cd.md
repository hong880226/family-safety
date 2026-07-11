# CI/CD Pipeline

This document describes the GitHub Actions workflows and how to onboard
a new environment to receive built artifacts.

## Overview

| Workflow | Trigger | Runner | Outcome |
|----------|---------|--------|---------|
| `backend.yml` | PR / push to `main` touching `backend/**` | ubuntu-latest | Lint (ruff + mypy) + pytest against Postgres + Redis |
| `docker-publish.yml` | push to `main` touching `backend/**`, `deploy/**`, or self | ubuntu-latest | Build & push Docker image to Aliyun |
| `agent-windows-build.yml` | PR / push to `main` touching `agent-windows/**` | windows-latest | Build Release binaries, zip, upload artifact |

## Required GitHub Secrets

Configure once at `Settings → Secrets and variables → Actions → New repository secret`.

| Secret | Example value | Where to get it |
|--------|---------------|-----------------|
| `ALIYUN_REGISTRY_USER` | `your-aliyun-username` | Aliyun console → Container Registry → Access credentials |
| `ALIYUN_REGISTRY_PASSWORD` | `xxxxxx` | Same as above |
| `ALIYUN_REGISTRY_NAMESPACE` | `familysafety` | Aliyun console → your registry → namespace name |

After push, the image is reachable as:

```
registry.cn-hangzhou.aliyuncs.com/<ALIYUN_REGISTRY_NAMESPACE>/familysafety-backend:<sha>
registry.cn-hangzhou.aliyuncs.com/<ALIYUN_REGISTRY_NAMESPACE>/familysafety-backend:latest
```

> The region is `cn-hangzhou` (Hangzhou). To change it, edit
> `env.REGION` at the top of `docker-publish.yml`.

## Local quick check before push

```bash
# Backend
cd backend
pip install -r requirements.txt -r requirements-dev.txt
ruff check .
mypy app/
pytest -v
```

## Verifying a deployed image

After the publish workflow finishes, you can pull and run it locally:

```bash
docker pull registry.cn-hangzhou.aliyuncs.com/<namespace>/familysafety-backend:latest
docker run --rm -p 8000:8000 \
  -e DATABASE_URL='postgresql+asyncpg://user:pass@host:5432/db' \
  -e REDIS_URL='redis://host:6379/0' \
  -e JWT_SECRET='change-me' \
  -e LLM_BASE_URL='https://api.deepseek.com/v1' \
  -e LLM_API_KEY='sk-...' \
  registry.cn-hangzhou.aliyuncs.com/<namespace>/familysafety-backend:latest
curl http://localhost:8000/healthz
```

## Workflow files

- `.github/workflows/backend.yml` — test suite
- `.github/workflows/docker-publish.yml` — image build & push
- `.github/workflows/agent-windows-build.yml` — Windows agent build

## Re-running the publish workflow manually

`docker-publish.yml` supports `workflow_dispatch` with an optional
`tag` input. Use it from the Actions tab → Build & Publish → Run workflow
to publish a specific version tag (e.g. `v0.1.0-redos-fix1`).
