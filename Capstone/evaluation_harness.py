"""Human evaluation + automatic recording/latency harness."""
from __future__ import annotations
import csv, json, os, glob, time
from datetime import datetime
from day3_config import EVAL_DIR, LATENCY_TARGET_MS
from day3_objections import OBJECTION_TEST_SET

RUBRIC = {
    "naturalness": "1-5: sounds robotic -> indistinguishable from a natural sales conversation",
    "persuasiveness": "1-5: generic/weak -> relevant, grounded and helpful without pressure",
    "fluency": "1-5: awkward -> fluent UrduLish/code-switching",
    "latency": "1-5: >4s -> <1.5s perceived response start",
    "conversation_flow": "1-5: loses context -> remembers/corrects/refers naturally",
}

def init_eval():
    os.makedirs(EVAL_DIR, exist_ok=True)

def save_turn(session_id, transcript, response, timings, audio_bytes=None):
    init_eval()
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S%fZ")
    call_id = f"{stamp}_{session_id}"
    record = {
        "call_id": call_id,
        "session_id": session_id,
        "timestamp": stamp,
        "transcript": transcript,
        "response": response,
        "timings": timings,
        "under_2s": timings.get("voice_total_ms", timings.get("total_ms", 99999)) < LATENCY_TARGET_MS,
    }
    with open(os.path.join(EVAL_DIR, f"{call_id}.json"), "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    if audio_bytes:
        with open(os.path.join(EVAL_DIR, f"{call_id}.mp3"), "wb") as f:
            f.write(audio_bytes)
    return record

def get_evaluation_history(limit: int = 20) -> list[dict]:
    init_eval()
    # Read existing human scores from CSV
    scores_map = {}
    csv_path = os.path.join(EVAL_DIR, "human_scores.csv")
    if os.path.exists(csv_path):
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                call_id = row.get("call_id")
                if call_id:
                    scores_map[call_id] = {
                        "scores": {k: int(row[k]) for k in RUBRIC.keys() if k in row and row[k].isdigit()},
                        "notes": row.get("notes", "")
                    }

    records = []
    json_files = glob.glob(os.path.join(EVAL_DIR, "*.json"))
    for file_path in json_files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                call_id = data.get("call_id") or os.path.splitext(os.path.basename(file_path))[0]
                data["call_id"] = call_id
                if call_id in scores_map:
                    data["human_evaluation"] = scores_map[call_id]
                records.append(data)
        except Exception:
            continue

    records.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return records[:limit]

def score_call(call_id: str, scores: dict, notes: str = ""):
    init_eval()
    validated_scores = {k: int(scores.get(k, 3)) for k in RUBRIC.keys()}
    row = {"call_id": call_id, **validated_scores, "notes": notes}
    path = os.path.join(EVAL_DIR, "human_scores.csv")
    exists = os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=row.keys())
        if not exists:
            w.writeheader()
        w.writerow(row)

    # Update JSON file if present
    json_files = glob.glob(os.path.join(EVAL_DIR, f"*{call_id}*.json"))
    for file_path in json_files:
        try:
            with open(file_path, "r+", encoding="utf-8") as f:
                data = json.load(f)
                data["human_evaluation"] = {"scores": validated_scores, "notes": notes}
                f.seek(0)
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.truncate()
        except Exception:
            pass

    return {"status": "ok", "call_id": call_id, "scores": validated_scores, "notes": notes}

def objection_test_report():
    counts = {}
    for x in OBJECTION_TEST_SET:
        counts[x["category"]] = counts.get(x["category"], 0) + 1
    return {
        "total": len(OBJECTION_TEST_SET),
        "by_category": counts,
        "all_categories_have_5_plus": all(v >= 5 for v in counts.values()),
        "rubric": RUBRIC,
    }

