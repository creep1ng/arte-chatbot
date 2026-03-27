# arte-chatbot

## CI Integration Test Configuration

Required secrets:
- `OPENAI_API_KEY` — API key for the OpenAI LLM provider
- `CHAT_API_KEY` — API key for authenticating with the /chat endpoint

Add these secrets to GitHub Actions Secrets.

Example usage in workflow:

```yaml
env:
  OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
  CHAT_API_KEY: ${{ secrets.CHAT_API_KEY }}
```

Ensure the secrets are set in your repository settings under GitHub > Settings > Secrets and variables > Actions.
# ARTE Chatbot

[![CI](https://github.com/creep1ng/arte-chatbot/actions/workflows/ci.yml/badge.svg)](https://github.com/creep1ng/arte-chatbot/actions/workflows/ci.yml)
[![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)

ARTE Chatbot is a FastAPI-based backend service for an intelligent chatbot with RAG (Retrieval-Augmented Generation) capabilities.

## 📁 Project Structure

```
arte-chatbot/
├── .github/
│   └── workflows/
│       └── ci.yml           # GitHub Actions CI pipeline
├── backend/
│   ├── __init__.py
│   ├── main.py              # FastAPI application
│   ├── config/              # Configuration files (catalog_index.json)
│   ├── Dockerfile           # Backend container definition
│   └── requirements.txt     # Python dependencies
├── scripts/
│   └── generate_index.py    # Script to generate catalog index from PDFs
├── rag/
│   ├── __init__.py
│   └── ...                  # RAG module components
├── evaluation/
│   ├── __init__.py
│   └── ...                  # Evaluation module
├── docs/
│   ├── adr/                 # Architecture Decision Records
│   └── ...                  # Documentation
├── docker-compose.yml       # Docker Compose configuration
└── README.md
```

## 📦 Data Infrastructure

La infraestructura de datos del proyecto utiliza **Amazon S3** para el almacenamiento de fichas técnicas de productos, garantizando acceso estandarizado, de alta disponibilidad y consistente entre todos los entornos (desarrollo local, CI, cloud).

Consultar [ADR-002](docs/adr/002.md) para detalles completos de la decisión.

### Estructura del Bucket S3

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

### Variables de Entorno Requeridas

| Variable | Descripción |
|----------|-------------|
| `AWS_ACCESS_KEY_ID` | Identificador de clave de acceso AWS |
| `AWS_SECRET_ACCESS_KEY` | Clave de acceso secreta AWS |
| `AWS_BUCKET_NAME` | Nombre del bucket S3 (`arte-chatbot-data`) |

### Flujo de Datos

```mermaid
graph TD
    Client[Cliente WhatsApp] -->|POST /chat| API[FastAPI Backend]
    API -->|1. Consulta índice| S3[/index/catalog_index.json]
    API -->|2. Descarga PDF| S3[/raw/paneles/modelo_x.pdf]
    API -->|3. File Input| LLM[OpenAI LLM]
    LLM -->|4. Respuesta| API
    API -->|5. Respuesta| Client
```

### Instrucciones para Colaboradores

1. **Obtener credenciales AWS**: Solicitar acceso al administrador del proyecto
2. **Configurar credenciales locales**: Añadir al archivo `.env` las variables listadas arriba
3. **Verificar acceso**: Ejecutar `aws s3 ls s3://arte-chatbot-data/raw/paneles/` para confirmar conectividad
4. **No almacenar credenciales en el repositorio**: Usar `.env` (ya en `.gitignore`)

Para más información sobre File Inputs como método de retrieval, consultar [ADR-003](docs/adr/003.md).

---

## 🚀 Local Setup

### Prerequisites

- **Docker** (version 20.10+)
- **Docker Compose** (version 2.0+)
- **Python 3.11+** (optional, for local development without Docker)

### Option 1: Using Docker Compose (Recommended)

1. **Clone the repository:**

```bash
git clone https://github.com/creep1ng/arte-chatbot.git
cd arte-chatbot
```

2. **Set up environment variables:**

Copy the example environment file and fill in your API keys:

```bash
cp .env.example .env
```

3. **Build and start the containers:**

```bash
docker compose up -d
```

4. **Verify the service is running:**

```bash
curl http://localhost:8000/health
```

5. **View logs:**

```bash
docker compose logs -f backend
```

6. **Stop the services:**

```bash
docker compose down
```

### Option 2: Local Development (Without Docker)

1. **Create a virtual environment:**

```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. **Set up environment variables:**

Copy the example environment file and fill in your API keys:

```bash
cp ../.env.example .env
echo CHAT_API_KEY=$(openssl rand -base64 32) >> .env
```

3. **Install dependencies:**

```bash
pip install -r requirements.txt
```

4. **Run the application:**

```bash
uvicorn main:app --reload
```

5. **Access the API:**

The API will be available at `http://localhost:8000`

## 📂 Catalog Indexing

The catalog index is used to inject product information into the chatbot prompts. The system reads PDF files from an S3 bucket and generates a JSON index with metadata (category, brand, model).

### Generating the Index

```bash
# Install dependencies (boto3 required)
pip install boto3

# Generate index from S3 bucket (default)
python scripts/generate_index.py

# Generate index from local directory
python scripts/generate_index.py --source-dir ./local_pdfs

# Dry run (show what would be indexed without writing)
python scripts/generate_index.py --dry-run

# Custom bucket and prefix
python scripts/generate_index.py --bucket my-bucket --prefix my-folder/ --output custom_index.json
```

### Index Output Format

The generated `catalog_index.json` has the following structure:

```json
[
  {
    "nombre": "Panel Solar 500W",
    "categoria": "panel",
    "ruta_s3": "s3://arte-chatbot-data/raw/panel-solar-500w.pdf"
  }
]
```

### Filename Convention

PDF files in the S3 bucket must follow the naming convention:

```
{categoria}-{marca}-{modelo}.pdf
```

Example: `panel-solar-500w.pdf` → categoria: `panel`, marca: `solar`, modelo: `500w`

## 📡 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Root endpoint, returns API info |
| `/health` | GET | Health check endpoint for CI/CD |
| `/docs` | GET | OpenAPI/Swagger documentation |
| `/redoc` | GET | ReDoc documentation |

### Health Check Response

```json
{
  "status": "healthy",
  "service": "arte-chatbot-backend",
  "version": "1.0.0"
}
```

## 🔄 CI/CD

The project uses **GitHub Actions** for continuous integration. The CI pipeline runs on every push and pull request.

### Pipeline Stages

1. **Lint** - Code quality checks using Ruff
2. **Build** - Docker image build
3. **Test** - Health endpoint verification
4. **Cleanup** - Container cleanup

### Running CI Locally

```bash
# Run linting
ruff check backend/

# Build Docker image
docker compose build

# Run health check
docker compose up -d backend
curl http://localhost:8000/health
```

## 🧪 Testing

This project uses **pytest** for testing. Tests are organized in `tests/` directories within each module.

### Running Tests

```bash
# Run all tests
pytest

# Run tests with verbose output
pytest -v

# Run tests with coverage
pytest --cov=backend --cov=rag

# Run tests for a specific module
pytest backend/tests/
```

### Test Structure

```
backend/tests/
├── __init__.py
├── test_api.py
└── test_models.py

rag/tests/
├── __init__.py
├── test_retriever.py
└── test_generator.py
```

### Running Tests with Docker

```bash
# Run tests inside the backend container
docker compose exec backend pytest

# Run tests with coverage
docker compose exec backend pytest --cov=backend --cov-report=term-missing
```

## � Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

Please ensure all tests pass before submitting a PR.

## 📄 License

This project is licensed under the terms included in the [LICENSE](LICENSE) file.
