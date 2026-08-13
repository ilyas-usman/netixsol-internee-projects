# Week 5 – Day 4: CrewAI — Multi-Agent Collaboration, Roles & Task Delegation

## Overview

This project explores **CrewAI**, a framework for building multi-agent AI systems where specialized agents collaborate to complete a shared objective.

The implementation focuses on designing agents with distinct **roles, goals, and backstories**, assigning role-appropriate tools, creating dependent tasks, comparing **sequential and hierarchical orchestration**, and evaluating token usage, approximate cost, latency, reliability, and output quality.

---

## Business Scenario

The chosen business problem is:

> **Research a competitor, summarize the findings into strategic insights, and draft a differentiated marketing angle.**

The competitor used for the analysis is **Notion**.

The workflow consists of three specialized agents:

```text
Competitor Research
        ↓
Strategic Analysis
        ↓
Marketing Copywriting
        ↓
Final Marketing Recommendation
```

This task was selected because research, strategic analysis, and copywriting are naturally separable responsibilities. Each stage can therefore be assigned to a specialized agent rather than relying on one general-purpose agent.

---

## Agents

### 1. Competitor Research Analyst

**Role:** Competitor Research Analyst

**Goal:** Gather accurate and well-sourced information about Notion's products, pricing, target customers, positioning, strengths, weaknesses, and public sentiment.

**Backstory:** A former competitive-intelligence consultant experienced in researching product pages, reviews, and market information to build accurate competitor profiles.

**Tool:** `SerperDevTool`

---

### 2. Strategic Insights Analyst

**Role:** Strategic Insights Analyst

**Goal:** Convert competitor research into 3–5 strategic insights covering strengths, weaknesses, customer needs, positioning, and market opportunities.

**Backstory:** A strategy consultant experienced in turning large amounts of research into concise, actionable insights.

**Tool:** `FileReadTool`

---

### 3. Marketing Copywriter

**Role:** Marketing Copywriter

**Goal:** Transform strategic insights into a compelling and differentiated marketing angle with supporting rationale.

**Backstory:** A technology-focused brand copywriter who specializes in developing specific positioning statements rather than generic marketing language.

**Tool:** `FileWriterTool`

---

## Tasks

The CrewAI workflow contains three main tasks:

1. **Competitor Research** — Research Notion's products, pricing, positioning, strengths, weaknesses, and customer sentiment.
2. **Strategic Analysis** — Convert the research into evidence-based strategic insights and identify the top strategic opportunity.
3. **Marketing Copywriting** — Turn the strategic opportunity into a differentiated marketing recommendation.

---

## Sequential Process

The sequential workflow executes tasks in a fixed order:

```text
Research
   ↓
Analysis
   ↓
Copywriting
   ↓
Final Recommendation
```

The workflow uses:

```python
process=Process.sequential
```

This approach is predictable and easy to debug because each task receives the output of the previous task.

---

## Hierarchical Process

The hierarchical workflow introduces a manager agent responsible for coordinating the specialist agents:

```text
                 Manager
                /   |   \
        Research Analysis Copywriting
                \   |   /
                 Final Result
```

The workflow uses:

```python
process=Process.hierarchical
manager_agent=manager_agent
```

The manager coordinates delegation, reviews outputs, and ensures that the final recommendation is supported by strategic evidence.

---

## Sequential vs. Hierarchical

| Metric             | Sequential | Hierarchical |
| ------------------ | ---------: | -----------: |
| **Execution Time** | 118.22 sec |    43.59 sec |
| **Total Tokens**   |    113,196 |      128,194 |
| **Approx. Cost**   |  $0.173694 |    $0.204598 |
| **Completed**      |        Yes |          Yes |

### Key Findings

The hierarchical workflow was approximately **63.15% faster** in the recorded experiment.

However, it consumed more tokens and had a higher approximate cost:

* Sequential: **113,196 tokens — $0.173694**
* Hierarchical: **128,194 tokens — $0.204598**

Therefore, hierarchical orchestration provided lower latency in this experiment but required more token usage and cost.

---

## Evaluation

The CrewAI workflow was manually evaluated using three criteria on a scale of **1–5**.

| Criterion             | Average Score |
| --------------------- | ------------: |
| **Factual Grounding** |        4.33/5 |
| **Completeness**      |        5.00/5 |
| **Strategic Quality** |        4.67/5 |
| **Overall**           |    **4.67/5** |

The results indicate strong performance across factual grounding, completeness, and strategic quality.

---

## Key Learnings

* Agent roles, goals, and backstories
* Role-specific tool assignment
* Task dependencies
* Context passing between tasks
* Sequential orchestration
* Hierarchical delegation
* Manager agents
* Multi-agent collaboration
* Token usage tracking
* Approximate cost calculation
* Latency comparison
* Agent output evaluation

---

## Technologies Used

* **Python**
* **CrewAI**
* **Google Gemini**
* **SerperDevTool**
* **FileReadTool**
* **FileWriterTool**
* **Pandas**
* **python-dotenv**

---
## Conclusion

CrewAI is useful when a problem naturally benefits from multiple specialized agents.

**Sequential processing** is preferable for clear and predictable pipelines where tasks have well-defined dependencies.

**Hierarchical processing** is more suitable for complex projects requiring dynamic delegation, centralized supervision, specialist coordination, and review.

For this Notion competitor-analysis project, both approaches successfully completed the task. The sequential workflow remained simpler and cheaper, while the hierarchical workflow achieved significantly lower latency in the recorded experiment at the cost of higher token usage and approximate API cost.
