# Issues — Cola de Mensajes y Migración a Async

> Proyecto: arte-chatbot
> Assignee: juanpret777
> Labels se indican por issue.

---

## Issue padre: US-ASYNC — Migración a Async y Cola de Mensajes

**Título**: `[US-ASYNC] Migrar backend a async con cola de mensajes para concurrencia`

**Labels**: `enhancement`, `architecture`, `priority: high`

**Assignee**: juanpret777

**Descripción**:

### Contexto

El backend actual opera de forma completamente sincrónica. El endpoint `/chat` es un `def` (no `async def`) que FastAPI ejecuta en un threadpool. Los clientes `LLMClient`, `FileInputsClient` y `S3Client` usan llamadas bloqueantes (`openai.OpenAI`, `boto3.client`). Esto limita la capacidad del sistema para atender múltiples clientes simultáneamente, ya que cada request mantiene un thread bloqueado durante 5-20 segundos (principalmente en llamadas a OpenAI).

### Objetivo

Migrar el backend a una arquitectura fully-async con:
1. **Cola de mensajes** (`asyncio.Queue`) para encolar requests entrantes
2. **Pool de workers** (`asyncio.Task`) que consumen de la cola y procesan requests en paralelo
3. **Clientes async** (`AsyncOpenAI`, S3 via `asyncio.to_thread`) para no bloquear el event loop
4. **Endpoint async** que encola y espera la respuesta del worker via `asyncio.Future`

### Alcance

Archivos afectados:
- `backend/app/queue.py` (nuevo)
- `backend/app/llm_client.py`
- `backend/app/file_inputs.py`
- `backend/app/s3_client.py`
- `backend/app/session.py`
- `backend/app/config.py`
- `backend/main.py`
- `pyproject.toml`
- `.env.example`
- `docker-compose.yml`

### Criterios de aceptación

- [ ] El endpoint `/chat` es `async def` y encola requests en `asyncio.Queue`
- [ ] Workers asíncronos procesan requests en paralelo (hasta `QUEUE_WORKERS` simultáneos)
- [ ] Todos los clientes (LLM, FileInputs, S3) usan operaciones async
- [ ] `SessionManager` usa `asyncio.Lock` en lugar de `threading.Lock`
- [ ] Backpressure funciona: requests se esperan cuando la cola está llena
- [ ] Tests existentes migrados a `pytest-asyncio` y pasan
- [ ] Variables de entorno `QUEUE_WORKERS` y `MAX_QUEUE_SIZE` configurables
- [ ] `docker compose up -d` funciona correctamente con la nueva arquitectura

---

## Subissue 1: TS-ASYNC-01 — Configuración y dependencias

**Título**: `[TS-ASYNC-01] Agregar configuración de cola y dependencias de testing async`

**Labels**: `chore`, `infrastructure`

**Assignee**: juanpret777

**Parent**: US-ASYNC

**Descripción**:

### Tarea

Preparar el entorno para la migración async sin romper funcionalidad existente.

### Pasos

1. Agregar `pytest-asyncio>=0.23.0` a `[dependency-groups].dev` en `pyproject.toml`
2. Agregar campos al `Settings` en `backend/app/config.py`:
   - `queue_workers: int = Field(default=5, ...)`
   - `max_queue_size: int = Field(default=100, ...)`
3. Actualizar `.env.example` con:
   ```
   QUEUE_WORKERS=5
   MAX_QUEUE_SIZE=100
   ```
4. Verificar que todos los tests existentes sigan pasando

### Criterios de aceptación

- [ ] `pyproject.toml` incluye `pytest-asyncio`
- [ ] `Settings` tiene campos `queue_workers` y `max_queue_size` con defaults
- [ ] `.env.example` documenta las nuevas variables
- [ ] `pytest` pasa sin errores

---

## Subissue 2: TS-ASYNC-02 — Migrar LLMClient a AsyncOpenAI

**Título**: `[TS-ASYNC-02] Migrar LLMClient de openai.OpenAI a openai.AsyncOpenAI`

**Labels**: `refactor`, `async`

**Assignee**: juanpret777

**Parent**: US-ASYNC

**Descripción**:

### Tarea

Convertir `backend/app/llm_client.py` de sincrónico a asíncrono.

### Cambios específicos

