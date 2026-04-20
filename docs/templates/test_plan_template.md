# Plantilla de Plan de Pruebas — Arte Chatbot

## Propósito
Esta plantilla estandariza la evaluación de nuevas features antes de su merge a main. Debe completarse para cada feature significativa del chatbot Arte.

## Alcance
- [ ] 模块/funcionalidad evaluada
- [ ] Versión de API analizada
- [ ] Historias de usuario relacionadas

---

## Estrategia de Pruebas

### 1. Pruebas Unitarias
- **Alcance**: Lógica de negocio pura, funciones helpers, parsing de datos
- **Herramienta**: pytest
- **Criterio**: ≥ 80% coverage en módulos modificados

### 2. Pruebas de Integración
- **Alcance**: Endpoints FastAPI, interacciones S3, llamadas a LLM mockeado
- **Herramienta**: pytest + httpx + moto (mock AWS)
- **Criterio**: Todos los endpoints con status codes correctos

### 3. Pruebas E2E (Harness automatizado)
- **Alcance**: Flujo conversacional completo vía `/chat`
- **Herramienta**: Scripts en `evaluation/intent_eval/` y `evaluation/escalation_eval/`
- **Criterio**: Accuracy ≥ 80%, tasa de falsos positivos de escalamiento ≤ 15%

### 4. Evaluación Humana
- **Alcance**: Calidad de respuestas, tono, adequación de escalamiento
- **Herramienta**: `evaluation/human_eval/cli.py`
- **Criterio**: Score ponderado ≥ 3.5/5, precisión de escalamiento ≥ 90%

---

## Precondiciones de Entorno

```bash
# Variables requeridas
OPENAI_API_KEY=sk-...
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_BUCKET_NAME=arte-chatbot-data
CHAT_API_KEY=...        # Para autenticar requests al endpoint
API_BASE_URL=http://localhost:8000
```

###Mocks Disponibles
- **S3**: Usar `moto` para mockear operaciones de bucket
- **LLM**: Mock responses para testing sin llamar a APIs reales
- **Session**: Fixture `chat_with_session` en `backend/tests/conftest.py`

---

## Casos de Prueba

| ID | Descripción | Pasos | Resultado Esperado | Prioridad |
|----|-------------|-------|-------------------|-----------|
| TC-001 |Health check endpoint responde | GET /health | 200 OK, {"status":"healthy"} | P0 |
| TC-002 |Chat responde con intent reconocido | POST /chat con query de intent conocido | 200 + intent_type correcto | P0 |
| TC-003 |Escalamiento correcto en consulta compleja | POST /chat con query que requiere escalar | 200 + escalate=true | P1 |
| TC-004 |Manejo de fallback (query incomprensible) | POST /chat con query fuera de dominio | 200 + fallback response apropiado | P1 |
| TC-005 |Sesión mantiene contexto | POST /chat múltiples mensajes en misma sesión | Contexto preservado | P2 |

---

## Criterios de Aceptación

- [ ] Todos los TC-P0 pasan
- [ ] Coverage no baja del umbral establecido
- [ ] No hay regresiones en intents existentes
- [ ] Evaluación humana obtiene score ≥ umbral

---

## Notas y decisiones

<!-- Registrar decisions tomadas durante la evaluación que puedan afectar otros equipos o futur releases -->