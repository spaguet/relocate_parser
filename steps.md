# Последовательность промптов для реализации relocate_helper

Выполняй этапы **строго по порядку**. Полный текст каждого промпта — в [TZ_telegram_parser_ai.md](TZ_telegram_parser_ai.md), раздел 16.

**Как отправлять ИИ:** `Выполни Промпт N из TZ_telegram_parser_ai.md` (для промптов 1–18 перед этим добавь общий префикс из раздела 16.2).

**Не передавай агенту:** API-ключи, Telegram-коды, файл сессии Telethon, production-секреты.

---

## Чеклист этапов

| Промпт | Выполнено | Дата | Название |
|:------:|:---------:|------|----------|
| 0 | [x] | 2026-07-25 | Зафиксировать открытые продуктовые решения |
| 1 | [x] | 2026-07-27 | Создать каркас проекта и локальную инфраструктуру |
| 2 | [x] | 2026-07-28 | Реализовать модель данных и миграции PostgreSQL |
| 3 | [x] | 2026-07-28 | Реализовать объектное хранилище и реестр источников |
| 4 | [ ] | | Реализовать разрешённый импорт Telegram |
| 5 | [ ] | | Реализовать ручную загрузку и разрешённый веб-импорт |
| 6 | [ ] | | Реализовать нормализацию, обезличивание, дедупликацию и chunking |
| 7 | [ ] | | Реализовать LLM-абстракцию, классификацию и извлечение фактов |
| 8 | [ ] | | Реализовать доказательства, конфликты, публикацию и карточки |
| 9 | [ ] | | Реализовать embeddings и гибридный retrieval |
| 10 | [ ] | | Реализовать проверку достаточности и генерацию ответа |
| 11 | [ ] | | Реализовать тарифы, доступ, лимиты и внутренний бюджет |
| 12 | [ ] | | Реализовать Telegram-бота и оплату Stars |
| 13 | [ ] | | Реализовать административное API, аутентификацию и UI |
| 14 | [ ] | | Связать фоновые задания и полный конвейер |
| 15 | [ ] | | Реализовать наблюдаемость, приватность и эксплуатационную защиту |
| 16 | [ ] | | Создать контрольный набор и автоматическую оценку качества |
| 17 | [ ] | | Подготовить CI/CD и окружения |
| 18 | [ ] | | Провести итоговый аудит готовности MVP |

---

## Заметки

| Промпт | Заметки |
|:------:|---------|
| 0 | Product decisions v0.2: Florianópolis/BR, RU, 8 тем быта, Claude, test mode без оплаты, источники/тарифы через admin, simple auth. Контрольный набор — ждём файл от владельца. |
| 1 | Каркас: src/relocate_helper (все модули), FastAPI /health/live|ready, structlog, pydantic-settings, RQ worker, Docker Compose (postgres+pgvector, redis, minio), 7 smoke tests. ADR: RQ. Docker не проверен — не установлен на машине. |
| 2 | PostgreSQL schema: 27 tables, async SQLAlchemy 2.x, Alembic 001_initial, pgvector+FTS, seed BR/Florianópolis/8 topics/4 plans, Database repository, docs/data-model.md. Integration tests skip без Postgres. |
| 3 | ObjectStorage (S3+memory), content-addressed keys, MIME/quarantine, DocumentStorageService (dedup), SourceRegistryService (encrypted sync_config), ContentDeletionService, admin API /admin/sources|documents. 21 tests pass; integration skip без Postgres. |
| 4 | |
| 5 | |
| 6 | |
| 7 | |
| 8 | |
| 9 | |
| 10 | |
| 11 | |
| 12 | |
| 13 | |
| 14 | |
| 15 | |
| 16 | |
| 17 | |
| 18 | |