1. Importar `AsyncOpenAI` en lugar de (o además de) `OpenAI`
2. Cambiar `self._openai_client: Optional[OpenAI]` → `Optional[AsyncOpenAI]`
3. En la property `openai_client`, instanciar `AsyncOpenAI(api_key=self.api_key)`
4. Convertir `get_llm_response_with_tools()` a `async def`:
   - `response = self.openai_client.chat.completions.create(...)` → `response = await self.openai_client.chat.completions.create(...)`
5. Convertir `get_llm_response_with_file()` a `async def`:
   - Mismo patrón con `await`
6. Mantener la firma pública y los tipos de retorno idénticos
7. Las excepciones capturadas (`AuthenticationError`, `APIError`) son las mismas en async

### Tests

- Migrar `backend/tests/test_llm_client.py` a `pytest-asyncio`
- Usar `AsyncMock` para mockear el cliente OpenAI
- Los tests de error handling deben verificar que las excepciones se propagan correctamente en contexto async

### Criterios de aceptación

- [ ] `LLMClient` usa `AsyncOpenAI`
- [ ] `get_llm_response_with_tools()` es `async def` y usa `await`
- [ ] `get_llm_response_with_file()` es `async def` y usa `await`
- [ ] Tests de `test_llm_client.py` pasan con `pytest-asyncio`

---

## Subissue 3: TS-ASYNC-03 — Migrar FileInputsClient a async

**Título**: `[TS-ASYNC-03] Migrar FileInputsClient de openai.OpenAI a openai.AsyncOpenAI`

**Labels**: `refactor`, `async`

**Assignee**: juanpret777

**Parent**: US-ASYNC

**Descripción**:

### Tarea

Convertir `backend/app/file_inputs.py` de sincrónico a asíncrono.

### Cambios específicos

1. Importar `AsyncOpenAI`
2. Cambiar `self._client: Optional[OpenAI]` → `Optional[AsyncOpenAI]`
3. En la property `client`, instanciar `AsyncOpenAI(api_key=self.api_key)`
4. Convertir `upload_pdf()` a `async def`:
   - `response = self.client.files.create(...)` → `response = await self.client.files.create(...)`
5. Convertir `delete_file()` a `async def`:
   - `self.client.files.delete(file_id)` → `await self.client.files.delete(file_id)`

### Tests

- Migrar `backend/tests/test_file_inputs.py` a `pytest-asyncio`
- Mockear `AsyncOpenAI.files.create()` y `AsyncOpenAI.files.delete()`

### Criterios de aceptación

- [ ] `FileInputsClient` usa `AsyncOpenAI`
- [ ] `upload_pdf()` es `async def` y usa `await`
- [ ] `delete_file()` es `async def` y usa `await`
- [ ] Tests pasan

---

## Subissue 4: TS-ASYNC-04 — Migrar S3Client a async

**Título**: `[TS-ASYNC-04] Agregar métodos async a S3Client usando asyncio.to_thread`

**Labels**: `refactor`, `async`

**Assignee**: juanpret777

**Parent**: US-ASYNC

**Descripción**:

### Tarea

Agregar wrappers async a `S3Client` sin reemplazar la implementación sync (que se mantiene como método interno).

### Cambios específicos

1. Importar `import asyncio`
2. Renombrar `download_pdf()` actual a `_download_pdf_sync()` (método privado)
3. Crear nuevo `async def download_pdf()` que llame:
   ```python
   async def download_pdf(self, s3_key: str) -> bytes:
       return await asyncio.to_thread(self._download_pdf_sync, s3_key)
   ```
4. Hacer lo mismo para `file_exists()` → `_file_exists_sync()` + `async def file_exists()`
5. Mantener `boto3` sync como dependencia (no agregar `aioboto3`)

### Justificación de `asyncio.to_thread` vs `aioboto3`

- Las operaciones S3 son rápidas (~100-500ms), no justifican la complejidad de `aioboto3`
- `asyncio.to_thread` es stdlib y no agrega dependencias
- El patrón es idéntico al que FastAPI usa internamente para endpoints sync

### Tests

- Agregar tests para los nuevos métodos async en `backend/tests/test_s3_client.py`
- Usar `AsyncMock` para la función interna sync

### Criterios de aceptación

