"""Six objection categories with grounded response strategies and a comprehensive test set."""
from __future__ import annotations
import json, re
from day3_config import GROQ_MODEL

CATEGORIES = {
    "price": {
        "keywords": [
            "mehnga", "mehngi", "expensive", "price high", "budget se bahar", "costly", "high price", "cost zyada", "too high",
            "sasta", "suit nahi",
            "مہنگا", "مہنگی", "قیمت زیادہ", "قیمت", "بجٹ سے باہر", "سستا", "کم قیمت", "زیادہ قیمت", "مہنگے"
        ],
        "strategy": "Acknowledge budget concern; use SQL to find cheaper matching options before making any claim."
    },
    "trust": {
        "keywords": [
            "trust", "bharosa", "scam", "fraud", "reliable", "genuine", "fake", "authentic", "verification",
            "بھروسہ", "اعتماد", "اسکام", "فراڈ", "ساکھ", "لیگل", "جینوئن", "ریلائبل", "جعلی", "تصدیق"
        ],
        "strategy": "Use retrieved developer/brochure facts only; if evidence is missing, say so and offer a human verification call."
    },
    "location": {
        "keywords": [
            "location", "door", "area acha nahi", "traffic", "access", "remote", "reach", "too far",
            "لوکیشن", "دور", "علاقہ", "علاقہ اچھا نہیں", "ٹریفک", "پہنچ", "بہت دور", "راستہ"
        ],
        "strategy": "Use stored location/listing facts; do not invent commute times or nearby facilities."
    },
    "investment": {
        "keywords": [
            "investment", "return", "roi", "profit", "appreciation", "future value", "yield", "resale",
            "سرمایہ کاری", "منافع", "انویسٹمنٹ", "ریٹرن", "ار او آئی", "فیوچر", "قدر میں اضافہ", "انویسٹ"
        ],
        "strategy": "Separate factual area/project information from predictions; never guarantee returns."
    },
    "builder": {
        "keywords": [
            "builder", "developer", "construction", "quality", "project history", "track record", "reputation",
            "بلڈر", "ڈویلپر", "تعمیر", "معیار", "ٹریک ریکارڈ", "تعمیراتی", "سابقع پراجیکٹس"
        ],
        "strategy": "Ground claims in developer notes/brochure; escalate if verification is requested but absent."
    },
    "maintenance": {
        "keywords": [
            "maintenance", "maintainance", "charges", "service charges", "monthly fee", "expense", "utilities cost",
            "مینٹیننس", "چارجز", "سروس چارجز", "ماہانہ فیس", "اخراجات", "مینٹی نینس", "ماہانہ اخراجات"
        ],
        "strategy": "Use verified commercial/property data or RAG documents; never invent a fee."
    },
}

def normalize_text(text: str) -> str:
    if not text:
        return ""
    # Strip Arabic/Urdu diacritics (tashdeed, fatha, damma, kasra, khari zabar, etc.)
    text = re.sub(r'[\u064B-\u065F\u0670]', '', text)
    # Standardize Allah spelling variations
    text = text.replace("الله", "اللہ")
    text = " ".join(text.lower().split())
    return text

def detect_objection(text: str) -> str:
    s = normalize_text(text)

    # Interrogative words for distance/amenity questions (e.g. "hospital kitna door hai", "school kitne door hain")
    # Must NOT trigger location objection when the user is asking a factual question
    interrogative_words = [
        "kitna", "kitni", "kitne", "kaunsa", "kaunsi", "kya", "how far", "what distance", "which",
        "کتنا", "کتنی", "کتنے", "کونسا", "کونسی", "کون", "کیا"
    ]
    facility_words = ["school", "hospital", "amenity", "amenities", "utility", "utilities", "اسکول", "سکول", "ہاسپٹل", "ہسپتال", "یوٹیلٹیز"]
    
    # FIX: previously required an EXACT "door"/"distance" word alongside a
    # facility word (school/hospital/utilities/amenities), so a one-letter
    # typo like "distnace" (real transcript: "school distnace how much
    # far?") defeated the guard entirely, and the query fell through to
    # location's own bare "far"/"door" keywords — misclassifying an
    # innocent amenity question as a location objection, which then
    # steered the LLM into a location-reassurance answer instead of
    # actually answering the amenity question. Asking about a school,
    # hospital, or utilities at all is virtually always informational,
    # not a location complaint, so the facility word alone is enough.
    is_question = any(w in s for w in interrogative_words) or any(f in s for f in facility_words)

    if any(k in s for k in CATEGORIES["builder"]["keywords"]):
        return "builder"
    for cat, spec in CATEGORIES.items():
        if cat == "builder":
            continue
        if cat == "location" and is_question:
            continue
        if any(k in s for k in spec["keywords"]):
            return cat
    return "none"

