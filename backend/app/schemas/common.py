"""通用响应 schema"""
from typing import Any, Optional
from pydantic import BaseModel


class ApiResponse(BaseModel):
    code: int = 0
    msg: str = "ok"
    data: Optional[Any] = None


class ChatRequest(BaseModel):
    prompt: str
    model: Optional[str] = None
    temperature: Optional[float] = 0.7


class AgentRunRequest(BaseModel):
    topic: str
    data_file: Optional[str] = None
    model: Optional[str] = None
