"""
Week 7 - Day 2 - Task 5: Hallucination Evaluation
====================================================
Runs 20 test questions through the full pipeline and measures:
  - Grounding Rate: % of answers whose factual claims (specifically, any
    NUMBER the answer states - a price, a percentage, a bed count) are
    traceable to something actually present in the retrieved context
    (SQL rows + vector chunks) that was fed to the LLM.
  - Retrieval Accuracy: % of questions where retrieval pulled a source
    document/row actually relevant to the question's topic.

IMPORTANT CHANGE FROM THE FIRST DRAFT: the previous version only checked
whether the answer *sounded like* a refusal ("grounded = not refused").
That's not a real grounding check - it would mark an answer "grounded"
even if it confidently invented a number the LLM made up. This version
does a real (if still heuristic) check: it extracts every number-like
token from the answer and verifies each one appears somewhere in the
context that was actually retrieved for that question. A number in the
answer that ISN'T in the context is flagged as ungrounded.

This is still not perfect - it can't catch a hallucinated CLAIM that
uses a real number (e.g. correct price, wrong property), and prose-only
claims with no numbers ("Bahria Town developers reliable hain") aren't
checked at all. Manual spot-review of the printed answers is still the
final word, especially for the "advisory" and open-ended FAQ categories.
"""

import re
import json

NUMBER_PATTERN = re.compile(r"\d[\d,]*\.?\d*\s*%?")

# Broadened from the first draft - the model's natural refusal phrasing in UrduLish
# varies a lot ("mere paas koi detail nahi hai", "afsos hai", "maazrat chahta hoon", etc.)
# and a narrow keyword list under-detects real refusals, which then falsely drags the
# grounding score down. Still heuristic, not exhaustive - if you see new refusal phrasings
# missed here in a future run, add them.
REFUSAL_MARKERS = [
    "don't have that", "not available", "no information", "no data", "cannot predict",
    "nahi hai", "nahi mili", "nahi mila", "afsos", "maazrat", "maaf kijiye", "maafi",
    "mere paas", "available nahi", "koi detail nahi", "detail nahi", "maloomat nahi",
]


def normalize_number(token):
    """Strips ALL whitespace (including narrow/non-breaking unicode spaces the LLM
    sometimes inserts before a % sign) and trailing % so '20\\u202f%' and '20%' compare equal."""
    return re.sub(r"\s+", "", token).rstrip("%").replace(",", "")


def extract_numbers(text):
    return {normalize_number(n) for n in NUMBER_PATTERN.findall(text) if n.strip(", .")}

EVAL_QUESTIONS = [
    {"id": 1, "q": "3 bed house in Lahore under 2 crore available hai?", "category": "residential", "expects_refusal": False},
    {"id": 2, "q": "DHA Phase 5 mein koi plot for sale hai?", "category": "residential", "expects_refusal": False},
    {"id": 3, "q": "Ye property ka price kya hai?", "category": "residential", "expects_refusal": False},
    {"id": 4, "q": "Kitne bedroom hain is house mein?", "category": "residential", "expects_refusal": False},
    {"id": 5, "q": "Karachi mein rent ke liye flat chahiye, 2 bed", "category": "residential", "expects_refusal": False},
    {"id": 6, "q": "Gulberg mein shop available hai kiraye par?", "category": "commercial", "expects_refusal": False},
    {"id": 7, "q": "Is shop ka frontage kitna hai?", "category": "commercial", "expects_refusal": False},
    {"id": 8, "q": "Office space Islamabad Blue Area mein hai?", "category": "commercial", "expects_refusal": False},
    {"id": 9, "q": "Payment plan ka down payment kitna percent hai?", "category": "faq", "expects_refusal": False},
    {"id": 10, "q": "Installments kitne saal ke liye available hain?", "category": "faq", "expects_refusal": False},
    {"id": 11, "q": "Booking cancel karni ho to refund policy kya hai?", "category": "faq", "expects_refusal": False},
    {"id": 12, "q": "Is society mein park hai ya nahi?", "category": "amenities", "expects_refusal": True},   # no amenities data exists - SHOULD refuse
    {"id": 13, "q": "Nearest school kaunsa hai is property ke?", "category": "amenities", "expects_refusal": True},  # no school data exists
    {"id": 14, "q": "Hospital kitni door hai yahan se?", "category": "amenities", "expects_refusal": True},   # no hospital/distance data exists
    {"id": 15, "q": "Developer ka reputation kaisa hai?", "category": "faq", "expects_refusal": False},
    {"id": 16, "q": "Investment ke liye best area kaunsa hai abhi?", "category": "advisory", "expects_refusal": False},
    {"id": 17, "q": "Property future mein kitni value gain karegi?", "category": "out_of_scope", "expects_refusal": True},
    {"id": 18, "q": "Kal weather kaisa hoga Lahore mein?", "category": "out_of_scope", "expects_refusal": True},
    {"id": 19, "q": "Agent ka phone number kya hai?", "category": "residential", "expects_refusal": True},  # CSV has agent NAME but no phone field - SHOULD refuse
    {"id": 20, "q": "Sabse sasta plot kahan available hai Lahore mein?", "category": "residential", "expects_refusal": False},
]