- [ ] `S3Client.download_pdf()` es `async def` y delega a `_download_pdf_sync()` via `asyncio.to_thread`
- [ ] `S3Client.file_exists()` es `async def` y delega a `_file_exists_sync()` via `asyncio.to_thread`
- [ ] Tests pasan

---

## Subissue 5: TS-ASYNC-05 — Implementar sistema de cola y workers

**Título**: `[TS-ASYNC-05] Crear módulo backend/app/queue.py con MessageQueue y workers async`

**Labels**: `feature`, `architecture`, `core`

**Assignee**: juanpret777

**Parent**: US-ASYNC

**Descripción**:

### Tarea

Implementar el módulo central de cola de mensajes y workers asíncronos.

### Archivo nuevo: `backend/app/queue.py`

#### Clase `ChatMessage`

```python
from dataclasses import dataclass, field
from typing import Any
import asyncio

@dataclass
class ChatMessage:
    """Mensaje encolado para procesamiento por un worker."""
    request_id: str
    session_id: str
    message: str
    future: asyncio.Future = field(default_factory=lambda: asyncio.get_event_loop().create_future())
```

#### Clase `MessageQueue`

```python
class MessageQueue:
    """Cola de mensajes con pool de workers async."""

    def __init__(
        self,
        max_workers: int = 5,
        max_queue_size: int = 100,
        llm_client: LLMClient = ...,
        s3_client: S3Client = ...,
        file_inputs_client: FileInputsClient = ...,
        session_manager: SessionManager = ...,
    ): ...

    async def start(self) -> None:
        """Crea y lanza max_workers tareas asyncio como workers."""

    async def stop(self) -> None:
        """Cancela todos los workers y espera su finalización."""

    async def enqueue(self, message: ChatMessage) -> None:
        """Pone un mensaje en la cola. Bloquea si la cola está llena (backpressure)."""

    async def _worker(self, worker_id: int) -> None:
        """
        Loop principal del worker:
        1. await self.queue.get() para obtener siguiente mensaje
        2. Procesar mensaje (escalation, LLM calls, tool calls)
        3. message.future.set_result() o message.future.set_exception()
        4. self.queue.task_done()
        """
```

#### Lógica del worker

El worker replica la lógica actual de `chat_endpoint` pero de forma async:

```python
async def _worker(self, worker_id: int) -> None:
    while True:
        try:
            msg = await self.queue.get()
            try:
                # 1. Obtener contexto de sesión
                context = await self.session_manager.get_context_string(msg.session_id)

                # 2. Primera llamada LLM
                llm_response = await self.llm_client.get_llm_response_with_tools(
                    message=msg.message,
                    session_id=msg.session_id,
                    system_prompt=ARTE_SYSTEM_PROMPT,
                    context=context,
                )

                # 3. Procesar tool calls si existen
                tool_calls = llm_response.get("tool_calls")
                if tool_calls:
                    for tool_call in tool_calls:
                        if tool_call.get("function", {}).get("name") == "leer_ficha_tecnica":
                            response_text = await self._process_tool_call_async(
                                tool_call, msg.message, msg.session_id
                            )
                            break
                    else:
                        response_text = llm_response.get("output_text", "")
                else:
                    response_text = llm_response.get("output_text", "")

                # 4. Guardar en sesión
                await self.session_manager.add_turn(
                    session_id=msg.session_id,
                    question=msg.message,
                    answer=response_text,
                    source_documents=[],
                )

                # 5. Resolver future
                if not msg.future.done():
                    msg.future.set_result(ChatResponse(
                        response=response_text,
                        escalate=False,
                        session_id=msg.session_id,
                    ))

            except Exception as e:
                if not msg.future.done():
                    msg.future.set_exception(e)
            finally:
                self.queue.task_done()

        except asyncio.CancelledError:
            break
```

### Tests: `backend/tests/test_queue.py`

Tests unitarios para:
- `ChatMessage` creation
- `MessageQueue` start/stop lifecycle
- `enqueue`/`dequeue` básico
- Worker procesa mensaje correctamente (mock de LLM)
- Worker maneja errores sin crashear (future recibe excepción)
- Backpressure: enqueue bloquea cuando cola está llena
- Múltiples workers procesan en paralelo
- `stop()` cancela workers limpiamente

### Criterios de aceptación

