<!-- Slide number: 1 -->

![preencoded.png](Image0.jpg)
Arte Chatbot — Actualización Sprint 2 al Sprint 5
Proyecto Aplicaventic — Equipo

Ricardo Arias
Líder

Sofia
Navales

Juan
Pretel

Mario
Gutiérrez
Medellín, Abril 29 de 2026

### Notes:

<!-- Slide number: 2 -->

📊 Contexto: De Sprint 2 a Sprint 5

Problema original
Visión
1,200 leads/mes → 3,200 (2026)
2 vendedores abrumados
15% quedan sin atender 3-4h
80% tiempo en consultas repetitivas

Chatbot RAG self-hosted
Automatización L1
Liberar vendedores para valor alto

Del MVP al Sistema Productivo
15 fichas → ~240 fichas en S3
Arquitectura RAG → File Inputs
Concepto → Evaluación formal con checklists

### Notes:

<!-- Slide number: 3 -->

🔄 Evolución por Sprint

Sprint 1
Sprint 2
Sprint 3
Sprint 4
Sprint 5
Walking Skeleton
Datos Reales
RAG Completo
Inteligencia Conversacional
Evaluación
✓ FastAPI /chat
✓ 15 fichas en S3
✓ File Inputs
✓ Catalog index
✓ Clasificador intent
✓ Rúbrica + harness
✓ Perfil usuario
✓ Contexto multi-turno
✓ Árbol escalamiento
✓ Dataset 10 conv.
✓ Framework eval.
✓ Auth manual
🔄 IaC AWS Fargate
🔄 Persistencia sesión
🔄 Test end-to-end
🔄 Reporte S2 vs S5

### Notes:

<!-- Slide number: 4 -->

⚡ Cambio de Arquitectura: RAG → File Inputs

Problema
Solución
15 productos altamente similares
Solo cambian 1-2 parámetros
→ RAG confunde entre modelos
→ Tasa alucinación alta
→ Chunking no preserva diferencias
File Inputs (LLM nativo)
PDF descarga desde S3
→ Se adjunta a llamada LLM
→ LLM procesa documento completo
→ Sin confusión entre modelos
→ Precisión verificable
→ Sin índice vectorial

Decisión documentada en ADR-003 y ADR-002

### Notes:

<!-- Slide number: 5 -->

📈 Estado Actual del Catálogo

Métrica
Sprint 2
Sprint 5 (Actual)
Fichas técnicas
15
~240
Cobertura
Parcial
Catálogo completo
Formatos
PDF no normalizado
Normalizados por categoría
Indexación
Catalog_index.json
Catalog_index.json + metadata completo
Ingesta
Manual
Script automatizado

Superamos el target original de 50 fichas
Incremento de 16x en contenido disponible

### Notes:

<!-- Slide number: 6 -->

🏗️ Arquitectura: Componentes Implementados

Backend (FastAPI)
├── /chat endpoint (POST)
├── SessionManager (en RAM)
├── S3Client (boto3)
├── LLMClient (OpenAI/Anthropic)
├── FileInputsClient
└── Tool Calling (leer_ficha_tecnica, buscar_producto)

Infraestructura
├── AWS S3 (arte-chatbot-data/)
│   ├── raw/paneles|inversores|controladores|baterias/
│   └── index/catalog_index.json
├── GitHub Actions CI/CD
└── Docker Compose

Frontend
└── HTML/CSS/JS de prueba

Evaluación
├── Harness automatizado (latencia, hallucination)
├── Rúbrica v1 → v2 (precisión, tono, escalamiento)
└── Dataset ≥10 conversaciones anotadas

### Notes:

<!-- Slide number: 7 -->

🎯 Features Implementadas

✅ Conversación natural sobre productos fotovoltaicos
✅ Respuesta a FAQs (formas de pago, garantía, tiempos)
✅ Clasificación de perfil de usuario (novato/intermedio/experto)
✅ Detección de escalamiento humano (5 intent_types)
✅ Mantenimiento de contexto multi-turno (6-20 turnos)
✅ Resolución de referencias anafóricas
✅ Adaptación de tono/vocabulario según perfil
✅ Tono profesional con vocabulario técnico del sector
✅ Backend FastAPI con /chat funcional
✅ Frontend de prueba HTML/CSS/JS
✅ Harness de evaluación automatizado
✅ Evaluación humana con rúbrica formal
✅ Base de conocimiento curada (~240 fichas)
✅ Integración con AWS S3

### Notes:

<!-- Slide number: 8 -->

📋 Clasificador de Intenciones (Sprint 3)

5 Intent Types implementados

FAQ
product_info
escalate_quote
escalate_technical
escalate_order
Preguntas frecuentes
Consultas sobre productos
Solicitud de cotización
Soporte técnico complejo
Pedidos y seguimiento

Clasificación vía prompt LLM (no keywords hardcodeadas)
Precisión target: ≥ 80% sobre 15 casos
Accuracy real: Sin datos verificados en comentarios

### Notes:

<!-- Slide number: 9 -->

🔍 Análisis de Seguridad — Issue #126

| Category | Status | Severity |
|----------|--------|----------|
| LLM01: Prompt Injection | PARTIAL | MAJOR |
| LLM02: Insecure Output Handling | PARTIAL | MAJOR |
| LLM04: Model DoS | PARTIAL | MAJOR |
| LLM06: Sensitive Info Disclosure | MISSING | CRITICAL |
| LLM07: Insecure Plugin Design | PARTIAL | CRITICAL |
| LLM08: Excessive Agency | PARTIAL | MAJOR |

Issues generados para demo day:
#128 — Synchronous endpoint (CRITICAL)
#130 — Path traversal S3 (CRITICAL)
#131 — Prompt injection (MAJOR)
#132 — Sin PII handling (CRITICAL)

