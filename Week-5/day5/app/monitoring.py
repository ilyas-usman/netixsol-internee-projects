"""
Request logging and lightweight in-process metrics.
See MONITORING_CHECKLIST.md for the full production monitoring policy.
"""
import json
import logging
import time

logging.basicConfig(
    filename="support_agent.log",
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("support_agent")

METRICS = {
    "total_requests": 0,
    "successful_requests": 0,
    "failed_requests": 0,
    "total_latency_seconds": 0.0,
    "total_input_tokens": 0,
    "total_output_tokens": 0,
}


def extract_token_usage(result: dict) -> dict:
    usage = result.get("token_usage")
    if isinstance(usage, dict):
        return {
            "input_tokens": usage.get("input_tokens", usage.get("prompt_tokens", 0)),
            "output_tokens": usage.get("output_tokens", usage.get("completion_tokens", 0)),
            "total_tokens": usage.get("total_tokens", 0),
        }
    return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}


def run_monitored_agent(agent, ticket: dict) -> dict:
    """Invoke the compiled agent while recording latency/tokens/errors."""
    start_time = time.perf_counter()
    logger.info("AGENT_REQUEST | %s", json.dumps(ticket))

    try:
        result = agent.invoke(ticket)
        latency = time.perf_counter() - start_time
        token_usage = extract_token_usage(result)

        METRICS["total_requests"] += 1
        METRICS["successful_requests"] += 1
        METRICS["total_latency_seconds"] += latency
        METRICS["total_input_tokens"] += token_usage["input_tokens"]
        METRICS["total_output_tokens"] += token_usage["output_tokens"]

        logger.info("AGENT_SUCCESS | latency=%.3f | tokens=%s", latency, json.dumps(token_usage))

        result["_monitoring"] = {"latency_seconds": latency, "token_usage": token_usage}
        return result

    except Exception as e:
        latency = time.perf_counter() - start_time
        METRICS["total_requests"] += 1
        METRICS["failed_requests"] += 1
        METRICS["total_latency_seconds"] += latency
        logger.exception("AGENT_ERROR | latency=%.3f | error=%s", latency, str(e))
        raise


def get_metrics() -> dict:
    total = METRICS["total_requests"]
    average_latency = (METRICS["total_latency_seconds"] / total) if total > 0 else 0.0
    return {
        **METRICS,
        "average_latency_seconds": round(average_latency, 3),
        "error_rate": (METRICS["failed_requests"] / total) if total > 0 else 0.0,
    }