- [ ] `ChatMessage` dataclass con `request_id`, `session_id`, `message`, `future`
- [ ] `MessageQueue` con `start()`, `stop()`, `enqueue()`
- [ ] Workers procesan requests y resuelven futures
- [ ] Errores en workers se propagan como excepciones en el future
- [ ] Backpressure funciona (cola llena → enqueue espera)
- [ ] `stop()` cancela workers sin dejar tareas huérfanas
- [ ] Tests unitarios pasan

---

## Subissue 6: TS-ASYNC-06 — Migrar SessionManager a asyncio.Lock

**Título**: `[TS-ASYNC-06] Migrar SessionManager de threading.Lock a asyncio.Lock`

**Labels**: `refactor`, `async`

**Assignee**: juanpret777

**Parent**: US-ASYNC

**Descripción**:

### Tarea

Convertir `backend/app/session.py` para usar `asyncio.Lock` en lugar de `threading.Lock`, y hacer los métodos que adquieren el lock en `async def`.

### Cambios específicos

1. Importar `import asyncio` (reemplazar `import threading`)
2. Cambiar `self._lock = threading.Lock()` → `self._lock = asyncio.Lock()`
3. Convertir `add_turn()` a `async def`:
   ```python
   async def add_turn(self, ...) -> None:
       async with self._lock:
           ...
   ```
4. Convertir `clear_session()` a `async def`:
   ```python
   async def clear_session(self, session_id: str) -> None:
       async with self._lock:
           ...
   ```
5. `get_history()` y `get_context_string()` NO necesitan el lock (lecturas de dict son seguras en CPython con GIL, y en asyncio no hay true parallelism)

### Tests

- Migrar `backend/tests/test_session.py` a `pytest-asyncio`
- Test de concurrencia: múltiples coroutines añadiendo turns simultáneamente

### Criterios de aceptación

- [ ] `SessionManager` usa `asyncio.Lock`
- [ ] `add_turn()` es `async def`
- [ ] `clear_session()` es `async def`
- [ ] Tests pasan, incluyendo test de concurrencia

---

## Subissue 7: TS-ASYNC-07 — Integrar cola en endpoint /chat

**Título**: `[TS-ASYNC-07] Convertir endpoint /chat a async y conectar con MessageQueue`

**Labels**: `feature`, `integration`

**Assignee**: juanpret777

**Parent**: US-ASYNC

**Descripción**:

### Tarea

Modificar `backend/main.py` para:
1. Usar lifespan events para iniciar/detener los workers
2. Convertir `chat_endpoint` a `async def` que encola requests
3. Eliminar la lógica de procesamiento directo del endpoint (ahora vive en los workers)

### Cambios específicos