def update_objection_counts(objections, category):
    if category == "none": return objections
    data=dict(objections)
    item=data.get(category, {"count":0,"unresolved":0})
    item["count"] += 1
    item["unresolved"] += 1
    data[category]=item
    return data

def mark_resolved(objections, category):
    data=dict(objections)
    if category in data: data[category]["unresolved"]=0
    return data

def should_escalate(objections, category):
    return category != "none" and objections.get(category,{}).get("unresolved",0) >= 2

def strategy(category):
    return CATEGORIES.get(category,{}).get("strategy","Answer normally from grounded context.")

def build_test_set():
    samples = {
        "price": [
            "Price bohat mehnga hai.", "Budget se bahar hai.", "Iski cost zyada hai.", "Thora sasta option hai?", "Mujhe ye price suit nahi karta.",
            "قیمت بہت زیادہ ہے", "بجٹ سے باہر ہے", "یہ بہت مہنگا ہے", "یہ قیمت مناسب نہیں", "کوئی سستا اپشن ہے؟"
        ],
        "trust": [
            "Is company par bharosa nahi hota.", "Ye scam to nahi?", "Yeh deal genuine lagta hai?", "Project genuine hai?", "Mujhe trust issue hai.",
            "اس کمپنی پر بھروسہ نہیں ہوتا۔", "یہ فراڈ تو نہیں؟", "یہ ڈیل جینوئن لگتی ہے؟", "پراجیکٹ جینوئن ہے؟", "مجھے اعتمادی مسئلہ ہے"
        ],
        "location": [
            "Location door hai.", "Area acha nahi lag raha.", "Yahan traffic bohat hota hai?", "Location meri requirement ke mutabiq nahi.", "Access ka concern hai.",
            "لوکیشن بہت دور ہے", "علاقہ اچھا نہیں ہے", "یہاں ٹریفک کا مسئلہ ہے", "لوکیشن مناسب نہیں", "بہت دور ہے"
        ],
        "investment": [
            "Investment ke liye ye kaisa hai?", "Return kitna milega?", "ROI kya hoga?", "Future appreciation guarantee hai?", "Profit ka chance kitna hai?",
            "سرمایہ کاری کے لیے یہ کیسا ہے؟", "کتنا منافع ملے گا؟", "ار او آئی کیا ہوگا؟", "فیوچر ویلیو کا کیا حساب ہے؟", "منافع کا کتنا چانس ہے؟"
        ],
        "builder": [
            "Builder ka track record?", "Developer ki construction quality?", "Builder reliable hai?", "Is developer ne pehle kya banaya?", "Builder ke projects kaise hain?",
            "بلڈر کا ٹریک ریکارڈ کیا ہے؟", "تعمیراتی معیار کیسا ہے؟", "ڈویلپر پر کتنا اعتماد ہے؟", "ڈویلپر نے پہلے کیا بنایا؟", "بلڈر کے پراجیکٹس کیسے ہیں؟"
        ],
        "maintenance": [
            "Maintenance charges zyada hain?", "Monthly maintenance kitni hai?", "Service charges kya hain?", "Maintenance ka cost afford nahi hoga.", "Monthly fee kitni lagegi?",
            "مینٹیننس چارجز زیادہ ہیں", "ماہانہ فیس کتنی ہے؟", "سروس چارجز کیا ہیں؟", "مینٹی نینس افورڈ نہیں ہوگی", "ماہانہ اخراجات کتنے ہیں؟"
        ],
    }
    out=[]
    for cat, qs in samples.items():
        for i,q in enumerate(qs,1):
            out.append({"id":f"{cat}-{i}","category":cat,"text":q,"expected_strategy":CATEGORIES[cat]["strategy"]})
    return out

OBJECTION_TEST_SET=build_test_set()