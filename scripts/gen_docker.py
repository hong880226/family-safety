"""Generate Docker files for backend."""
from pathlib import Path

BACKEND = Path("E:/codeRepo/familysafety/backend")
DEPLOY = Path("E:/codeRepo/familysafety/deploy")


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  wrote {path.relative_to(Path('E:/codeRepo/familysafety'))} ({len(content)} bytes)")


# Backend Dockerfile
write(BACKEND / "Dockerfile", """# syntax=docker/dockerfile:1.7

FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \\
    PYTHONDONTWRITEBYTECODE=1 \\
    PIP_NO_CACHE_DIR=1 \\
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System deps for asyncpg / bcrypt
RUN apt-get update && apt-get install -y --no-install-recommends \\
        build-essential \\
        libpq-dev \\
        curl \\
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first (cache layer)
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy app
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \\
    CMD curl -fsS http://localhost:8000/healthz || exit 1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
""")


write(BACKEND / ".dockerignore", """__pycache__
*.pyc
*.pyo
*.pyd
.Python
*.egg-info/
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/
venv/
.venv/
.env
.env.local
*.db
*.sqlite
*.log
logs/
tests/
.git/
.gitignore
.idea/
.vscode/
*.md
uvicorn.log
smoke_test.py
e2e_test.py
""")


# Alembic config
write(BACKEND / "alembic.ini", """[alembic]
script_location = alembic
prepend_sys_path = .
sqlalchemy.url = sqlite:///./familysafety.db

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
""")


write(BACKEND / "alembic" / "env.py", """\"\"\"Alembic env (placeholder; using Base.metadata.create_all for v0.1).\"\"\"
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# We use Base.metadata.create_all on startup instead of Alembic for v0.1.
# This file is a placeholder so `alembic` CLI works.
target_metadata = None


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
""")


write(BACKEND / "alembic" / "script.py.mako", """\"\"\"${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
\"\"\"
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
""")


# docker-compose.yml at deploy/
write(DEPLOY / "docker-compose.yml", """services:
  postgres:
    image: postgres:16-alpine
    container_name: fs-postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-familysafety}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-familysafety}
      POSTGRES_DB: ${POSTGRES_DB:-familysafety}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "${POSTGRES_PORT:-5432}:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-familysafety}"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: fs-redis
    restart: unless-stopped
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data
    ports:
      - "${REDIS_PORT:-6379}:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  backend:
    build:
      context: ../backend
      dockerfile: Dockerfile
    container_name: fs-backend
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    environment:
      ENVIRONMENT: ${ENVIRONMENT:-prod}
      DEBUG: ${DEBUG:-false}
      DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER:-familysafety}:${POSTGRES_PASSWORD:-familysafety}@postgres:5432/${POSTGRES_DB:-familysafety}
      REDIS_URL: redis://redis:6379/0
      JWT_SECRET: ${JWT_SECRET:?JWT_SECRET must be set in .env}
      JWT_EXPIRE_MINUTES: ${JWT_EXPIRE_MINUTES:-10080}
      LLM_BASE_URL: ${LLM_BASE_URL}
      LLM_API_KEY: ${LLM_API_KEY}
      LLM_MODEL: ${LLM_MODEL:-deepseek-chat}
      CORS_ORIGINS: ${CORS_ORIGINS:-["*"]}
    ports:
      - "${BACKEND_PORT:-8000}:8000"
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:8000/readyz"]
      interval: 30s
      timeout: 5s
      retries: 3

volumes:
  postgres_data:
  redis_data:
""")


write(DEPLOY / ".env.example", """# Copy to .env and customize

# --- PostgreSQL ---
POSTGRES_USER=familysafety
POSTGRES_PASSWORD=change-me-please
POSTGRES_DB=familysafety
POSTGRES_PORT=5432

# --- Redis ---
REDIS_PORT=6379

# --- Backend ---
ENVIRONMENT=prod
DEBUG=false
BACKEND_PORT=8000

# --- JWT (REQUIRED, generate a random 32+ char string) ---
JWT_SECRET=please-replace-with-a-random-32-char-secret-string
JWT_EXPIRE_MINUTES=10080

# --- LLM (any OpenAI-compatible endpoint) ---
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=sk-your-deepseek-key
LLM_MODEL=deepseek-chat

CORS_ORIGINS=["*"]
""")


write(DEPLOY / "README.md", """# FamilySafety 部署

## 一键启动（开发）

```bash
cd deploy
cp .env.example .env
# 编辑 .env，至少填 JWT_SECRET 和 LLM_API_KEY

docker compose up -d
docker compose logs -f backend
```

浏览器访问：
- API 文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/healthz

## 数据持久化

- PostgreSQL 数据：Docker volume `postgres_data`
- Redis 数据：Docker volume `redis_data`

## 升级

```bash
cd deploy
git pull
docker compose pull
docker compose up -d --build
```

## 备份

```bash
# 备份数据库
docker exec fs-postgres pg_dump -U familysafety familysafety > backup.sql

# 恢复
cat backup.sql | docker exec -i fs-postgres psql -U familysafety familysafety
```

## 卸载

```bash
docker compose down -v  # -v 会同时删除数据卷
```
""")

print("\nDone. Docker files ready.")