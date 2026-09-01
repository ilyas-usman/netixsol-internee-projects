"""
Week 7 - Day 2 - Full Test Runner
====================================
Runs all 5 Day 2 tasks end-to-end and prints results so you can eyeball
correctness at each stage. Run this AFTER:
  1. Copying all Day 2 .py files + knowledge_docs/ folder + both CSVs
     into the same folder.
  2. pip install pandas chromadb sentence-transformers groq
  3. Setting GROQ_API_KEY as an environment variable.

Usage: python test_day2_all.py
"""
import os
import json
from dotenv import load_dotenv

load_dotenv()  # reads .env in this folder - GROQ_API_KEY=... goes there

print("\n" + "=" * 70)
print("TASK 1 + 3: Building structured DB from CSVs")
print("=" * 70)
from structured_retrieval import build_database, query_properties, query_commercial, format_as_context

build_database("Property_with_Feature_Engineering.csv", "dummy_commercial_properties.csv")

print("\nSample query - 3 bed Lahore houses under 2 crore:")
props = query_properties(city="Lahore", purpose="For Sale", bedrooms=3, max_price=20_000_000, limit=3)
print(format_as_context(props, kind="residential"))


print("\n" + "=" * 70)
print("TASK 2: RAG pipeline - indexing knowledge_docs/ and testing retrieval")
print("=" * 70)
from rag_pipeline import load_documents, chunk_documents, index_chunks, retrieve, evaluate_chunk_sizes

docs = load_documents("./knowledge_docs")
print(f"Loaded {len(docs)} documents: {[d['source'] for d in docs]}")

chunks = chunk_documents(docs, chunk_size=400)
collection = index_chunks(chunks)
print(f"Indexed {len(chunks)} chunks")

test_query = "What is the down payment for Bahria Town plots?"
hits = retrieve(test_query, collection, k=3)
print(f"\nRetrieval test for: '{test_query}'")
for h in hits:
    print(f"  [{h['score']:.3f}] {h['source']}: {h['text'][:100]}...")

print("\nChunk size evaluation (200 vs 400 vs 800 chars):")
eval_results = evaluate_chunk_sizes(docs, [
    "What is the down payment for installment plans?",
    "Is there a park nearby in Gulberg?",
    "What is the refund policy if I cancel?",
])
print(json.dumps(eval_results, indent=2))

# re-index at 400 (evaluate_chunk_sizes leaves the collection on whichever size ran last)
collection = index_chunks(chunk_documents(docs, chunk_size=400))


print("\n" + "=" * 70)
print("TASK 2 (cont.): Full answer generation via Groq (requires GROQ_API_KEY)")
print("=" * 70)
if os.environ.get("GROQ_API_KEY"):
    from rag_pipeline import generate_answer
    hits = retrieve(test_query, collection, k=3)
    answer = generate_answer(test_query, hits)
    print(f"Q: {test_query}")
    print(f"A: {answer}")
else:
    print("GROQ_API_KEY not set - skipping live answer generation test.")


print("\n" + "=" * 70)
print("TASK 4: Recommendation engine")
print("=" * 70)
from recommendation_engine import recommend_properties, recommend_commercial, explain_recommendations

recs = recommend_properties(budget_max=25_000_000, city="Lahore", bedrooms=3,
                             purpose="For Sale", desired_amenities=["Park"], investment_goal=False)
print("Residential recommendations:")
print(explain_recommendations(recs))

comm_recs = recommend_commercial(budget_max=50_000_000, city="Lahore", unit_type="Shop")
print("\nCommercial recommendations:")
print(explain_recommendations(comm_recs, kind="commercial"))


print("\n" + "=" * 70)
print("TASK 5: Hallucination evaluation (20 questions)")
print("=" * 70)
if os.environ.get("GROQ_API_KEY"):
    from hallucination_eval import run_evaluation
    from rag_pipeline import generate_answer as gen_ans

    def full_pipeline_answer_with_context(question):
        hits = retrieve(question, collection, k=3)
        context_text = "\n\n".join(h["text"] for h in hits)
        answer = gen_ans(question, hits)
        return answer, context_text

    report = run_evaluation(full_pipeline_answer_with_context)
    print(f"Grounding rate: {report['grounding_rate']}")
    print(report["retrieval_accuracy_note"])
    print()
    for r in report["results"]:
        flag = "" if r["grounded"] else "  <-- CHECK THIS"
        print(f"[{r['category']}] Q: {r['question']}")
        print(f"  A: {r['answer']}")
        if r["ungrounded_numbers"]:
            print(f"  Numbers in answer NOT found in retrieved context: {r['ungrounded_numbers']}")
        print(f"  grounded={r['grounded']}{flag}\n")
else:
    print("GROQ_API_KEY not set - skipping hallucination eval (needs live LLM calls).")

print("\n" + "=" * 70)
print("DONE - review output above for each task")
print("=" * 70)