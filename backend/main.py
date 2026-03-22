"""
ARTE Chatbot Backend
FastAPI server with /health and /chat endpoints.
"""
from dotenv import load_dotenv

load_dotenv(override=False)

import uuid
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from rag import (
    DEFAULT_ESCALATION_MESSAGE,
    EscalationDetector,
    default_detector,
)
from backend.app.llm_client import LLMClient, LLMServiceError, ARTE_SYSTEM_PROMPT
from backend.app.auth import verify_api_key
from backend.app.session import session_manager

app = FastAPI(title="ARTE Chatbot Backend")
llm_client = LLMClient()


class ChatRequest(BaseModel):
    """Request model for /chat endpoint."""
    message: str = Field(..., min_length=1)
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    """Response model for /chat endpoint."""
    response: str
    escalate: bool = False
    reason: Optional[str] = None
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
def chat_endpoint(request: ChatRequest, api_key: str = Depends(verify_api_key)):
    """
    Chat endpoint that handles user messages.
    """
    session_id = request.session_id or str(uuid.uuid4())

    # Detect escalation
    escalation_result = default_detector.detect(request.message)

    if escalation_result.escalate:
        # Aún guardamos la consulta en la sesión aunque vayamos a escalar
        session_manager.add_turn(
            session_id=session_id,
            question=request.message,
            answer=DEFAULT_ESCALATION_MESSAGE,
            source_documents=[]
        )
        return ChatResponse(
            response=DEFAULT_ESCALATION_MESSAGE,
            escalate=True,
            reason=escalation_result.reason,
            session_id=session_id,
        )

    try:
        # Obtener contexto de la sesión para mejorar el prompt
        context_string = session_manager.get_context_string(session_id)
        
        llm_response = llm_client.get_llm_response(
            message=request.message,
            session_id=session_id,
            system_prompt=ARTE_SYSTEM_PROMPT,
            context=context_string
        )
        
        # Guardar el turno en la sesión
        session_manager.add_turn(
            session_id=session_id,
            question=request.message,
            answer=llm_response,
            source_documents=[]  # TODO: Obtener esto del RAG cuando esté disponible
        )
    except LLMServiceError as e:
        raise HTTPException(status_code=503, detail=str(e))

    return ChatResponse(
        response=llm_response,
        escalate=False,
        session_id=session_id,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
