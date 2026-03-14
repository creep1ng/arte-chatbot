"""
ARTE Chatbot Backend
FastAPI server with /health and /chat endpoints.
"""

from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from rag import (
    DEFAULT_ESCALATION_MESSAGE,
    EscalationDetector,
    default_detector,
)

app = FastAPI(title="ARTE Chatbot Backend")

# Session storage (in-memory for Sprint 1)
# TODO: Replace with PostgreSQL in future sprints
_sessions: dict[str, list[dict[str, Any]]] = {}


class ChatRequest(BaseModel):
    """Request model for /chat endpoint."""

    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    """Response model for /chat endpoint."""

    response: str
    escalate: bool
    reason: str | None = None
    session_id: str


@app.get("/health")
async def health_check() -> JSONResponse:
    """Health check endpoint for CI/CD pipeline."""
    return JSONResponse(
        status_code=200,
        content={
            "status": "healthy",
            "service": "arte-chatbot-backend",
            "version": "1.0.0",
        },
    )


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint."""
    return {"message": "ARTE Chatbot Backend API", "docs": "/docs"}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Chat endpoint that handles user messages.

    Currently implements basic escalation detection via keywords.
    RAG pipeline integration coming in future sprints.
    """
    # Generate session_id if not provided
    session_id = request.session_id or "default"

    # Initialize session if needed
    if session_id not in _sessions:
        _sessions[session_id] = []

    # Detect escalation using the RAG module
    escalation_result = default_detector.detect(request.message)

    if escalation_result.escalate:
        # Return escalation response
        return ChatResponse(
            response=DEFAULT_ESCALATION_MESSAGE,
            escalate=True,
            reason=escalation_result.reason,
            session_id=session_id,
        )

    # TODO: Implement full RAG pipeline here
    # For now, return a placeholder response
    return ChatResponse(
        response="Gracias por tu mensaje. Estoy configurando mi base de conocimientos. ¿Tienes alguna pregunta sobre paneles solares o inversores?",
        escalate=False,
        session_id=session_id,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
