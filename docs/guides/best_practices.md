# Guía de Buenas Prácticas — Arte Chatbot

Esta guía consolida las convenciones de desarrollo, patrones de arquitectura y reglas de estilo para mantener la calidad y consistencia del código en el proyecto Arte Chatbot.

---

## 1. Arquitectura y Principios de Diseño

### SOLID Principles
- **S**ingle Responsibility: Cada módulo tiene una única responsabilidad. Ej: `S3Client` solo maneja operaciones con S3, no lógica de negocio.
- **O**pen/Closed: Abierto para extensión, cerrado para modificación.
- **L**iskov Substitution: Las subclases pueden sustituir sus clases base sin comportamiento inesperado.
- **I**nterface Segregation: Preferir muchos interfaces pequeños específicos (ej: `FileLoader` y `DocumentParser`) sobre uno grande general.
- **D**ependency Inversion: Depender de abstracciones, no de concreciones. Inyectar dependencias via constructor o `Annotated[ Depends()]`.

### Inyección de Dependencias en FastAPI
```python
# Correcto: Usar Depends para inyección
from fastapi import Depends

class ChatService:
    def __init__(self, llm_client: LLMClient, s3_client: S3Client):
        self.llm = llm_client
        self.s3 = s3_client

@router.post("/chat")
async def chat_endpoint(
    message: str,
    service: ChatService = Depends(ChatService)
):
    ...

# Incorrecto: No crear instancias en el endpoint
@router.post("/chat")
async def chat_endpoint(message: str):
    service = ChatService(LlmClient(), S3Client())  # ❌
```

### Async/Await
- Usar `async/await` para todas las operaciones I/O-bound (HTTP, S3, LLM calls).
- No bloquear el event loop con `time.sleep()`, usar `asyncio.sleep()`.
- Los tests pueden usar `pytest-asyncio` para testear funciones async.

```python
# Correcto
async def fetch_ficha_tecnica(path: str) -> bytes:
    return await s3_client.download_file(path)

# Incorrecto (bloqueante)
def fetch_ficha_tecnica(path: str) -> bytes:
    return s3_client.download_file(path)  # ❌ bloquea
```

---

## 2. Estilo de Código y Type Hints

### Naming Conventions
- `snake_case` para funciones, métodos, variables, argumentos
- `PascalCase` para clases, tipos, protocolos
- `SCREAMING_SNAKE_CASE` para constantes
- Prefijos `is_`, `has_`, `can_` para booleanos

```python
# Variables y funciones
user_id: str
is_authenticated: bool
def get_user_by_id(user_id: str) -> Optional[User]:
    ...

# Clases
class ChatService:
    ...

# Constantes
MAX_TOKEN_COUNT = 2000
```

### Type Hints Obligatorios
- Todas las funciones y métodos deben tener type hints completos (parámetros y retorno).
- Para tipos complejos usar `typing` (`Optional`, `List`, `Dict`, `Union`).
- Para alias simples, definir en mayúsculas.

```python
from typing import Optional, List, Dict, Any

IntentType = str
ConfidenceScore = float

def classify_intent(message: str) -> tuple[IntentType, ConfidenceScore]:
    ...

def get_session_history(session_id: str) -> Optional[List[Dict[str, Any]]]:
    ...
```

### Imports
Organizar en tres bloques separados por líneas en blanco:
1. stdlib (`datetime`, `json`, `pathlib`)
2. third-party (`fastapi`, `boto3`, `openai`)
3. local/app (`from backend.app.models import`)

Ordenar alfabéticamente dentro de cada bloque.

```python
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import boto3
from fastapi import Depends, HTTPException

from backend.app.models import ChatRequest, ChatResponse
```

---

## 3. Manejo de Errores

### No usar `except:` genérico
- Siempre especificar las excepciones que se capturan.
- Crear excepciones custom cuando el error tiene semántica de negocio.

```python
# Incorrecto
try:
    result = download_file(path)
except:
    logger.error("Error")

# Correcto
try:
    result = await s3_client.download_file(path)
except S3FileNotFoundError:
    raise HTTPException(status_code=404, detail="File not found")
except BotoCoreError as e:
    logger.error(f"S3 error: {e}")
    raise HTTPException(status_code=500, detail="Storage service error")
```

