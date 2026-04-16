from typing import Optional

from pydantic import BaseModel


class SourceDocument(BaseModel):
    ruta: str
    contenido_relevante: Optional[str] = None