Origen: Commit 861d61a (Marzo 23, 2026)

### Notes:

<!-- Slide number: 10 -->

🔍 Análisis de Código — Issue #127

| Category | Status | Severity |
|----------|--------|----------|
| Type Hints | PARTIAL | MINOR |
| SOLID Principles | NON-COMPLIANT | MAJOR |
| Async/Await | NON-COMPLIANT | CRITICAL |
| Error Handling | PARTIAL | MINOR |
| Testing | PARTIAL | MINOR |

Problemas críticos:
def chat_endpoint (sync) → Bloquea event loop
Clientes a nivel de módulo → Sin dependency injection
No hay tests para catalog.py

### Notes:

<!-- Slide number: 11 -->

🔍 Análisis de UX — Issue #125

Lo que funciona bien
Lo que necesita mejoras

Transparencia: Bot se identifica como "Arte"
Contexto: Historial y referencias anafóricas ✅
Escalamiento: Comunicación clara del tipo de agente ✅
Tono: Consistente con marca B2B ✅

Fallback fuera de dominio: No redirige útilmente ❌
Recomendación de productos: Tarda 5+ mensajes ❌
Escalamiento urgente: No existe (seg. eléctrica) ❌
Respuestas: Excesivamente verbosas ❌
Links a fichas: No se incluyen en respuestas ❌

### Notes:

<!-- Slide number: 12 -->

⚠️ Deuda Técnica — items para producción

Prioridad Alta (antes de producción)
🔴 Endpoint síncrono /chat (bloquea event loop)
🔴 Path traversal en acceso S3
🔴 Sin input sanitization (prompt injection)
🔴 Sin PII handling ni log redaction
🟡 Missing dependency injection FastAPI
🟡 Sin rate limiting

Prioridad Media (futuro cercano)
🟡 Sesiones en RAM sin persistencia
🟡 Sin timeouts en LLM/tool calls
🟡 Sin circuit breaker

### Notes:

<!-- Slide number: 13 -->

📦 Entregables: Estado Actual

E1 — Código fuente + documentación
E2 — Base de conocimiento (≥50 fichas)
E3 — Sistema funcional desplegado
E4 — Dataset + evaluación humana
E5 — Documento recomendaciones
E6 — Presentación ejecutiva

✅ Repo completo con modularidad y ADRs
✅ Superado: ~240 fichas en S3
🔄 Backend local OK · AWS Fargate abierto
🔄 Dataset existe · Reporte S2 vs S5 abierto
❌ No encontrado como documento
❌ No encontrada en repo

### Notes:

<!-- Slide number: 14 -->

📋 Comparativa: Prometido vs Implementado

Feature
Conversación natural productos
FAQs
Clasificación perfil usuario
Escalamiento humano
Contexto multi-turno
Adaptación tono/vocabulario
Backend FastAPI
Frontend prueba
Harness evaluación
Evaluación humana
Base conocimiento (≥50)
File Inputs + catalog_index
Integración S3

Estado
✅ Implementado
✅ Implementado
✅ Implementado
✅ Implementado
✅ Implementado
✅ Implementado
✅ Implementado
✅ Implementado
✅ Implementado
✅ Implementado
✅ Superado (~240)
✅ Implementado
✅ Implementado

### Notes:

<!-- Slide number: 15 -->

🎯 Objetivos Específicos: Estado

OE1 — Analizar y modelar proceso ventas
OE2 — Identificar fases automatizables + escalamiento
OE3 — Análisis comparativo alternativas chatbot
OE4 — Prototipo chatbot con escalamiento
OE5 — Evaluaciones con métricas
OE6 — Recomendaciones integración futura

✅ Completado (documentado con BPMN)
✅ Completado (5 intent_types)
❓ Sin evidencia en issues/ADRs publicados
✅ Completado (sistema funcional)
✅ Completado (rúbrica + harness)
🔄 Parcial (fragmentado en ADRs)

### Notes:

<!-- Slide number: 16 -->

📊 Métricas del Sistema (Sprint 2 al 5)

Métrica
Precisión técnica
Tasa alucinación
Latencia p95
Cobertura catálogo
Docs rastreables
Costo/conversación

S1
-
-
2.3s
0%
0%
-

S2
3.5/5
<20%
<3s
100%
100%
<$0.05

S5
≥3.5/5 ✅
<20% ✅
<3s ✅
100% ✅
100% ✅
<$0.05 ✅

Métricas target cumplidas según harness

### Notes:

<!-- Slide number: 17 -->

🔜 Qué queda faltando — Demo Day

Seguridad
Code Quality
UX
Integración

Path traversal S3
Endpoint síncrono
Missing DI
Sin rate limiting
Sin PII handling

Fallback fuera dominio
Verbosidad respuestas
Sin links a fichas
Escalamiento urgente

IaC AWS Fargate
Persistencia sesiones
Test end-to-end
Reporte S2 vs S5

Todo esto se documenta como trabajo futuro
priorizado para antes de producción

### Notes:

<!-- Slide number: 18 -->

🎯 CIERRE — Sprint 2 al 5

Logros Clave

✅ Cambio de arquitectura RAG → File Inputs
✅ Sistema funcional con ~240 fichas en S3
✅ Clasificación de intents y escalamiento
✅ Contexto multi-turno con perfil de usuario
✅ Framework de evaluación con rúbrica formal
✅ Checklists de seguridad, código y UX
✅ Deuda técnica identificada y priorizada

Para el Demo Day

🎯 Demostrar conversación funcional
🎯 Mostrar clasificación de intents en vivo
🎯 Presentar gaps y plan de remediación
🎯 Proyectar siguiente fase: producción

### Notes:
