"""
ARTE Chatbot Backend
Simple FastAPI server with /health endpoint for CI testing.
"""

from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(title="ARTE Chatbot Backend")


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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
