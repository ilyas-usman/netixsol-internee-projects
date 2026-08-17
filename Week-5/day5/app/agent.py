"""
The production LangGraph agent: state definition, every node, routing
logic, and the compiled graph used by the API layer.
"""
from typing import TypedDict, List, Dict, Any, Optional

from langgraph.graph import StateGraph, START, END

from app.config import llm, EVALUATION_MODE
from app.data import CATEGORIES, PRIORITIES
from app.tools import lookup_customer, search_knowledge_base, get_external_customer_context


# ---------------------------------------------------------------------
# State
# ---------------------------------------------------------------------
class ProductionTicketState(TypedDict, total=False):
    ticket_id: str
    customer_id: str
    ticket_text: str
    category: str
    priority: str
    customer_info: Dict[str, Any]
    knowledge_results: List[str]
    external_context: Dict[str, Any]
    draft_response: str
    final_response: str
    requires_human: bool
    human_feedback: str
    status: str
    errors: List[str]
    retry_count: int
    response_valid: bool
    validation_problems: List[str]
    model_refused: bool


ANALYZER_PROMPT = """
You are a professional customer-support triage analyst.

Analyze the following support ticket.

Ticket:
{ticket_text}

Return ONLY this format:

CATEGORY: <billing|technical|account|refund|general>
PRIORITY: <low|medium|high|critical>

Rules:
- billing: payment, charge, invoice, duplicate charge
- technical: bugs, errors, application failures
- account: login, password, account access
- refund: requests to return money
- general: everything else

Priority:
- critical: security, major financial loss, widespread outage
- high: significant customer impact
- medium: normal customer issue
- low: minor/general request
"""

REFUSAL_PATTERNS = [
    "i can't help", "i cannot help", "i'm unable", "i am unable",
    "i cannot comply", "i can't comply", "i cannot assist", "i'm sorry, but i can't",
]

FORBIDDEN_CLAIMS = [
    "refund has been issued", "refund was processed",
    "your account has been changed", "payment has been reversed",
]


# ---------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------
def analyze_ticket(state: ProductionTicketState) -> dict:
    prompt = ANALYZER_PROMPT.format(ticket_text=state["ticket_text"])
    response = llm.invoke(prompt)
    text = response.content.strip()

    category, priority = "general", "medium"
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("CATEGORY:"):
            category = line.split(":", 1)[1].strip().lower()
        elif line.startswith("PRIORITY:"):
            priority = line.split(":", 1)[1].strip().lower()

    if category not in CATEGORIES:
        category = "general"
    if priority not in PRIORITIES:
        priority = "medium"

    return {"category": category, "priority": priority}


def get_customer_info(state: ProductionTicketState) -> dict:
    return {"customer_info": lookup_customer.invoke(state["customer_id"])}


def external_context_node(state: ProductionTicketState) -> dict:
    result = get_external_customer_context.invoke(state["customer_id"])
    if result.get("success"):
        return {"external_context": result, "errors": state.get("errors", [])}

    errors = state.get("errors", []).copy()
    errors.append(result.get("error", "Unknown external API error."))
    return {"external_context": {}, "errors": errors}


def retrieve_knowledge(state: ProductionTicketState) -> dict:
    return {"knowledge_results": search_knowledge_base.invoke(state["category"])}


def _draft_prompt(state: ProductionTicketState) -> str:
    return f"""
You are a professional customer-support agent.

Customer:
{state.get("customer_info", {})}

External context:
{state.get("external_context", {})}

Ticket:
{state["ticket_text"]}

Category:
{state["category"]}

Priority:
{state["priority"]}

Company knowledge:
{state.get("knowledge_results", [])}

Write a concise and professional response.

Rules:
- Never invent customer information.
- Never promise a refund.
- Never perform financial actions.
- Never claim an action was completed if it was not.
- If human approval is required, say the issue requires review.
"""


def detect_model_refusal(response_text: str) -> bool:
    text = response_text.lower()
    return any(pattern in text for pattern in REFUSAL_PATTERNS)


