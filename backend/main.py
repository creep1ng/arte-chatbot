from dotenv import load_dotenv

load_dotenv(override=False)

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
import uuid

from backend.app.llm_client import LLMClient, LLMServiceError, ARTE_SYSTEM_PROMPT

app = FastAPI()
llm_client = LLMClient()


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    session_id: str


@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(request: ChatRequest):
    session_id = request.session_id or str(uuid.uuid4())

    try:
        llm_response = llm_client.get_llm_response(
            message=request.message,
            session_id=session_id,
            system_prompt=ARTE_SYSTEM_PROMPT,
        )
    except LLMServiceError as e:
        raise HTTPException(status_code=503, detail=str(e))

    return ChatResponse(
        response=llm_response,
        session_id=session_id,
    )
