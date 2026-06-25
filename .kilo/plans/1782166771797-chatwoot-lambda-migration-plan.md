# Plan de migración: Chatwoot sobre deploy Lambda de main

## Resultado objetivo

Migrar `feature/chatwoot-integration` para que conserve la funcionalidad Chatwoot sin reemplazar el despliegue serverless definido en `main` (`7a18022`, merge de `2f6bf72`). La rama final debe desplegar backend en Lambda/API Gateway con estado durable en DynamoDB y secretos resueltos desde SSM/Secrets Manager.

## Decisiones cerradas

| Tema | Decisión |
|---|---|
| Deploy base | Usar el deploy Lambda de `main` como fuente de verdad. |
| ECS/Fargate/Cloudflare/Valkey | Revertirlo de esta rama, salvo archivos que ya existan en `main`. |
| Estado productivo Chatwoot | Migrar a DynamoDB usando/extiendiendo `ChatbotStateRepository`. |
| Redis/Valkey | Fuera de alcance para esta migración. No introducir VPC/Valkey en Lambda ahora. |
| Secretos | Usar valores locales solo para desarrollo; producción debe usar `*_SECRET_REF`. |
| Debounce Chatwoot | No depender de `asyncio.create_task`/`sleep` como mecanismo productivo en Lambda. |

## Fase 1: limpiar la rama contra `main`

1. Guardar un respaldo del estado actual si hay cambios staged importantes que no estén en commits.
2. Restaurar desde `main` los artefactos de deploy serverless:
   - `.github/workflows/ci.yml`
   - `.env.example`
   - `.gitignore`
   - `docs/deployment.md`
   - `infra/terraform/**`
   - `scripts/**`
   - `pyproject.toml`
   - `uv.lock`
3. Quitar del stage cualquier archivo de memoria local accidental:
   - `.engram/**`
4. Confirmar que vuelven a existir las piezas Lambda:
   - `infra/terraform/modules/lambda_backend/*`
   - `scripts/build_lambda_package.py`
   - `scripts/lambda_smoke.py`
   - `scripts/lambda_rollback.py`
   - `scripts/workflow_deploy_checks.py`
   - dependencia `mangum>=0.19.0`
   - `[tool.arte_chatbot.lambda_package]`

## Fase 2: restaurar runtime serverless

1. En `backend/main.py`, preservar la base de `main`:
   - import de `Mangum`
   - `_build_state_repository()`
   - wiring de `DynamoDBStateRepository`
   - `session_manager.set_state_repository(...)`
   - `set_buffer_state_repository(...)`
   - `rate_limiter.set_state_repository(...)`
   - `handler = _EventLoopSafeMangum(app)`
2. Reintegrar endpoints Chatwoot encima de esa base, sin remover `/chat`, `/buffer-result`, `/health` ni el handler Lambda.
3. En `backend/app/config.py`, conservar settings serverless:
   - `STATE_BACKEND`
   - `DYNAMODB_STATE_TABLE_NAME`
   - `DYNAMODB_STATE_KEY_PREFIX`
   - `SESSION_TTL_SECONDS`
   - `BUFFER_TTL_SECONDS`
   - `RATE_LIMIT_TTL_SECONDS`
   - `LAMBDA_TIMEOUT_SECONDS`
   - `OPENAI_API_KEY_SECRET_REF`
   - `CHAT_API_KEY_SECRET_REF`
4. Restaurar `backend/app/secret_resolver.py` y mantener sus usos en:
   - `backend/app/auth.py`
   - `backend/app/file_inputs.py`
   - `backend/app/llm_client.py`

## Fase 3: migrar estado Chatwoot a DynamoDB

1. Extender el boundary `ChatbotStateRepository` para cubrir estado Chatwoot mínimo:
   - mapping `chatwoot_conversation_id -> session_id`
   - mapping inverso `session_id -> chatwoot_conversation_id`
   - idempotency keys de webhooks/mensajes
   - buffer de mensajes por conversación
   - estado de procesamiento/escalamiento
   - outbox o registro mínimo de respuestas enviadas si hace falta reintento seguro
2. Implementar esos métodos en `DynamoDBStateRepository` con TTL y `key_prefix` igual al resto del estado serverless.
3. Refactorizar `SessionManager` para mantener la API síncrona actual, pero delegar estado durable en el repository cuando `STATE_BACKEND=dynamodb`.
4. Refactorizar `MessageBuffer` para que el flujo Chatwoot use repository durable en producción.
5. Mantener memoria local solo como fallback/desarrollo/tests, no como comportamiento productivo Lambda.

## Fase 4: reemplazar debounce inseguro en Lambda

1. Eliminar dependencia productiva de tareas en proceso para Chatwoot:
   - `asyncio.create_task(...)`
   - `asyncio.sleep(...)` como timer de debounce
2. Elegir el comportamiento Lambda-safe inicial:
   - recomendado: procesar el webhook entrante de forma síncrona/idempotente sin debounce productivo, o
   - usar estado durable y polling/trigger externo explícito en una fase posterior.
3. Si se mantiene debounce funcional, documentarlo como mejor esfuerzo solo local, no como garantía productiva.
4. Asegurar que Chatwoot reciba 5xx si el procesamiento real falla y que los reintentos sean idempotentes.