def check_number_grounding(answer, question, context_text):
    """
    Every number-like token in the answer must appear somewhere in the retrieved
    context OR in the question itself. The question-echo allowance matters: a
    refusal like "2 crore ke under koi house nahi hai" is restating the user's
    own number back to them, not making a new factual claim - that's not a
    hallucination and shouldn't be flagged as one.
    """
    answer_numbers = extract_numbers(answer)
    allowed_numbers = extract_numbers(context_text) | extract_numbers(question)
    ungrounded = answer_numbers - allowed_numbers
    return ungrounded  # empty set = fully grounded on numbers


def run_evaluation(answer_with_context_fn):
    """
    answer_with_context_fn: callable(question_text) -> (answer_text, context_text)
    where context_text is the CONCATENATION of everything actually retrieved
    (SQL formatted rows + vector chunks) and fed to the LLM for that question -
    NOT the answer itself. This is what makes the check meaningful: we're
    verifying the answer's numbers against what the model was actually given,
    not against some external ground truth.
    """
    results = []
    for item in EVAL_QUESTIONS:
        answer, context = answer_with_context_fn(item["q"])
        refused = any(p in answer.lower() for p in REFUSAL_MARKERS)

        if item["expects_refusal"]:
            grounded = refused  # correct behavior IS refusing - answering would be a hallucination risk
            ungrounded_numbers = set()
        else:
            ungrounded_numbers = check_number_grounding(answer, item["q"], context) if not refused else set()
            grounded = refused or len(ungrounded_numbers) == 0

        results.append({
            "id": item["id"], "question": item["q"], "category": item["category"],
            "answer": answer, "refused": refused, "expects_refusal": item["expects_refusal"],
            "ungrounded_numbers": list(ungrounded_numbers), "grounded": grounded,
        })

    grounding_rate = sum(r["grounded"] for r in results) / len(results)
    retrieval_accuracy_note = (
        "Retrieval accuracy needs a manual pass: for each question, check whether the "
        "printed 'context' actually contained the right source doc/row for that topic "
        "(e.g. question 9 about down payment should retrieve payment_plan_*.txt, not "
        "faq_booking.txt). Not auto-scored here since 'correct source' isn't always a "
        "single unambiguous file."
    )
    return {
        "grounding_rate": round(grounding_rate, 3),
        "retrieval_accuracy_note": retrieval_accuracy_note,
        "results": results,
    }


if __name__ == "__main__":
    def dummy_fn(q):
        return ("Sir, is bare mein exact data mere paas nahi hai.", "")
    report = run_evaluation(dummy_fn)
    print(json.dumps(report, indent=2, ensure_ascii=False))