"""
Week 7 - Day 2 - Task 2: RAG Pipeline
=======================================
Document Loader -> Chunking -> Embedding -> Vector Store -> Retriever -> Answer Generation

Notes on stack choices for THIS project:
- LLM (answer generation): Groq API (fast inference, you already have a key)
- Embeddings: sentence-transformers (local, free, no extra key needed) -
  Groq does not serve an embeddings endpoint, so this is the practical swap-in
  for the "GPT-5.5/Claude/Gemini" line in your stack doc, which was about the
  reasoning LLM, not embeddings.
- Vector store: ChromaDB (local, zero-infra, matches your stack doc's first choice)

What goes IN the vector store here (per the structured/semantic split in Task 3):
  brochure text, FAQs, payment-plan descriptions, developer notes, location "feel" writeups
What does NOT go in the vector store: prices, bedroom counts, availability, agent names
  (those live in SQL - see structured_retrieval.py)
"""

import os
import glob
import chromadb
from chromadb.utils import embedding_functions
from groq import Groq
from dotenv import load_dotenv

load_dotenv()  # reads .env in the current working directory, sets os.environ from it

# ---------- CONFIG ----------
CHROMA_DIR = "./chroma_db"
COLLECTION_NAME = "realestate_knowledge"
EMBED_MODEL = "all-MiniLM-L6-v2"   # 384-dim, fast, good enough for short property text
GROQ_MODEL = "openai/gpt-oss-120b"  # swap for whichever Groq model you're standardized on
CHUNK_SIZES_TO_EVALUATE = [200, 400, 800]  # characters, evaluated in evaluate_chunk_sizes()


# ---------- 1. DOCUMENT LOADER ----------
def load_documents(docs_dir="./knowledge_docs"):
    """
    Loads unstructured knowledge: FAQs, brochures, payment plan text, developer notes.
    Expects .txt/.md files. Each file = one logical document, tagged with a source type
    inferred from its filename prefix (faq_, brochure_, payment_, developer_).
    """
    docs = []
    for path in glob.glob(os.path.join(docs_dir, "*")):
        if not path.endswith((".txt", ".md")):
            continue
        fname = os.path.basename(path)
        source_type = fname.split("_")[0] if "_" in fname else "general"
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        docs.append({"source": fname, "type": source_type, "text": text})
    return docs


# ---------- 2. CHUNKING ----------
def chunk_text(text, chunk_size=400, overlap=60):
    """
    Simple sliding-window chunker on characters, breaking at sentence boundaries
    where possible so we don't cut a payment-plan clause mid-sentence.
    """
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        window = text[start:end]
        # try to end on a sentence boundary
        last_period = window.rfind(". ")
        if last_period > chunk_size * 0.5:  # only trim if it doesn't waste too much
            end = start + last_period + 1
        chunks.append(text[start:end].strip())
        start = end - overlap
    return [c for c in chunks if c]


def chunk_documents(docs, chunk_size=400, overlap=60):
    all_chunks = []
    for doc in docs:
        for i, chunk in enumerate(chunk_text(doc["text"], chunk_size, overlap)):
            all_chunks.append({
                "id": f"{doc['source']}::chunk{i}",
                "text": chunk,
                "metadata": {"source": doc["source"], "type": doc["type"]},
            })
    return all_chunks


# ---------- 3 & 4. EMBEDDING + VECTOR STORE ----------
def get_collection(reset=False):
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)
    if reset:
        try:
            client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass
    return client.get_or_create_collection(name=COLLECTION_NAME, embedding_function=embed_fn)


def index_chunks(chunks, reset=True):
    collection = get_collection(reset=reset)
    if not chunks:
        return collection
    collection.add(
        ids=[c["id"] for c in chunks],
        documents=[c["text"] for c in chunks],
        metadatas=[c["metadata"] for c in chunks],
    )
    return collection


# ---------- 5. RETRIEVER ----------
def retrieve(query, collection, k=4, source_type_filter=None):
    where = {"type": source_type_filter} if source_type_filter else None
    results = collection.query(query_texts=[query], n_results=k, where=where)
    hits = []
    for doc, meta, dist in zip(results["documents"][0], results["metadatas"][0], results["distances"][0]):
        hits.append({"text": doc, "source": meta["source"], "score": 1 - dist})
    return hits


