# relocate_helper

AI-помощник для путешественников и экспатов: сбор данных из разрешённых источников, база знаний, Telegram-бот и админ-панель.

> Полное ТЗ: [TZ_telegram_parser_ai.md](TZ_telegram_parser_ai.md)  
> Продуктовые решения: [docs/product-decisions.md](docs/product-decisions.md)

## Требования

- Python **3.12+**
- [Docker](https://docs.docker.com/get-docker/) и Docker Compose (для локальной инфраструктуры)
- Git

## Быстрый старт (локально)

### 1. Клонировать и настроить окружение

```bash
git clone https://github.com/spaguet/relocate_parser.git relocate_helper
cd relocate_helper
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/macOS
source .venv/bin/activate

pip install -e ".[dev]"
cp .env.example .env   # при необходимости отредактируйте
```

### 2. Поднять инфраструктуру

```bash
docker compose up --build -d
```

Сервисы:

| Сервис | URL / порт |
|--------|------------|
| API | http://localhost:8000 |
| Health (live) | http://localhost:8000/health/live |
| Health (ready) | http://localhost:8000/health/ready |
| Admin API (sources) | http://localhost:8000/admin/sources |
| OpenAPI docs | http://localhost:8000/docs |
| PostgreSQL | localhost:5432 |
| Redis | localhost:6379 |
| MinIO (S3) | http://localhost:9000 (консоль: :9001) |

### 3. Запуск API без Docker (опционально)

```bash
# Убедитесь, что postgres/redis/minio запущены через compose
export DATABASE_URL=postgresql://relocate:relocate@localhost:5432/relocate_helper
export REDIS_URL=redis://localhost:6379/0
export S3_ENDPOINT_URL=http://localhost:9000

relocate-helper-api
# или: python -m relocate_helper.main
```

### 4. Worker (RQ)

```bash
relocate-helper-worker
```

## Разработка

```bash
# Windows
.\scripts\dev.ps1 install-dev
.\scripts\dev.ps1 test

# Linux/macOS / Make
make install-dev
make test
make lint
make typecheck
make format
```

| Команда | Описание |
|---------|----------|
| `make lint` | Ruff lint |
| `make format` | Ruff format + autofix |
| `make typecheck` | mypy |
| `make test` | pytest smoke tests |
| `make migrate` | Alembic upgrade head |
| `make seed` | Idempotent geo/topics/plans seed |
| `make up` / `make down` | Docker Compose |

## Структура проекта

```text
src/relocate_helper/
├── api/           # FastAPI app, health endpoints, dependencies
├── admin/         # Source registry API, schemas, sync_config crypto
├── storage/       # ObjectStorage (S3/memory), document versions, deletion
├── bot/           # Telegram bot (aiogram) — позже
├── ingestion/     # telegram, web, youtube, files
├── processing/    # normalize, chunk, extract — позже
├── retrieval/     # hybrid search — позже
├── answering/     # answer generation — позже
├── billing/       # plans, limits — позже
├── db/            # models, migrations, repository
├── workers/       # RQ worker
└── common/        # config, logging, health
```

## Секреты и безопасность

- **Не коммитьте** `.env`, файлы сессии Telethon (`*.session`), API-ключи.
- Используйте `.env.example` как шаблон с **фиктивными** значениями.
- Production: задайте `APP_ENV=production` и реальные `SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`, S3 credentials — приложение упадёт при старте, если останутся dev-defaults.

## Health checks

- `GET /health/live` — процесс жив (для liveness).
- `GET /health/ready` — проверка PostgreSQL, Redis, S3 (MinIO); статус `degraded`, если зависимость недоступна.

## Документация

- [docs/data-model.md](docs/data-model.md) — ER-диаграмма и правила удаления (промпт 2)
- [steps.md](steps.md) — чеклист промптов реализации

## Лицензия

Proprietary — внутренний проект.