## Fase 5: secretos y configuración

1. Agregar settings para secretos Chatwoot por referencia:
   - `CHATWOOT_AGENT_BOT_TOKEN_SECRET_REF`
   - `CHATWOOT_WEBHOOK_SECRET_REF`
2. Resolverlos con `configured_secret_value(...)` igual que `OPENAI_API_KEY` y `CHAT_API_KEY`.
3. Mantener como no secretos:
   - `CHATWOOT_ENABLED`
   - `CHATWOOT_API_URL`
   - `CHATWOOT_ACCOUNT_ID`
   - `CHATWOOT_INBOX_ID`
   - `CHATWOOT_HANDOFF_TEAM_ID`
   - labels Chatwoot
4. Actualizar `.env.example` para distinguir local vs producción:
   - valores plaintext solo para local
   - producción mediante `*_SECRET_REF`
5. No agregar `REDIS_URL`/`REDIS_PASSWORD` al contrato productivo si Redis queda fuera de alcance.

## Fase 6: tests

1. Restaurar y mantener tests serverless de `main`:
   - `backend/tests/test_lambda_runtime.py`
   - `backend/tests/test_runtime_secret_refs.py`
   - `backend/tests/test_state_repository.py`
   - `backend/tests/test_repository_wiring.py`
   - tests de scripts Lambda en `scripts/tests/**`
2. Adaptar tests Chatwoot para no asumir Redis productivo:
   - `backend/tests/test_chatwoot_handler.py`
   - `backend/tests/test_chatwoot_endpoints.py`
   - `backend/tests/test_chatwoot_scenarios.py`
   - `backend/tests/test_message_buffer_redis.py` debe renombrarse o limitarse explícitamente a modo local/legacy si se conserva.
3. Agregar cobertura para:
   - resolución de secretos Chatwoot por `*_SECRET_REF`
   - idempotencia de webhook duplicado
   - mapping conversación/sesión persistido en DynamoDB fake/mock
   - handler Lambda con rutas Chatwoot disponibles
   - `STATE_BACKEND=dynamodb` sin Redis configurado
4. Ejecutar como mínimo:
   - `pytest backend/tests/test_lambda_runtime.py`
   - `pytest backend/tests/test_runtime_secret_refs.py`
   - `pytest backend/tests/test_repository_wiring.py`
   - `pytest backend/tests/test_chatwoot_endpoints.py`
   - `pytest backend/tests/test_chatwoot_handler.py`
   - `pytest scripts/tests/test_lambda_delivery_scripts.py scripts/tests/test_workflow_deploy_checks.py`

## Fase 7: validación de deploy

1. Verificar que el workflow siga construyendo `dist/lambda/backend.zip`.
2. Verificar que no reaparezcan jobs productivos ECS/Fargate.
3. Verificar Terraform Lambda/API Gateway/DynamoDB:
   - `infra/terraform/modules/lambda_backend/*`
   - env `prod`
   - env `local-staging` si aplica
4. Verificar guard checks de scripts para que fallen si:
   - se borra `handler`
   - se borra `mangum`
   - se elimina `lambda_backend`
   - se reintroduce deploy productivo ECS como ruta principal
5. Smoke esperado:
   - `/health`
   - `/chat`
   - `/health/chatwoot` con Chatwoot disabled
   - `/webhook/chatwoot` rechazando firma inválida
   - `/webhook/chatwoot` aceptando firma válida en modo test/mock

## Riesgos principales

| Riesgo | Mitigación |
|---|---|
| Borrar de nuevo piezas Lambda durante merge | Restaurar deploy desde `main` antes de re-aplicar Chatwoot. |
| Estado perdido por memoria local en Lambda | Usar DynamoDB repository para sesiones, buffers, ownership e idempotencia. |
| Secretos Chatwoot en env plaintext productivo | Agregar `*_SECRET_REF` y resolver por SSM/Secrets Manager. |
| Debounce roto por freeze de Lambda | No usar tareas en proceso como garantía productiva. |
| Tests verdes pero deploy roto | Mantener tests Lambda/runtime/deploy guard de `main`. |
| PR demasiado grande | Separar en commits por fase y revisar primero deploy restore, luego runtime, luego Chatwoot state. |

## Orden sugerido de commits

1. `chore: restore lambda deployment baseline`
2. `fix: preserve lambda runtime wiring for chatwoot branch`
3. `feat: resolve chatwoot secrets from runtime references`
4. `feat: persist chatwoot state in dynamodb repository`
5. `fix: make chatwoot webhook processing lambda-safe`
6. `test: cover chatwoot lambda deployment integration`

## Fuera de alcance

- Rediseñar `main` para Lambda en VPC con Valkey/Redis.
- Reintroducir ECS/Fargate como deploy productivo principal.
- Implementar preview environments por PR; eso ya está documentado como follow-up separado.
- Cambiar arquitectura frontend/admin salvo que el restore desde `main` lo requiera.

## Criterio de finalización

La migración está completa cuando la rama conserva todos los tests y guards Lambda de `main`, Chatwoot funciona sin Redis productivo, los secretos productivos se resuelven por referencias AWS, y el workflow sigue desplegando el backend como Lambda/API Gateway con DynamoDB como estado durable.
