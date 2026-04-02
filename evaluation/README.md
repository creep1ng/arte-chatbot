# Evaluation Harness

This module provides an automated testing harness for evaluating the ARTE Chatbot's performance and accuracy.

## Overview

The harness sends a dataset of test queries to the `/chat` endpoint and records:
- Response text
- Latency (in milliseconds)
- Session ID
- Escalation flag

Results are saved in both JSON and CSV formats with timestamps.

## Quick Start

### Running the Harness

1. Ensure the backend is running:
   ```bash
   docker compose up -d
   ```

2. Run the harness:
   ```bash
   # Inside the container
   docker compose exec backend python -m evaluation.harness.run

   # Or directly if running locally
   python -m evaluation.harness.run
   ```

### Output Files

Results are saved to `evaluation/harness/output/` with timestamps:
- `results_YYYYMMDD_HHMMSS.json` - Full JSON output
- `results_YYYYMMDD_HHMMSS.csv` - CSV format for analysis

## Adding New Test Queries

To add new queries to the test dataset, edit `evaluation/harness/dataset.json`:

```json
[
  {
    "id": "q001",
    "query": "¿Your question in Spanish?",
    "expected_intent": "intent_name",
    "should_escalate": false
  }
]
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique identifier (e.g., q001, q002) |
| `query` | string | The test query in Spanish |
| `expected_intent` | string | Expected intent (optional) |
| `should_escalate` | boolean | Whether this query should escalate to human agent |

### Best Practices for Adding Queries

1. **Use realistic solar energy domain queries**:
   - Technical specifications
   - Product recommendations
   - Pricing inquiries
   - Warranty questions
   - Troubleshooting

2. **Cover different intent types**:
   - `technical_specs` - Questions about product specifications
   - `product_recommendation` - Seeking product advice
   - `pricing` - Cost-related questions
   - `warranty_info` - Guarantee/warranty questions
   - `technical_support` - Troubleshooting

3. **Include escalation cases**:
   - Complex pricing for large installations
   - Custom requirements
   - Complaints or issues requiring human intervention

4. **Test edge cases**:
   - Empty or very short messages
   - Questions outside the solar domain
   - Multiple questions in one message

## Example Queries

```json
{
  "id": "q006",
  "query": "¿Cuántos paneles necesito para un sistema de 3kW?",
  "expected_intent": "product_recommendation",
  "should_escalate": false
},
{
  "id": "q007",
  "query": "¿Ofrecen instalación en la ciudad de Medellín?",
  "expected_intent": "service_availability",
  "should_escalate": true
}
```

## CI/CD Integration

The harness is designed to run as part of the GitHub Actions pipeline. Add this step to your workflow:

```yaml
- name: Run evaluation harness
  run: |
    docker compose up -d
    sleep 5
    docker compose exec -T backend python -m evaluation.harness.run
```

## Output Format

### JSON Output

```json
{
  "timestamp": "2024-01-15T10:30:00.000000Z",
  "total_queries": 5,
  "results": [
    {
      "query_id": "q001",
      "query": "¿Cuáles son las características del panel...?",
      "expected_intent": "technical_specs",
      "should_escalate": false,
      "response": "Gracias por tu consulta...",
      "session_id": "abc-123",
      "latency_ms": 45.32,
      "escalated": false,
      "error": "",
      "timestamp": "2024-01-15T10:30:00Z"
    }
  ]
}
```

### CSV Output

| query_id | query | expected_intent | should_escalate | response | session_id | latency_ms | escalated | error | timestamp |
|----------|-------|-----------------|----------------|----------|------------|------------|-----------|-------|-----------|
| q001 | ... | technical_specs | false | ... | abc-123 | 45.32 | false | | 2024-01-15... |

## Hallucination Check

Run the hallucination check script on a harness CSV output:

```bash
python evaluation/hallucination_check.py --run evaluation/harness/output/results_YYYYMMDD_HHMMSS.csv
```

Optionally upload the report to S3:

```bash
python evaluation/hallucination_check.py --run evaluation/harness/output/results_YYYYMMDD_HHMMSS.csv --upload-s3
```

### Environment variables for S3 upload

| Variable | Description |
|----------|-------------|
| `AWS_ACCESS_KEY_ID` | AWS access key |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key |
| `AWS_BUCKET_NAME` | S3 bucket name (e.g. `arte-chatbot-data`) |
| `AWS_REGION` | AWS region (defaults to `us-east-1`) |

### Report output

The report is saved to `evaluation/results/hallucination_<timestamp>.json` containing:
- `hallucination_rate_percent`: Global hallucination rate
- `suspicious_queries`: List of flagged queries with reasons
- `average_num_sources`: Mean `num_sources` across all queries

A rate below **20%** satisfies the US-07 acceptance criterion.

## Troubleshooting

### Connection Refused

If you see "Connection error: Could not connect to http://localhost:8000":
- Ensure Docker containers are running: `docker compose ps`
- Check if the backend is healthy: `curl http://localhost:8000/health`

### Request Timeout

If requests timeout:
- Increase the timeout in `run.py` (default is 30 seconds)
- Check backend logs: `docker compose logs backend`

### Module Not Found

If you get "No module named evaluation.harness":
- Ensure you're running from the project root
- Check that `evaluation/__init__.py` exists
