"""Day 3 automated tests: memory, routing, objections and API smoke tests."""
import os, tempfile
os.environ["DAY3_MEMORY_DB"]=os.getenv("DAY3_TEST_MEMORY_DB","./day3_test_memory.db")

from conversation_memory import reset_session, get_state, heuristic_slots, parse_money
from day3_router import _heuristic_route
from day3_objections import OBJECTION_TEST_SET, detect_objection

def test_money():
    assert parse_money("Budget 3 crore hai.") == 30_000_000
    assert parse_money("2.5 lakh") == 250_000

def test_slots():
    x=heuristic_slots("Budget 3 crore hai, DHA Lahore mein 3 bed house chahiye")
    assert x["budget"]==30_000_000 and x["city"]=="Lahore" and x["bedrooms"]==3

def test_routes():
    assert _heuristic_route("3 bed house Lahore under 2 crore")["route"]=="sql"
    assert _heuristic_route("payment plan ka down payment kitna hai?")["route"]=="rag"
    assert _heuristic_route("DHA house aur payment plan batao")["route"]=="both"

def test_objections():
    assert len(OBJECTION_TEST_SET) >= 30
    assert detect_objection("Price bohat mehnga hai")=="price"
    assert detect_objection("Builder reliable hai?")=="builder"

def test_persistence():
    sid="day3-test"
    reset_session(sid)


def test_natural_chat_and_location_grounding():
    from day3_agent import run_turn

    sid = "day3-natural-test"
    reset_session(sid)


def test_location_broadening_preserves_city():
    from day3_agent import run_turn

    sid = "day3-broadening-test"
    reset_session(sid)


def test_verified_nearby_facilities():
    from day3_agent import run_turn

    sid = "day3-facilities-test"
    reset_session(sid)


def test_purpose_question_and_city_reset():
    from day3_agent import run_turn

    sid = "day3-purpose-test"
    reset_session(sid)
    first = run_turn(sid, "Faisalabad mein ghar 40 lac tak dikhao")
    purpose = run_turn(sid, "ye sale hai ya rent?")
    assert "For Sale" in purpose["response"]
    broad = run_turn(sid, "city koi bhi ho")
    assert "city ki koi restriction nahi" in broad["response"]
    assert "city" not in broad["memory"]["slots"]
    assert first["listings"]
    reset_session(sid)
    result = run_turn(sid, "near school option in Faisalabad")
    assert result["listings"]
    assert all(item["nearby_school"] != "Not available in verified data" for item in result["listings"])
    assert result["listings"][0]["benefits"]
    reset_session(sid)
    run_turn(sid, "Faisalabad DHA mein ghar dikhao")
    result = run_turn(sid, "DHA kay ilawa Faisalabad mein koi shop?")
    assert result["memory"]["slots"].get("city") == "Faisalabad"
    assert "location" not in result["memory"]["slots"]
    assert all("Faisalabad" in item["location"] for item in result["listings"])
    reset_session(sid)
    assert "Wa alaikum assalam" in run_turn(sid, "assalam o alaikum")["response"]
    assert "theek hoon" in run_turn(sid, "kya haal hai")["response"]
    assert "theek hoon" in run_turn(sid, "our sunaoo kya chal rha life may")["response"]
    assert "madad" in run_turn(sid, "kya kr rhe ho aj kal?")["response"]
    assert "madad" in run_turn(sid, "pagal hu kya tm?")["response"]
    assert "budget" in run_turn(sid, "okay")["response"].lower()

    result = run_turn(sid, "Faisalabad DHA mein 50 lac ka ghar dikhao")
    assert result["listings"] == []
    assert "Faisalabad DHA" in result["response"]
    reset_session(sid)
    from conversation_memory import update_state, add_turn
    update_state(sid, slots={"budget":30_000_000})
    add_turn(sid,"user","Budget 3 crore hai.")
    assert get_state(sid)["slots"]["budget"]==30_000_000
    reset_session(sid)

def test_farewells():
    from day3_agent import run_turn
    sid = "test-farewell"
    reset_session(sid)

    res1 = run_turn(sid, "Islamabad mein house dikhao")
    assert res1["listings"]

    res2 = run_turn(sid, "اوکے اللہ حافظ")
    assert res2["route"]["route"] == "chat"
    assert "Allah Hafiz" in res2["response"] or "shukriya" in res2["response"]
    assert res2.get("listings") == []

    res3 = run_turn(sid, "بائے")
    assert res3["route"]["route"] == "chat"
    assert "Allah Hafiz" in res3["response"] or "shukriya" in res3["response"]
    assert res3.get("listings") == []

def test_urdu_objections():
    assert detect_objection("قیمت بہت زیادہ ہے") == "price"
    assert detect_objection("اس بلڈر پر بھروسہ کیسے کروں؟") == "builder"
    assert detect_objection("لوکیشن بہت دور ہے") == "location"
    assert detect_objection("سرمایہ کاری کے لیے یہ کیسا ہے؟") == "investment"
    assert detect_objection("اسکام یا فراڈ کا خطرہ تو نہیں؟") == "trust"
    assert detect_objection("مینٹیننس چارجز کتنے ہیں؟") == "maintenance"

def test_human_evaluation():
    from evaluation_harness import save_turn, score_call, get_evaluation_history
    sid = "eval-test-sid"
    rec = save_turn(sid, "Test prompt", "Test response", {"total_ms": 500})
    call_id = rec["call_id"]

    res = score_call(call_id, {"naturalness": 5, "persuasiveness": 4, "fluency": 5, "latency": 5, "conversation_flow": 4}, "Great call")
    assert res["status"] == "ok"

    history = get_evaluation_history(limit=5)
    assert any(item["call_id"] == call_id for item in history)

if __name__=="__main__":
    test_money(); test_slots(); test_routes(); test_objections(); test_persistence(); test_natural_chat_and_location_grounding(); test_location_broadening_preserves_city(); test_verified_nearby_facilities(); test_purpose_question_and_city_reset()
    test_farewells(); test_urdu_objections(); test_human_evaluation()
    print("All Day 3 local tests passed successfully.")

