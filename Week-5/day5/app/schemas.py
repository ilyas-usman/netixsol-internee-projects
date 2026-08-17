"""
Request/response contracts for the API.
"""
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class TicketRequest(BaseModel):
    ticket_id: str = Field(..., min_length=1, max_length=100)
    customer_id: str = Field(..., min_length=1, max_length=100)
    ticket_text: str = Field(..., min_length=5, max_length=5000)

    @field_validator("ticket_id", "customer_id", "ticket_text")
    @classmethod
    def strip_whitespace(cls, value: str) -> str:
        return value.strip()


class TicketResponse(BaseModel):
    ticket_id: str
    category: Optional[str] = None
    priority: Optional[str] = None
    requires_human: bool = False
    status: str
    response: Optional[str] = None
    latency_seconds: float
    token_usage: dict = {}
    error: Optional[str] = None
