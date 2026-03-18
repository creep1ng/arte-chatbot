# ARTE Chatbot Backend Dockerfile
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install UV from ghcr.io/astral-sh/uv:0.10.7
COPY --from=ghcr.io/astral-sh/uv:0.10.7 /uv /uvx /bin/

# Copy project files for dependency resolution
COPY pyproject.toml uv.lock ./

# Create virtual environment and install dependencies using uv sync
RUN uv venv && \
    uv sync --frozen --no-install-project --group dev --group lint --group typecheck

# Add venv to PATH
ENV PATH="/app/.venv/bin:$PATH"

# Copy application code
COPY backend/ ./backend/
COPY rag/ ./rag/

# Expose the application port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