#### Lifespan

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: iniciar workers. Shutdown: detener workers."""
    queue_manager = MessageQueue(
        max_workers=settings.queue_workers,
        max_queue_size=settings.max_queue_size,
        llm_client=llm_client,
        s3_client=s3_client,
        file_inputs_client=file_inputs_client,
        session_manager=session_manager,
    )
    await queue_manager.start()
    app.state.queue_manager = queue_manager
    logger.info("Message queue started with %d workers", settings.queue_workers)
    yield
    await queue_manager.stop()
    logger.info("Message queue stopped")

app = FastAPI(title="ARTE Chatbot Backend", lifespan=lifespan)
```

#### Endpoint

```python
@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    request: ChatRequest,
    api_key: str = Depends(verify_api_key),
) -> ChatResponse:
    session_id = request.session_id or str(uuid.uuid4())
    request_id = str(uuid.uuid4())

    # Escalation check (se mantiene sync, es O(1))
    escalation_result = default_detector.detect(request.message)
    if escalation_result.escalate:
        await session_manager.add_turn(
            session_id=session_id,
            question=request.message,
            answer=DEFAULT_ESCALATION_MESSAGE,
            source_documents=[],
        )
        return ChatResponse(
            response=DEFAULT_ESCALATION_MESSAGE,
            escalate=True,
            reason=escalation_result.reason,
            session_id=session_id,
        )

    # Encolar mensaje
    msg = ChatMessage(
        request_id=request_id,
        session_id=session_id,
        message=request.message,
    )
    await app.state.queue_manager.enqueue(msg)

    # Esperar respuesta del worker (con timeout)
    try:
        response = await asyncio.wait_for(msg.future, timeout=60.0)
        return response
    except asyncio.TimeoutError:
        logger.error("Request timeout: request_id=%s", request_id)
        raise HTTPException(status_code=504, detail="Request timeout")
    except LLMServiceError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.exception("Unexpected error: request_id=%s", request_id)
        raise HTTPException(status_code=500, detail="Internal server error")
```

#### Eliminar `_process_tool_call` del módulo principal

La lógica de `_process_tool_call` se mueve a `MessageQueue._process_tool_call_async()` dentro del módulo de cola.

### Tests

- Migrar `backend/tests/test_chat.py` a `pytest-asyncio`
- Usar `httpx.AsyncClient` para testear el endpoint
- Mockear `MessageQueue` para tests unitarios del endpoint
- Test de integración con cola real y workers mockeados

### Criterios de aceptación

- [ ] `app` tiene `lifespan` que inicia/detiene `MessageQueue`
- [ ] `/chat` es `async def` y encola requests
- [ ] Timeout de 60s en `await future`
- [ ] Escalation se resuelve inmediatamente (sin encolar)
- [ ] `_process_tool_call` eliminado de `main.py` (vive en queue.py)
- [ ] Tests pasan

---

## Subissue 8: TS-ASYNC-08 — Actualizar Docker Compose y documentación

**Título**: `[TS-ASYNC-08] Actualizar docker-compose.yml, .env.example y documentación`

**Labels**: `chore`, `documentation`

**Assignee**: juanpret777

**Parent**: US-ASYNC

**Descripción**:

### Tarea

Actualizar los archivos de configuración y documentación para reflejar la nueva arquitectura.

### Cambios específicos

1. **`docker-compose.yml`**: Agregar variables de entorno al servicio backend:
   ```yaml
   environment:
     - QUEUE_WORKERS=5
     - MAX_QUEUE_SIZE=100
   ```

2. **`.env.example`**: Agregar:
   ```
   # Cola de mensajes
   QUEUE_WORKERS=5
   MAX_QUEUE_SIZE=100
   ```

3. **`AGENTS.md`**: Actualizar sección de arquitectura para mencionar el sistema de cola y workers async.

### Criterios de aceptación

- [ ] `docker-compose.yml` tiene variables `QUEUE_WORKERS` y `MAX_QUEUE_SIZE`
- [ ] `.env.example` documenta las nuevas variables
- [ ] `docker compose up -d` funciona con la nueva configuración

---

## Subissue 9: TS-ASYNC-09 — Validación end-to-end y carga

**Título**: `[TS-ASYNC-09] Validación end-to-end: concurrencia, backpressure y carga`

**Labels**: `testing`, `validation`

**Assignee**: juanpret777

**Parent**: US-ASYNC

**Descripción**:

### Tarea

Verificar que la arquitectura async funciona correctamente bajo condiciones reales.

### Pasos

1. **Health check**: `docker compose up -d` → `curl localhost:8000/health` OK
2. **Request simple**: Enviar un POST /chat y verificar respuesta correcta
3. **Concurrencia**: Enviar 5 requests simultáneos con `curl` o script Python:
   ```python
   import asyncio, httpx

   async def send_request(client, i):
       r = await client.post("http://localhost:8000/chat", json={"message": f"Test {i}"})
       print(f"Request {i}: {r.status_code} in {r.elapsed}")

   async with httpx.AsyncClient() as client:
       await asyncio.gather(*[send_request(client, i) for i in range(10)])
   ```
4. **Verificar logs**: Los logs deben mostrar workers diferentes procesando requests simultáneamente
5. **Backpressure**: Enviar 200 requests simultáneos y verificar que los excedentes esperan (no se rechazan)
6. **Full test suite**: `pytest` completo — todos pasan
7. **Linting**: `ruff check backend/ rag/` — sin errores
8. **Type checking**: `mypy backend/` — sin errores

### Criterios de aceptación

- [ ] Health check responde
- [ ] Request simple funciona
- [ ] 5+ requests simultáneos se procesan en paralelo (verificar en logs)
- [ ] Backpressure funciona (no HTTP 503 por threadpool saturado)
- [ ] `pytest` pasa al 100%
- [ ] `ruff check` sin errores
- [ ] `mypy` sin errores
