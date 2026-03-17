"""
ARTE Chatbot Backend
Simple FastAPI server with /health endpoint for CI testing.
"""

import uuid
from datetime import datetime
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

app = FastAPI(title="ARTE Chatbot Backend")


class ChatRequest(BaseModel):
    """Request model for /chat endpoint."""
    message: str = Field(..., description="User message")
    session_id: str | None = Field(default=None, description="Session identifier")


class ChatResponse(BaseModel):
    """Response model for /chat endpoint."""
    response: str
    session_id: str
    latency_ms: float
    source_documents: list[dict[str, Any]] | None = None
    escalated: bool = False
    timestamp: str


@app.get("/health")
async def health_check():
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
async def root():
    """Root endpoint."""
    return {"message": "ARTE Chatbot Backend API", "docs": "/docs"}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Chat endpoint - skeleton implementation for RAG pipeline.
    
    This is a basic implementation that returns a placeholder response.
    The full RAG implementation will be added in future iterations.
    """
    import time
    start_time = time.perf_counter()
    
    # Generate session_id if not provided
    session_id = request.session_id or str(uuid.uuid4())
    
    # Skeleton response - in production, this would call the RAG pipeline
    response_text = (
        f"Gracias por tu consulta sobre energía solar. "
        f"Esta es una respuesta automática en modo skeleton. "
        f"Tu mensaje fue: '{request.message[:50]}...' "
        f"El sistema RAG procesará tu consulta pronto."
    )
    
    latency_ms = (time.perf_counter() - start_time) * 1000
    
    return ChatResponse(
        response=response_text,
        session_id=session_id,
        latency_ms=latency_ms,
        source_documents=[],
        escalated=False,
        timestamp=datetime.utcnow().isoformat() + "Z",
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
