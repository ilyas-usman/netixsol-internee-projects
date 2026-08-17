"""
Quick sanity check against a running instance of the API.

Usage:
    1. In one terminal:  uvicorn app.main:app --reload
    2. In another:       python scripts/smoke_test.py
"""
import json
import requests

BASE_URL = "http://127.0.0.1:8000"


def main():
    print("Checking /health ...")
    print(json.dumps(requests.get(f"{BASE_URL}/health").json(), indent=2))

    print("\nSubmitting a normal ticket to /tickets ...")
    payload = {
        "ticket_id": "SMOKE-001",
        "customer_id": "C001",
        "ticket_text": "The application keeps crashing when I open it.",
    }
    response = requests.post(f"{BASE_URL}/tickets", json=payload)
    print(response.status_code)
    print(json.dumps(response.json(), indent=2))

    print("\nChecking /metrics ...")
    print(json.dumps(requests.get(f"{BASE_URL}/metrics").json(), indent=2))


if __name__ == "__main__":
    main()
