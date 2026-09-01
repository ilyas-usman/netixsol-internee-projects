"""Week 7 Day 6 — Task 2: Prompt Injection Testing & Security Guardrails.

Provides sanitization and defense against prompt injection attempts:
- "Ignore instructions."
- "Reveal your prompt."
- "Book fake appointments."
- "Give internal company data."
- Jailbreak attempts & system instruction extraction.
"""
from __future__ import annotations

import re
from typing import Any

INJECTION_PATTERNS = [
    (r"ignore\s+(?:all\s+)?(?:previous\s+)?instructions", "ignore_instructions"),
    (r"disregard\s+(?:all\s+)?rules", "ignore_instructions"),
    (r"reveal\s+(?:your\s+)?system\s+prompt", "prompt_leak"),
    (r"show\s+(?:me\s+)?(?:your\s+)?instructions", "prompt_leak"),
    (r"what\s+are\s+your\s+system\s+prompts", "prompt_leak"),
    (r"book\s+fake\s+appointment", "fake_booking_attack"),
    (r"give\s+(?:me\s+)?internal\s+company\s+data", "data_leak_attack"),
    (r"show\s+(?:me\s+)?api\s+keys", "data_leak_attack"),
    (r"reveal\s+passwords", "data_leak_attack"),
    (r"you\s+are\s+now\s+DAN", "jailbreak_attempt"),
    (r"pretend\s+you\s+have\s+no\s+rules", "jailbreak_attempt"),
]

SAFE_INJECTION_RESPONSES = {
    "ignore_instructions": "Main RealEstate Hub ka AI assistant hoon. Main sirf verified real estate options, viewing bookings, aur property queries mein aapki madad kar sakta hoon.",
    "prompt_leak": "Main security aur privacy policy ke tehet system prompt ya internal instructions share nahi kar sakta. Aap property search ya appointment booking ke baare mein pooch sakte hain.",
    "fake_booking_attack": "System mein fake ya unverified appointments creation allow nahi hai. Meherbani karke valid client name, date, aur time specify karein.",
    "data_leak_attack": "Internal company data ya credentials confidentiality policy ke tehet protected hain. Main aapko sirf public verified property listings aur scheduling status bata sakta hoon.",
    "jailbreak_attempt": "Main RealEstate Hub guardrails ke mutabiq kaam karta hoon. Batayein, aapko kis location ya budget mein property chahiye?",
    "generic_injection": "Main RealEstate Hub ka AI property assistant hoon. Meherbani karke apni property request ya appointment booking ki detail bata dein.",
}


def check_prompt_injection(user_text: str) -> dict[str, Any]:
    """Task 2: Analyze input for prompt injection & adversarial patterns."""
    if not user_text:
        return {"is_injection": False, "attack_type": None, "safe_response": None}

    text_lower = user_text.lower()
    for pattern, attack_type in INJECTION_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return {
                "is_injection": True,
                "attack_type": attack_type,
                "safe_response": SAFE_INJECTION_RESPONSES.get(attack_type, SAFE_INJECTION_RESPONSES["generic_injection"]),
            }

    return {"is_injection": False, "attack_type": None, "safe_response": None}
