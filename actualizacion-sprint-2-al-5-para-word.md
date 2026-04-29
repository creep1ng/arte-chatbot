# Actualización del Proyecto — Sprint 2 al Sprint 5

*Anexo de actualización para documento Word del proyecto "Automatización del Proceso de Atención al Cliente en Arte Soluciones Energéticas"*

---

## 1. Cambio de Arquitectura: RAG Vectorial → File Inputs

### Decisión

Durante el Sprint 2 se identificó que el enfoque tradicional RAG con base de datos vectorial (ChromaDB) era inadecuado para el catálogo de Arte Soluciones Energéticas. Los 15 productos iniciales presentaban alta similitud entre sí —solo изменяются uno o dos parámetros— lo que causaba que el retrieval vectorial confundiera modelos y generara tasas elevadas de alucinación.

La decisión, documentada en **ADR-003** (File Inputs como método de retrieval) y **ADR-002** (Infraestructura de datos con S3), fue adoptar **File Inputs**: en lugar de indexar PDFs en una base vectorial, el chatbot utiliza Tool Calling para invocar `leer_ficha_tecnica(ruta)`, que descarga el PDF desde S3 y lo adjunta directamente como File Input en la llamada al LLM. El LLM procesa el documento nativo con su capacidad nativa de lectura de PDFs.

### Justificación

| Criterio | RAG + ChromaDB | File Inputs |
|----------|----------------|-------------|
| Precisión en documentos similares | Baja (confusión entre modelos) | Alta (documento completo) |
| Complejidad de implementación | Alta (chunking, embeddings, indexación) | Baja |
| Costo tokens | Medio (embeddings + retrieval + generación) | Marginal (PDF adjunto solo cuando se necesita) |
| Mantenimiento | Alto (re-indexación en updates) | Bajo (sin índice) |
| Portabilidad entre providers | Baja (depende del modelo de embeddings) | Alta (OpenAI, Anthropic, Google soportan File Inputs) |

### Trade-offs aceptados

- **Incremento de tokens por conversación**: Cada mensaje que requiere consultar una ficha técnica consume más tokens al adjuntar el PDF. Para el volumen actual el costo es marginal.
- **Reversibilidad documentada**: Si el volumen de mensajes crece 10x o más, se reevaluará la migración a RAG en Sprint 4. Esta decisión está documentada y es monitoreable.

### Commit asociado al cambio

