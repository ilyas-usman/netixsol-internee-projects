# 🚀 Capstone — Production-Ready Support Ticket Triage Agent

## 📌 Overview

This capstone project brings together the major concepts learned throughout Week 5 to build an end-to-end **Production-Ready Support Ticket Triage Agent**.

The system uses **LangGraph** for controlled agent orchestration and **Groq** for fast LLM inference. It processes customer-support tickets, classifies them, retrieves relevant customer and knowledge-base information, generates responses, validates them, performs self-correction when required, and routes consequential cases to human reviewers.

The project also includes **evaluation, FastAPI deployment, logging, monitoring, and an executive report**, making it a complete mini production-oriented agent system rather than only a framework demonstration.

---

## 🎯 Business Problem

Customer-support teams often spend significant time manually:

- Reading and understanding incoming tickets
- Categorizing support requests
- Determining ticket priority
- Looking up customer information
- Searching support documentation
- Writing repetitive responses
- Identifying tickets that require escalation

The goal of this project is to automate these repetitive tasks while keeping **human oversight for consequential decisions** such as refunds, security incidents, and high-priority issues.

---

## 💡 Solution

The Support Ticket Triage Agent provides an automated workflow:

```text
Customer Ticket
      ↓
Ticket Analysis
      ↓
Customer Lookup
      ↓
External Context
      ↓
Knowledge Retrieval
      ↓
Response Drafting
      ↓
Response Validation
      ↓
Self-Correction
      ↓
Human Review Check
      ↓
 ┌───────────────┐
 │               │
 ▼               ▼
Human Review   Finalize
 │               │
 └───────┬───────┘
         ↓
   Final Response