### Excepciones Custom
```python
class ChatbotError(Exception):
    """Base exception for chatbot errors."""
    pass

class EscalationError(ChatbotError):
    """Raised when escalation decision cannot be made."""
    pass

class SessionNotFoundError(ChatbotError):
    """Raised when session ID does not exist."""
    pass
```

---

## 4. Testing

### Estructura
- Tests en carpetas `tests/` dentro de cada módulo (`backend/tests/`, `rag/tests/`).
- Nombrar archivos como `test_<module>.py`.
- Nombrar funciones como `test_<scenario>_<expected_result>`.

```python
# backend/tests/test_session.py
import pytest

async def test_session_creates_new_when_not_exists():
    ...

async def test_session_retrieves_existing_context():
    ...
```

### Aislamiento de Dependencias
- Usar fixtures para mocks de S3, LLM, etc.
- No depender de servicios externos en tests unitarios.
- Los tests de integración pueden usar `moto` para mock AWS.

```python
# conftest.py
import pytest
from moto import mock_aws

@pytest.fixture
def s3_client():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        yield client
```

### Cobertura
- Mínimo 80% coverage en módulos modificados.
- Ejecutar con `pytest --cov=backend --cov=rag`.

---

## 5. Seguridad

### Secrets y Variables de Entorno
- Nunca hardcodear credenciales en código.
- Usar `pydantic.Settings` o `dotenv` para cargar desde `.env`.
- El archivo `.env` debe estar en `.gitignore`.

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    openai_api_key: str
    aws_access_key_id: str
    aws_secret_access_key: str

    class Config:
        env_file = ".env"
```

### Logs
- No loggear información sensible (API keys, passwords, PII).
- Usar structured logging (JSON) para producción.
- Incluir correlation IDs para trazabilidad.

---

## 6. Documentation

### Docstrings (Google Style)
```python
def get_ficha_tecnica(product_id: str) -> bytes:
    """Download technical spec PDF for a given product.

    Args:
        product_id: Unique identifier of the product (e.g., "LGU-500W-Mono").

    Returns:
        PDF file content as bytes.

    Raises:
        S3FileNotFoundError: If the product's spec file doesn't exist in the bucket.
        S3AccessDeniedError: If credentials don't have read permissions.
    """
```

### README y ADR
- Crear ADR para decisiones arquitectónicas significativas (en `docs/adr/`).
- Mantener README actualizado con commands de setup y uso.

---

## 7. Git y Commits

### Conventional Commits
- `feat:` Nuevas funcionalidades
- `fix:` Corrección de bugs
- `chore:` Mantenimiento, dependencies
- `docs:` Documentación
- `refactor:` Refactoring sin cambio de comportamiento
- `test:` Tests
- Referenciar issue: `feat: [US-01] agregar endpoint /chat`

### Pre-commit Hooks
- Configurar pre-commit para linting y formateo automático antes de commit.
- No hacer commit de código que no pasa lint.

---

## 8. Docker y Entorno

### Docker Best Practices
- Usar imágenes oficiales mínimas (alpine) donde sea posible.
- No correr como root dentro del contenedor.
- Usar salud checks (`HEALTHCHECK`) en Dockerfile.

### Variables de Entorno
- Documentar todas las variables requeridas en `.env.example`.
- Usar valores por defecto sensatos para desarrollo local.

---

## 9. Monitoreo y Observabilidad

### Logging
- Niveles: DEBUG (desarrollo), INFO (operación normal), WARNING, ERROR, CRITICAL.
- Loggear inicio/fin de operaciones largas con duración.
- Incluir contexto estructurado (session_id, user_id, request_id).

### Métricas a Monitorear
- Latencia de endpoints (`/chat` p95, p99).
- Tasa de errores (4xx, 5xx).
- Tasa de escalamiento a humanos.
- Usage de tokens.

---

## Referencias
- PEP 8 — Style Guide for Python Code
- Google Python Style Guide
- FastAPI Best Practices
- SOLID Principles (Robert C. Martin)