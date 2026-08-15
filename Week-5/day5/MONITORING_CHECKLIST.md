# Production Monitoring Checklist

## 1. Error Rate

- **track:** API failures, agent exceptions, tool failures, validation errors
- **alert:** > 5% over a rolling 15-minute window
- **action:** Inspect logs, recent deployments, model/tool availability

## 2. Latency

- **track:** p50, p95, and p99 request latency
- **alert:** p95 > 10 seconds for 15 minutes
- **action:** Check model latency, tool calls, retries, and external APIs

## 3. Cost Drift

- **track:** Tokens per ticket and estimated cost per ticket
- **alert:** > 25% increase from 7-day baseline
- **action:** Inspect prompt growth, unnecessary retries, and model usage

## 4. Output Quality

- **track:** Task success, classification accuracy, safety, response quality
- **alert:** Quality score falls below 85%
- **action:** Review failed examples and rerun evaluation suite

## 5. Safety

- **track:** Unauthorized actions, unsafe responses, human-review bypasses
- **alert:** Any confirmed critical safety violation
- **action:** Immediately investigate and consider disabling affected workflow

## 6. Tool Reliability

- **track:** Tool success rate, timeout rate, external API errors
- **alert:** > 5% tool failures over 15 minutes
- **action:** Check external service health and activate fallback

## 7. Re-evaluation Cadence

- **track:** Agent quality against the fixed evaluation dataset
- **alert:** Any major model, prompt, tool, or workflow change
- **action:** Run the full evaluation suite before production rollout

## 8. Scheduled Evaluation

- **track:** Regression performance and quality drift
- **alert:** Weekly or after significant production changes
- **action:** Compare against previous evaluation baseline

