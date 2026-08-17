"""
FastAPI entrypoint for the Support Ticket Triage Agent.

Run with:
    uvicorn app.main:app --reload
"""
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.agent import production_agent
from app.config import PROJECT_NAME, FRAMEWORK, MODEL_PROVIDER
from app.monitoring import logger, run_monitored_agent, get_metrics
from app.schemas import TicketRequest, TicketResponse

app = FastAPI(
    title=PROJECT_NAME,
    description="Production-oriented LangGraph support-ticket triage API.",
    version="1.0.0",
)


def format_api_result(result: dict) -> dict:
    monitoring = result.get("_monitoring", {})
    return {
        "ticket_id": result.get("ticket_id"),
        "category": result.get("category"),
        "priority": result.get("priority"),
        "requires_human": result.get("requires_human", False),
        "status": result.get("status", "unknown"),
        "response": result.get("final_response"),
        "latency_seconds": round(monitoring.get("latency_seconds", 0.0), 3),
        "token_usage": monitoring.get("token_usage", {}),
        "error": None,
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": PROJECT_NAME,
        "framework": FRAMEWORK,
        "model_provider": MODEL_PROVIDER,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/metrics")
def metrics():
    return get_metrics()


@app.post("/tickets", response_model=TicketResponse)
def process_ticket(request: TicketRequest):
    logger.info("API_REQUEST | ticket_id=%s | customer_id=%s", request.ticket_id, request.customer_id)

    ticket = {
        "ticket_id": request.ticket_id,
        "customer_id": request.customer_id,
        "ticket_text": request.ticket_text,
    }

    try:
        result = run_monitored_agent(production_agent, ticket)
        response = format_api_result(result)
        logger.info("API_RESPONSE | ticket_id=%s | status=%s", request.ticket_id, response["status"])
        return response

    except Exception as e:
        logger.exception("API_ERROR | ticket_id=%s | error=%s", request.ticket_id, str(e))
        raise HTTPException(
            status_code=500,
            detail={"error": "Agent processing failed.", "ticket_id": request.ticket_id},
        )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    logger.warning("VALIDATION_ERROR | %s", str(exc))
    return JSONResponse(
        status_code=422,
        content={"error": "Invalid request.", "details": exc.errors()},
    )