El último commit del Milestone 2 (`6797c543` — fix #15: "restore function wrapper in tools.py broken by merge") migró las definiciones de herramientas del formato Responses API `{name, description, parameters}` al formato Chat Completions API anidado `{type, function: {name, description, parameters}}`, afectando `backend/app/tools.py`, `backend/tests/test_llm_client.py` y `backend/tests/test_tools.py`.

---

## 2. Evolución por Sprint

### Sprint 1 — Walking Skeleton

- Infraestructura: Repo, Docker, CI con GitHub Actions
- Backend FastAPI modular con endpoint POST /chat
- Gestión de session_id en memoria
- Modelos Pydantic validados
- Harness de evaluación automatizado
- Latencia: 2.3s

### Sprint 2 — Datos Reales (Milestone 2)

- 21 issues planeados, 0 abiertos
- Curación de fichas técnicas con convencional naming `{categoria}_{fabricante}_{modelo}.pdf`
- Archivo de metadatos CSV/JSON con nombre_comercial, categoría, fabricante, modelo, ruta_s3
- `catalog_index.json` para System Prompt del LLM
- Integración AWS S3 (bucket `arte-chatbot-data/`)
- Herramienta `leer_ficha_tecnica(ruta)` con File Inputs
- Campo `source_documents` en responses
- Commit crítico `6797c543` migrando tools a Chat Completions API
- **Items NO completados ni mergeados**: Issues #45, #46, #47 (RAG/ChromaDB) cerrados como `not_planned` por cambio de arquitectura

### Sprint 3 — RAG Completo (Milestone 3)

- 20 issues planeados, 0 abiertos
- `classify_intent()` implementada con versiones de prompts guardadas en `backend/config/intent_prompt_versions.py`
- 5 intent_types: `FAQ`, `product_info`, `escalate_quote`, `escalate_technical`, `escalate_order`
- Clasificación vía prompt LLM (no keywords hardcodeadas), precisión ≥ 80% sobre 15 casos
- Evaluación humana con rúbrica (escala 1–5), precisión técnica promedio ≥ 3.5/5
- Harness de alucinación con regex `\\d+[\\.,]?\\d*\\s*(W|V|A|%|°C|kWh)`, tasa < 20%
- Ingesta de fichas hasta 50+
- **Sin PR mergeada verificada para los metrics de accuracy real**

### Sprint 4 — Inteligencia Conversacional (Milestone 4)

- 8 issues planeados, 0 abiertos
- `infer_user_profile()` clasificando en `novato`, `intermedio`, `experto` (solo primeros 2 turnos, default "intermedio")
- Adaptación de system prompt según perfil de usuario (tono/vocabulario diferente)
- `expand_query_with_context()` para resolución de referencias anafóricas, latencia adicional < +1.5s
- Ventana de sesión ampliada: `deque(maxlen=12)` (6 turnos × 2 roles), configurable via `SESSION_WINDOW_TURNS`
- Árbol de decisión de escalamiento cubriendo 5 intent_types, tasa falsos escalamientos < 15%
- **Sin PR mergeada verificada para resultados de evaluación de perfil**

### Sprint 5 — Evaluación (Milestone 5)

- 13 issues, 8 cerrados, 5 abiertos

**Cerrados (con PR mergeada verificada)**:
- #117 — Autenticación manual con CHAT_API_KEY via input field (sin credenciales embebidas)
- #70 — Rúbrica v2 con 3 dimensiones (precisión técnica, tono, escalamiento correcto), sesión con experto
- #69 — Dataset de ≥10 conversaciones anotadas (≥2 turnos cada una)
- #25 — Reporte de calidad del sistema (dashboard con métricas)
- #24 — Framework de evaluación humana con rúbrica, CLI de evaluación, checklists de UX y Seguridad

**Abiertos (sin PR mergeada)**:
- #118 — Test de integración final end-to-end
- #116 — Despliegue en AWS Fargate y S3 con CI/CD (IaC)
- #115 — Persistencia de sesiones con Redis/PostgreSQL
- #71 — Reporte de calidad comparativo S2 vs S5

---

## 3. Diff del Último Commit Asociado al Milestone 2

| Campo | Valor |
|-------|-------|
| **Commit** | `6797c543c27d4faec717a33263e67a81a173fb0d` |
| **Fecha** | 2026-04-05 |
| **Issue** | #15 (TS-03 — Pipeline de indexación del catálogo local) |
| **Mensaje** | `fix(#15): restore function wrapper in tools.py broken by merge` |

**Archivos modificados**:

1. `backend/app/tools.py` (+98, -94): Restructuración de herramientas `{name, description, parameters}` → `{type, function: {name, description, parameters}}` (Responses API → Chat Completions API)
2. `backend/tests/test_llm_client.py` (+1, -1): Actualización de acceso a nombres `t["name"]` → `t["function"]["name"]`
3. `backend/tests/test_tools.py` (+15, -14): Actualización de todos los tests para la nueva estructura anidada

---

## 4. Análisis de Checklists

### 4.1 Seguridad — Issue #126

| Category | Status | Severity |
|----------|--------|----------|
| LLM01: Prompt Injection | PARTIAL | MAJOR |
| LLM02: Insecure Output Handling | PARTIAL | MAJOR |
| LLM04: Model Denial of Service | PARTIAL | MAJOR |
| LLM06: Sensitive Information Disclosure | MISSING | CRITICAL |
| LLM07: Insecure Plugin Design | PARTIAL | CRITICAL |
| LLM08: Excessive Agency | PARTIAL | MAJOR |

**Issues críticos generados**:
- #128 — [CRITICAL] Synchronous endpoint blocking event loop
- #129 — Missing dependency injection in FastAPI endpoints
- #130 — [CRITICAL] Path traversal vulnerability in S3 tool access
- #131 — No input sanitization enabling prompt injection
- #132 — No PII handling or log sanitization

**Origen común**: Commit `861d61a` (feat: [TASK-M2-NEW2] Implement Tool Calling and File Inputs) — todas las vulnerabilidades LLM01, LLM04, LLM06, LLM07, LLM08 fueron introducidas en el mismo commit del 23 de marzo de 2026.

### 4.2 Código — Issue #127

| Category | Status | Severity |
|----------|--------|----------|
| Type Hints | PARTIAL | MINOR |
| SOLID Principles | NON-COMPLIANT | MAJOR |
| Async/Await | NON-COMPLIANT | CRITICAL |
| Error Handling | PARTIAL | MINOR |
| Testing | PARTIAL | MINOR |

**Issues críticos generados**:
- #128 — Synchronous `/chat` endpoint blocking event loop (`main.py:583` — `def` en lugar de `async def`). Re-introducido tras merge de branch async.
- #129 — Missing dependency injection: clientes instanciados a nivel de módulo (`main.py:138-140`) en lugar de via `Annotated[Depends()]`

### 4.3 UX — Issue #125

| Categoría | Resultado |
|-----------|-----------|
| Transparencia y Expectativas | ✅ Identificación como "Arte" · ✅ Sin simulación de humanidad · ✅ Límites claros · ❌ Fallback fuera de dominio |
| Retención de Contexto | ✅ Historial de sesión · ✅ Referencias anafóricas · ❌ Pérdida ante errores |
| Cualificación de Consulta | ✅ Preguntas lógicas · ❌ Recomendación de productos tardía (after 5 msgs) |
| Escalamiento | ⚠️ Detección parcial · ✅ Comunicación clara del tipo de agente · ❌ Mecanismo urgente no implementado |
| Tono y Profesionalismo | ✅ Consistente con marca B2B · ❌ Respuestas no concisas · ❌ Sin empatía en problemas |
| Accesibilidad | ❌ Verboso en preguntas sencillas · ❌ Sin link a fichas técnicas |
| Escalamiento a Humanos | ❌ No escala urgentemente (problemas seguridad eléctrica) |

---

## 5. Objetivos Específicos

| # | Objetivo | Estado | Evidencia |
|---|----------|--------|-----------|
| OE1 | Analizar y modelar el proceso actual de ventas | ✅ | Documentado con BPMN, niveles organizacionales, stakeholders |
| OE2 | Identificar fases automatizables y criterios de escalamiento | ✅ | Clasificador de 5 intent_types implementado en M3 |
| OE3 | Análisis comparativo de alternativas de chatbot | ❓ | Sin evidencia en issues ni ADRs publicados |
| OE4 | Prototipo de chatbot conversacional con consultas frecuentes y escalamiento | ✅ | Sistema funcional con File Inputs + clasificación + escalamiento |
| OE5 | Evaluaciones con métricas definidas | ✅ | Framework con rúbrica v1/v2, harness automatizado, dataset ≥10 |
| OE6 | Recomendaciones para integración futura | 🔄 | ADR-002/003 documentan infraestructura; fragmentado |

---

## 6. Features Prometidas vs. Implementadas

| Feature | Estado | Notas |
|---------|--------|-------|
| Conversación natural sobre productos fotovoltaicos | ✅ | `leer_ficha_tecnica` + File Inputs |
| Respuesta a FAQs (formas de pago, garantía, tiempos) | ✅ | Intent `FAQ` en M3 |
| Clasificación de perfil de usuario (novato/intermedio/experto) | ✅ | M4 — `infer_user_profile()` + adaptación de tono |
| Detección de escalamiento humano | ✅ | M4 — árbol de decisión para 5 intent_types |
| Mantenimiento de contexto multi-turno | ✅ | M4 — `deque(maxlen=12)`, resolución anafórica |
| Tono profesional con vocabulario técnico | ✅ | M4 — adaptación por perfil |
| Backend FastAPI con /chat | ✅ | Con PR mergeada |
| Frontend de prueba HTML/CSS/JS | ✅ | Existe en repo |
| Harness de evaluación automatizado | ✅ | `evaluation/` con latencia, tasa escalamiento |
| Evaluación humana con rúbrica | ✅ | `evaluation/rubric_v1.md` → v2 |
| Base de conocimiento curada (mínimo 50 fichas) | ✅🚩 | **Superado**: ~240 fichas en S3 |
| Catalog_index.json + File Inputs | ✅ | Implementado desde S2 |
| Integración con AWS S3 | ✅ | bucket `arte-chatbot-data/` |

---

## 7. Cambios de Alcance

| Cambio | Referencia | Estado |
|--------|-----------|--------|
| RAG + ChromaDB → File Inputs + Tool Calling | Documento S2 (pág. 13) + ADR-002/003 | ✅ Implementado |
| Integración con Chatwoot/Odoo explícitamente fuera del alcance | Documento S2 (pág. 12) | ✅ Correcto |
| Despliegue en producción explícitamente fuera del alcance | Documento S2 (pág. 12) | ✅ Parcial — M5 #116 abierto |

---

## 8. Qué Quedó Faltando

*Nota: Esta sección resume los gaps identificados hasta la fecha de corte (29 de abril de 2026). Para el Demo Day, se presentan como trabajo futuro documentado y priorizado.*

### 8.1 Seguridad y Código (Crítico — requiere atención antes de producción)

| Gap | Severidad | Prioridad post-demo |
|-----|-----------|---------------------|
| Endpoint `/chat` síncrono bloqueando el event loop | CRITICAL | Alta |
| Missing dependency injection en FastAPI | MAJOR | Alta |
| Path traversal en S3 tool access (`ruta_s3` sin validación) | CRITICAL | Alta |
| Prompt injection — input sin sanitizar | MAJOR | Alta |
| Sin PII handling ni log redaction | CRITICAL | Alta |
| Sin rate limiting (`slowapi`) | MAJOR | Media |
| Sin timeouts en LLM calls ni tool calls | MAJOR | Media |
| Sesiones en RAM sin persistencia ni encriptación | MAJOR | Media |

### 8.2 UX y Experiencia de Usuario

| Gap | Estado | Para demo day |
|-----|--------|---------------|
| Fallback fuera de dominio redirige útilmente | ❌ No implementado | Se documenta como mejora futura |
| Recomendación de productos tardía (after 5 msgs) | ❌ No implementado | Se documenta como mejora futura |
| Escalamiento urgente (seguridad eléctrica) no existe | ❌ No implementado | Se documenta como mejora futura |
| Respuestas excesivamente verbosas | ❌ No resuelto | Se documenta como mejora futura |
| Sin link a fichas técnicas en respuestas | ❌ No implementado | Se documenta como mejora futura |
| Transición fluida a agente humano sin repetir info | ❌ No implementado | Se documenta como mejora futura |
| Privacidad — no informa al usuario cómo se usan sus datos | ❌ No implementado | Se documenta como mejora futura |

### 8.3 Datos sin Verificación Accesible

*Estos items no tienen comentarios con resultados numéricos ni PR mergeada verificada:*

| Gap | Razón |
|-----|-------|
| Métricas reales de latencia promedio post-S5 | Issue #71 (reporte S2 vs S5) abierto — sin datos |
| Resultados concretos de evaluación humana | Issue #69 cerrado, sin evidencia de PR ni resultados |
| Tasa de escalamiento real vs baseline S1 | Issue #23 cerrado, sin dataset ni resultados |
| Accuracy real del clasificador de intent (≥80% target) | Issue #62 cerrado, sin datos numéricos |
| Evaluación con sesión de experto real | Issue #70 cerrado, sin evidencia en comentarios |

---

## 9. Resumen de Entregables

| Entregable | Estado | Notas |
|------------|--------|-------|
| E1 — Código fuente + documentación técnica | ✅ | Repo con modularidad, ADRs, README |
| E2 — Base de conocimiento (≥50 fichas) | ✅🚩 | **Superado**: ~240 fichas en S3 |
| E3 — Sistema funcional desplegado | 🔄 | backend funcional en local; AWS Fargate (#116) abierto |
| E4 — Dataset + evaluación humana + informe | 🔄 | Dataset ≥10 existe; reporte S2 vs S5 (#71) abierto |
| E5 — Documento recomendaciones producción | ❌ | No encontrado como documento; fragmentos en ADRs |
| E6 — Presentación ejecutiva | ❌ | No encontrada en repo |

---

## 10. Estado Actual del Sistema

- **~240 productos** subidos en S3 (incremento desde 15 fichas iniciales hasta远超 el target de 50)
- **Arquitectura File Inputs** que demostró ser más precisa y mantenible que RAG vectorial para el dominio de productos similares
- **Deuda técnica significativa** en seguridad (5 categorías en PARTIAL/MISSING, 2 CRITICAL) y código (2 issues CRITICAL sin resolver)
- **UX con gaps conocidos** que no fueron resueltos completamente (verbosidad, fallback, escalamiento urgente)
- **5 issues abiertos** en M5 sin PR mergeada, incluyendo despliegue IaC, persistencia de sesiones, test de integración, y reporte comparativo final
