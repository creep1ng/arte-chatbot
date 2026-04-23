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

### Propósito
Herramienta implementada para cumplir con **US-07 (Precisión técnica verificable)**. Mide la tasa de alucinación del chatbot analizando las respuestas generadas por el harness de evaluación.

El sistema utiliza dos criterios conservadores para detectar información inventada:
1. **Valores técnicos sin fuentes**: Respuestas que contienen valores numéricos con unidades técnicas (W, V, A, %, °C, kWh) pero `num_sources == 0` (no se consultó ninguna ficha técnica)
2. **Valores no presentes en fuentes**: Respuestas que contienen valores numéricos técnicos que **no aparecen** en ninguno de los documentos fuente recuperados

### Uso

Ejecutar el script sobre un CSV generado por el harness:

```bash
python evaluation/hallucination_check.py --run evaluation/harness/output/results_YYYYMMDD_HHMMSS.csv
```

Opcionalmente subir el reporte a S3:

```bash
python evaluation/hallucination_check.py --run evaluation/harness/output/results_YYYYMMDD_HHMMSS.csv --upload-s3
```

### Variables de entorno para subida a S3

| Variable | Descripción |
|----------|-------------|
| `AWS_ACCESS_KEY_ID` | Clave de acceso AWS |
| `AWS_SECRET_ACCESS_KEY` | Clave secreta AWS |
| `AWS_BUCKET_NAME` | Nombre del bucket S3 (ej: `arte-chatbot-data`) |
| `AWS_REGION` | Región AWS (por defecto `us-east-1`) |

### Salida del reporte

El reporte se guarda en `evaluation/results/hallucination_<timestamp>.json` con los siguientes campos:

| Campo | Descripción |
|-------|-------------|
| `total_queries` | Total de consultas analizadas |
| `hallucination_count` | Cantidad de alucinaciones detectadas |
| `hallucination_rate_percent` | Tasa global de alucinación (%) |
| `average_num_sources` | Promedio de fuentes utilizadas por consulta |
| `suspicious_queries` | Lista detallada de consultas marcadas, con:
| | - `query_id`: Identificador de la consulta
| | - `reason`: Motivo de la marca (`num_sources == 0` o `numerical hallucination detected`)
| | - `suspicious_values`: Valores numéricos no encontrados en fuentes
| | - `num_sources`: Cantidad de fuentes recuperadas para esta consulta
| `criteria` | Criterios de detección utilizados en esta ejecución

### Criterios de aceptación

Un resultado **inferior al 20%** de tasa de alucinación cumple con los criterios de US-07.

### Notas de implementación

- El script utiliza expresiones regulares para extraer valores numéricos con unidades técnicas comunes en el dominio solar
- **No marca como alucinación** conversaciones normales sin valores técnicos incluso si `num_sources == 0` (evita falsos positivos)
- Se integra directamente con la salida del harness sin dependencias adicionales del backend
- Compatible con Python 3.12+ (utiliza `datetime.now(timezone.utc)` en lugar del deprecado `utcnow()`)

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

## Quality Report (US-13)

This section covers the quality report system for comparing Sprint 2 (baseline) vs Sprint 5 (final) metrics.

### S3 Report Structure

Reports are stored in S3 with the following structure:

```
arte-chatbot-data/
└── evaluation/
    └── reports/
        ├── sprint_2/
        │   ├── harness/report_YYYYMMDD_HHMMSS.json
        │   ├── hallucination/report_YYYYMMDD_HHMMSS.json
        │   └── human_eval/report_YYYYMMDD_HHMMSS.json
        └── sprint_5/
            ├── harness/report_YYYYMMDD_HHMMSS.json
            ├── hallucination/report_YYYYMMDD_HHMMSS.json
            └── human_eval/report_YYYYMMDD_HHMMSS.json
```

### Metrics Tracked

| Metric | Description | Source |
|--------|-------------|--------|
| Latency (avg, p50, p95, p99) | Response time in milliseconds | Harness |
| Escalation Rate | Percentage of queries escalated | Harness |
| Escalation Accuracy | Correct escalation decisions (%) | Harness |
| Technical Accuracy | Score 1-5 from human evaluation | Human Eval |
| Hallucination Rate | Percentage of hallucinations detected | Hallucination Check |

### Running the Harness with S3 Upload

```bash
# Run and upload to S3
python -m evaluation.harness.run --sprint sprint_5 --upload-s3

# With custom API endpoint
python -m evaluation.harness.run --sprint sprint_2 --api-url http://localhost:8000
```

### Generating Mock Data

For testing without real evaluations:

```bash
# Generate mock data locally
python evaluation/mock_data_generator.py --output-dir evaluation/mock_data

# Upload mock data to S3
python evaluation/upload_mock_to_s3.py --sprints sprint_2 sprint_5
```

### Quality Report Notebook

The interactive quality report is in `evaluation/quality_report.ipynb`.

**Usage:**

1. Open in Jupyter:
   ```bash
   jupyter notebook evaluation/quality_report.ipynb
   ```

2. Or run with JupyterLab:
   ```bash
   jupyter lab evaluation/quality_report.ipynb
   ```

3. Install dependencies if needed:
   ```bash
   pip install plotly boto3 pandas numpy
   ```

**Features:**
- Reads data from S3 if available, falls back to mock data
- Interactive Plotly charts comparing Sprint 2 vs Sprint 5
- Latency analysis with percentiles
- Human evaluation dimension breakdown
- Gauge charts for current status
- Export to HTML/PDF for sharing

**Export options:**
```python
# Export to HTML (interactive)
fig.write_html("evaluation/reports/quality_report.html")

# Export to PDF (requires kaleido)
fig.write_image("evaluation/reports/quality_report.pdf", format="pdf")
```

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `AWS_ACCESS_KEY_ID` | AWS access key | Yes (for S3) |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key | Yes (for S3) |
| `AWS_BUCKET_NAME` | S3 bucket name (default: `arte-chatbot-data`) | No |
| `AWS_REGION` | AWS region (default: `us-east-1`) | No |

### Git Commit Tracking

Each evaluation run automatically records:
- Current git commit hash (`git rev-parse --short HEAD`)
- Current git branch name

This allows correlating evaluation results with specific code versions.