# ---------- 6. ANSWER GENERATION ----------
def generate_answer(query, hits, structured_context=None, groq_api_key=None):
    """
    structured_context: pre-formatted string from structured_retrieval.py (SQL results)
    for prices/availability/etc, so the LLM never has to guess numbers.
    """
    client = Groq(api_key=groq_api_key or os.environ.get("GROQ_API_KEY"))

    context_blocks = "\n\n".join(f"[Source: {h['source']}]\n{h['text']}" for h in hits)
    structured_block = f"\n\nVERIFIED DATABASE FACTS (use these exact numbers, never override them):\n{structured_context}" if structured_context else ""

    system_prompt = (
        "You are a real estate assistant for RealEstate Hub in Pakistan. "
        "Answer ONLY using the provided context and database facts. "
        "If the answer isn't in the context, say you don't have that information "
        "and offer to connect them with an agent. Never invent prices, availability, "
        "or property details. Respond in UrduLish (Roman Urdu mixed with English), warm and professional."
    )
    user_prompt = f"Context:\n{context_blocks}{structured_block}\n\nQuestion: {query}"

    resp = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,  # low - grounding matters more than creativity here
    )
    return resp.choices[0].message.content


def generate_grounded_reply(user_text, hits, structured_context=None, extra_instructions="", groq_api_key=None):
    """
    Day 3 entry point — use this instead of generate_answer() whenever you
    already have conversation history / voice rules / objection strategy
    to include. Those go into `extra_instructions` as SYSTEM content.

    WHY THIS EXISTS (bug it fixes): the original call site in day3_agent.py
    was passing an entire pre-assembled meta-prompt (history + voice rules +
    persistent slots + a "say you don't have info and offer an agent" line)
    as the `query` argument to generate_answer(), which then nested it AGAIN
    inside "Question: {query}". The model ended up seeing the fallback
    instruction sitting right next to the real DB facts inside the same
    Question block, and a small model (gpt-oss-20b) would sometimes just
    parrot the fallback line back regardless of whether the facts actually
    answered the question. Traced this directly: query_properties()
    correctly returns real rows for "DHA mein kya options hain?" every
    single time — the SQL/retrieval layer was never the problem, prompt
    structure was. Keeping the meta-prompt content out of the nested
    "Question:" field and putting it in the system message instead removes
    the contradiction.
    """
    client = Groq(api_key=groq_api_key or os.environ.get("GROQ_API_KEY"))

    context_blocks = "\n\n".join(f"[Source: {h['source']}]\n{h['text']}" for h in hits) if hits else "(no unstructured context retrieved for this turn)"
    structured_block = (
        f"\n\nVERIFIED DATABASE FACTS (use these exact numbers, never override them):\n{structured_context}"
        if structured_context else
        "\n\nVERIFIED DATABASE FACTS: none retrieved for this turn."
    )

    system_prompt = (
        "You are a real estate voice assistant for RealEstate Hub in Pakistan.\n\n"
        "CRITICAL GROUNDING RULE: if VERIFIED DATABASE FACTS are provided below and they "
        "are relevant to the user's question, you MUST use them directly and MUST NOT say "
        "you lack information or offer to connect a human agent for that request — the "
        "facts ARE the answer. Only say you don't have information and offer a human agent "
        "when there are truly NO verified facts and NO context relevant to the question.\n"
        "Never invent prices, availability, amenities, schools, hospitals, or developer claims "
        "beyond what's given in the context/facts below.\n\n"
        f"{extra_instructions}"
    ).strip()

    user_prompt = f"Context:\n{context_blocks}{structured_block}\n\nUser's question: {user_text}"

    resp = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
    )
    return resp.choices[0].message.content


# ---------- CHUNK SIZE EVALUATION ----------
def evaluate_chunk_sizes(docs, test_queries, groq_api_key=None):
    """
    Evaluate CHUNK_SIZES_TO_EVALUATE by measuring, for each size:
      - avg retrieval score (embedding similarity) for a set of test queries
      - number of chunks produced (proxy for index size / cost)
    Smaller chunks (200) = more precise but can lose surrounding context (e.g. a payment
    plan clause split from its heading). Larger chunks (800) = more context but noisier
    retrieval and higher token cost per query. 400 is the usual sweet spot for FAQ/brochure
    style text; this function lets you confirm that empirically on YOUR documents.
    """
    results = {}
    for size in CHUNK_SIZES_TO_EVALUATE:
        chunks = chunk_documents(docs, chunk_size=size, overlap=int(size * 0.15))
        collection = index_chunks(chunks, reset=True)
        scores = []
        for q in test_queries:
            hits = retrieve(q, collection, k=3)
            if hits:
                scores.append(sum(h["score"] for h in hits) / len(hits))
        results[size] = {
            "num_chunks": len(chunks),
            "avg_retrieval_score": round(sum(scores) / len(scores), 4) if scores else 0,
        }
    return results


if __name__ == "__main__":
    docs = load_documents()
    if not docs:
        print("No docs found in ./knowledge_docs - add FAQ/brochure .txt files first.")
    else:
        chunks = chunk_documents(docs, chunk_size=400)
        collection = index_chunks(chunks)
        print(f"Indexed {len(chunks)} chunks from {len(docs)} documents.")

        test_qs = ["What is the down payment for installment plans?", "Is there a park nearby?"]
        eval_results = evaluate_chunk_sizes(docs, test_qs)
        print("Chunk size evaluation:", eval_results)