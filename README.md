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
│   ├── Dockerfile           # Backend container definition
│   └── requirements.txt     # Python dependencies
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

2. **Build and start the containers:**

```bash
docker compose up -d
```

3. **Verify the service is running:**

```bash
curl http://localhost:8000/health
```

4. **View logs:**

```bash
docker compose logs -f backend
```

5. **Stop the services:**

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

2. **Install dependencies:**

```bash
pip install -r requirements.txt
```

3. **Run the application:**

```bash
uvicorn main:app --reload
```

4. **Access the API:**

The API will be available at `http://localhost:8000`

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
