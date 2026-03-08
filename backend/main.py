from fastapi import FastAPI, Header
from pydantic import BaseModel
from typing import Optional
import uuid

app = FastAPI()

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    session_id: str

@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(request: ChatRequest):
    session_id = request.session_id or str(uuid.uuid4())
    return ChatResponse(
        response=f"Recibido: {request.message}",
        session_id=session_id
    )