def safe_draft_response(state: ProductionTicketState) -> dict:
    try:
        response = llm.invoke(_draft_prompt(state))
        draft = response.content

        if detect_model_refusal(draft):
            return {
                "model_refused": True,
                "draft_response": "This request requires additional review by a support representative.",
                "errors": state.get("errors", []) + ["Model refused to generate the requested response."],
            }

        return {"model_refused": False, "draft_response": draft}

    except Exception as e:
        return {
            "model_refused": False,
            "draft_response": (
                "We are currently unable to generate an automated "
                "response. A support representative will review this request."
            ),
            "errors": state.get("errors", []) + [f"Model generation error: {str(e)}"],
        }


def validate_response(state: ProductionTicketState) -> dict:
    response = state.get("draft_response", "").lower()
    problems = []

    if not response.strip():
        problems.append("Response is empty.")

    for phrase in FORBIDDEN_CLAIMS:
        if phrase in response:
            problems.append(f"Potential unauthorized action claim: {phrase}")

    return {"response_valid": len(problems) == 0, "validation_problems": problems}


def correct_response(state: ProductionTicketState) -> dict:
    retry_count = state.get("retry_count", 0)

    if retry_count >= 2:
        return {
            "draft_response": "Your request requires review by a support representative.",
            "retry_count": retry_count,
            "response_valid": True,
        }

    prompt = f"""
Rewrite the following customer-support response.

Original response:
{state["draft_response"]}

Problems:
{state.get("validation_problems", [])}

Rules:
- Do not promise refunds.
- Do not claim financial actions were completed.
- Do not claim account changes were completed.
- Keep the response concise and professional.
"""
    response = llm.invoke(prompt)
    return {"draft_response": response.content, "retry_count": retry_count + 1}


def check_human_review(state: ProductionTicketState) -> dict:
    requires_human = (
        state.get("priority") in ["critical", "high"]
        or state.get("category") == "refund"
    )
    return {"requires_human": requires_human}


def human_review(state: ProductionTicketState) -> dict:
    """
    In the live API this always stops for a real human decision — the
    endpoint returns status='pending_human_review' and a separate
    approval step (e.g. an internal review endpoint or dashboard)
    should call back in with the final decision. EVALUATION_MODE
    auto-approves so batch evaluation runs don't block on input().
    """
    if EVALUATION_MODE:
        return {"final_response": state["draft_response"], "status": "human_approved_evaluation"}

    return {
        "final_response": None,
        "status": "pending_human_review",
    }


def finalize_response(state: ProductionTicketState) -> dict:
    return {"final_response": state["draft_response"], "status": "completed"}


# ---------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------
def route_response_validation(state: ProductionTicketState) -> str:
    if state.get("response_valid", False):
        return "human_check"
    if state.get("retry_count", 0) >= 2:
        return "human_check"
    return "correct_response"


def route_after_human_check(state: ProductionTicketState) -> str:
    return "human_review" if state["requires_human"] else "finalize"


# ---------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------
def build_agent():
    workflow = StateGraph(ProductionTicketState)

    workflow.add_node("analyze", analyze_ticket)
    workflow.add_node("customer_lookup", get_customer_info)
    workflow.add_node("fetch_external_context", external_context_node)
    workflow.add_node("knowledge_retrieval", retrieve_knowledge)
    workflow.add_node("draft", safe_draft_response)
    workflow.add_node("validate_response", validate_response)
    workflow.add_node("correct_response", correct_response)
    workflow.add_node("human_check", check_human_review)
    workflow.add_node("human_review", human_review)
    workflow.add_node("finalize", finalize_response)

    workflow.add_edge(START, "analyze")
    workflow.add_edge("analyze", "customer_lookup")
    workflow.add_edge("customer_lookup", "fetch_external_context")
    workflow.add_edge("fetch_external_context", "knowledge_retrieval")
    workflow.add_edge("knowledge_retrieval", "draft")
    workflow.add_edge("draft", "validate_response")

    workflow.add_conditional_edges(
        "validate_response",
        route_response_validation,
        {"correct_response": "correct_response", "human_check": "human_check"},
    )
    workflow.add_edge("correct_response", "validate_response")

    workflow.add_conditional_edges(
        "human_check",
        route_after_human_check,
        {"human_review": "human_review", "finalize": "finalize"},
    )
    workflow.add_edge("human_review", END)
    workflow.add_edge("finalize", END)

    return workflow.compile()


production_agent = build_agent()
