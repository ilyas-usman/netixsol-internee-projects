"""
Tools available to the agent: internal lookups and one external API call.
"""
import requests
from langchain_core.tools import tool

from app.data import CUSTOMERS, KNOWLEDGE_BASE


@tool
def search_knowledge_base(topic: str) -> list:
    """Search the support knowledge base by topic."""
    return [item["content"] for item in KNOWLEDGE_BASE if item["topic"] == topic.lower()]


@tool
def lookup_customer(customer_id: str) -> dict:
    """Retrieve customer information using a customer ID."""
    customer = CUSTOMERS.get(customer_id)
    if not customer:
        return {"found": False, "message": "Customer not found."}
    return {"found": True, "customer": customer}


@tool
def get_external_customer_context(customer_id: str) -> dict:
    """Retrieve external customer-related context from a public API."""
    try:
        response = requests.get("https://jsonplaceholder.typicode.com/users", timeout=5)
        response.raise_for_status()
        users = response.json()

        index = sum(ord(char) for char in customer_id) % len(users)
        user = users[index]

        return {
            "success": True,
            "source": "JSONPlaceholder",
            "context": {
                "name": user.get("name"),
                "company": user.get("company", {}).get("name"),
                "city": user.get("address", {}).get("city"),
            },
        }
    except requests.Timeout:
        return {"success": False, "error": "External customer service timed out."}
    except requests.RequestException as e:
        return {"success": False, "error": f"External API error: {str(e)}"}
