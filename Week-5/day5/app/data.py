"""
Simulated data sources. Swap these for real database calls
(e.g. PostgreSQL) when moving beyond the demo stage.
"""

CATEGORIES = ["billing", "technical", "account", "refund", "general"]
PRIORITIES = ["low", "medium", "high", "critical"]

CUSTOMERS = {
    "C001": {"name": "Ali Khan", "plan": "Premium", "account_status": "active"},
    "C002": {"name": "Sara Ahmed", "plan": "Basic", "account_status": "active"},
    "C003": {"name": "Usman Ilyas", "plan": "Premium", "account_status": "active"},
}

KNOWLEDGE_BASE = [
    {"topic": "billing", "content": "Duplicate charges should be investigated before issuing a refund."},
    {"topic": "refund", "content": "Refund requests above the automatic refund threshold require human approval."},
    {"topic": "technical", "content": "Users should restart the application and verify their internet connection before escalation."},
    {"topic": "account", "content": "Account recovery requires identity verification before sensitive changes."},
]
