# AGENTS.md — Arte Chatbot Agent Instructions

## Project Overview

Arte Chatbot es un sistema de respuesta automática diseñado para automatizar la atención al cliente de primer nivel en Arte Soluciones Energéticas, una empresa B2B de energía solar. El proyecto utiliza **File Inputs** (subida directa de PDFs al LLM) en lugar de RAG tradicional con base de datos vectorial. El sistema está diseñado para consultar fichas técnicas de productos (paneles, inversores, etc.) mediante Tool Calling, responder consultas especializadas, detectar intenciones y escalar conversaciones complejas a agentes humanos.

Consultar [ADR-002](docs/adr/002.md) y [ADR-003](docs/adr/003.md) para detalles completos de la arquitectura de datos.

## Repository Structure

- `backend/` – API REST desarrollada con FastAPI que expone el endpoint principal del chatbot y gestiona las sesiones.
- `rag/` – Módulo que encapsula la lógica de retrieval via File Inputs (no usa embeddings ni vector store).
- `evaluation/` – Scripts y harnesses automatizados para medir latencia, precisión técnica y tasas de escalamiento.
- `docs/` – Documentación técnica en Markdown, incluyendo Architecture Decision Records (ADR).
- `docker-compose.yml` – Orquestador principal que levanta los servicios requeridos (API) en entornos locales.

## Build & Development Commands

```bash
# Levantar el entorno de desarrollo completo
docker compose up -d

# Reconstruir imágenes tras cambios en dependencias
docker compose up -d --build

# Ver logs del backend en tiempo real
docker compose logs -f backend

# Entrar al contenedor del backend
docker compose exec -it backend bash

# Tests de salud
curl http://localhost:8000/health
```

## Code Style & Conventions

### General
- **Arquitectura de Software**: Aplicar principios **SOLID**. Cada módulo debe tener responsabilidades únicas, depender de abstracciones mediante interfaces/protocolos de Python, y estar cerrado a modificación pero abierto a extensión.
- **Gestor de Dependencias**: Usar **`uv`** (no pip, poetry o conda).
- **Tipado**: Type Hints obligatorios en todas las funciones y métodos.
- **Commits**: Convenciones semánticas (`feat:`, `fix:`, `chore:`, `docs:`), referenciando número de issue (e.g., `feat: [US-01] agregar endpoint /chat`).

### Python
- **Imports**: Organizar en tres bloques separados por líneas en blanco: (1) stdlib, (2)第三方, (3) local/app imports. Dentro de cada bloque, orden alfabético.
- **Formatting**: 88 caracteres por línea (Black default). Indentación con 4 espacios.
- **Naming**:
  - `snake_case` para funciones, métodos, variables y argumentos
  - `PascalCase` para clases y tipos
  - `SCREAMING_SNAKE_CASE` para constantes
  - Prefijos `is_`, `has_`, `can_` para booleanos
- **Types**: Usar `typing` para tipos complejos (`Optional[str]`, `List[int]`, `Dict[str, Any]`). Para alias simples, definir en mayúsculas.
- **Docstrings**: Usar Google style con tipo de parámetros y valores de retorno.
- **Error Handling**: Nunca usar `except:` sin especificar excepciones. Preferir excepciones custom cuando el error tiene semántica de negocio.
- **Async**: Preferir `async/await` para operaciones I/O-bound (HTTP, S3, etc.).

### FastAPI Specific
- Usar `Annotated` con `Depends()` para dependency injection
- Validar DTOs con Pydantic v2
- Usar `async` para todos los endpoints salvo que haya razón justificada

## Architecture Notes

### Data Infrastructure (S3)

Todas las fichas técnicas se almacenan en **Amazon S3**. Esta decisión garantiza acceso estandarizado, alta disponibilidad y consistente entre todos los entornos.

**Estructura del bucket:**
```
arte-chatbot-data/
├── raw/
│   ├── paneles/
│   ├── inversores/
│   ├── controladores/
│   └── baterias/
└── index/
    └── catalog_index.json
```

**Variables de entorno requeridas:**
- `AWS_ACCESS_KEY_ID` — Identificador de clave de acceso AWS
- `AWS_SECRET_ACCESS_KEY` — Clave de acceso secreta AWS
- `AWS_BUCKET_NAME` — Nombre del bucket (`arte-chatbot-data`)

### Flujo de Datos con File Inputs

```mermaid
graph TD
    Client[WhatsApp/User] -->|POST /chat| API[FastAPI Backend]
    API -->|1. Consulta índice| S3[/index/catalog_index.json]
    API -->|2. Descarga PDF| S3[/raw/paneles/modelo_x.pdf]
    API -->|3. File Input + Tool Calling| LLM[OpenAI/Anthropic LLM]
    LLM -->|4. Respuesta| API
    API -->|5. Respuesta| Client
```

**Data Flow**: Las consultas entran al backend (FastAPI), que preserva el contexto de sesión. El chatbot utiliza Tool Calling para invocar `leer_ficha_tecnica(ruta)`, que descarga el PDF desde S3 y lo adjunta como File Input al LLM. El LLM responde utilizando el contenido completo del documento.

## Testing Strategy

- **Framework**: pytest
- **Organización**: Tests en carpetas `tests/` dentro de cada módulo (`backend/tests/`, `rag/tests/`).
- **Cobertura**: Cada feature nueva debe incluir tests unitarios. Features con componentes externos requieren tests de integración.
- **CI**: GitHub Actions ejecuta linting, tests con pytest y health checks en cada PR.

### Comandos de Testing

```bash
# Ejecutar todos los tests
pytest

# Ejecutar tests con coverage
pytest --cov=backend --cov=rag

# Ejecutar un archivo de test específico
pytest backend/tests/test_api.py

# Ejecutar una función de test específica
pytest backend/tests/test_api.py::test_health_check

# Ejecutar tests que coincidan con un patrón (markers)
pytest -k "test_health"

# Ejecutar tests dentro del contenedor
docker compose exec backend pytest

# Ejecutar un solo test dentro del contenedor
docker compose exec backend pytest backend/tests/test_api.py::test_health_check
```

> **WARNING**: Los tests requieren un archivo `.env` (o variables de entorno exportadas) con al menos `OPENAI_API_KEY` y `CHAT_API_KEY` configuradas. `backend.main` instancia `FileInputsClient()` a nivel de módulo, lo cual falla si `OPENAI_API_KEY` no está presente durante la colección de tests. Copiar `.env.example` a `.env` antes de ejecutar `pytest`.

## Security & Compliance

- **Manejo de Secretos**: Ninguna llave de API (OpenAI, Anthropic, AWS, etc.) debe ser subida al repositorio. Usar `.env` (ya en `.gitignore`).
- **Credenciales AWS**: Gestionar exclusivamente via variables de entorno. No hardcodear nunca.

## Extensibility Hooks

- **Interfaces de Retrieval**: El código en `rag/` debe definir clases abstractas para facilitar el intercambio del método de retrieval (ej. `BaseFileLoader`, `BaseDocumentParser`) sin alterar el backend.
- **Variables de Entorno**: `LLM_PROVIDER`, `AWS_BUCKET_NAME`, `LOG_LEVEL`.
- **Tool Calling**: El sistema está diseñado para que nuevas herramientas puedan añadirse sin modificar la lógica existente.

## Further Reading

- [ADR-001: Arquitectura inicial y orquestación de servicios](docs/adr/001.md)
- [ADR-002: Infraestructura de datos con S3](docs/adr/002.md)
- [ADR-003: File Inputs como método de retrieval](docs/adr/003.md)
- [Plantilla de ADR](docs/adr/template.md)
