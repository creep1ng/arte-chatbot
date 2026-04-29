<!-- Slide number: 1 -->

![preencoded.png](Image0.jpg)
Arte Chatbot — Presentación Sprint 1 & 2
Proyecto Aplicaventic — Equipo

Ricardo Arias
Líder

Sofia

Juan

Mario
Medellín, Marzo 25 de 2026

### Notes:

<!-- Slide number: 2 -->

![preencoded.png](Image0.jpg)
📊 Contexto del Proyecto

Problema
Visión
1,200 leads/mes → 3,200
2 vendedores abrumados
15% quedan sin atender 3-4h
Margen de mejora: 80% tiempo en consultas repetitivas
Chatbot RAG self-hosted
Automatización L1
Liberar vendedores para valor alto

### Notes:

<!-- Slide number: 3 -->
🔄 Metodología: SCRUM + Walking Skeleton + TDSP

Walking Skeleton
Daily Asincrónica
TDSP Cíclico
Sprint 1: Corte vertical completo (punta a punta)
→ Skeleton
→ Sprint 2: Carne
→ Sprint 3: Calidad
Updates en GitHub cuando trabajas
Sincro semanal
Miércoles 30 min
Resolver bloqueos
Cada sprint:
→ Business
→ Data
→ Modeling
→ Deploy
→ Feedback

### Notes:

<!-- Slide number: 4 -->
Matriz de Stakeholders del Proyecto
Identificamos los principales interesados en el proyecto "Arte Chatbot" para entender mejor sus expectativas e influencia.

![preencoded.png](Image0.jpg)
Alto interés

![preencoded.png](Image4.jpg)

![preencoded.png](Image3.jpg)
Desarrolladores del proyecto y Administrador de Arte
Profesora
Bajo poder
Alto poder

![preencoded.png](Image1.jpg)

![preencoded.png](Image2.jpg)
Clientes y Equipo de venta
Bajo interés
Esta matriz nos ayuda a priorizar la comunicación y la gestión de expectativas con cada grupo de interesados clave.

### Notes:

<!-- Slide number: 5 -->
✅ Sprint 1 — Estado: 100% Completado

Tareas Cumplidas
Resultado
✓ Infraestructura (Repo, Docker, CI)
✓ Backend FastAPI modular
✓ Endpoint POST /chat
✓ Gestión sessionid en memoria
✓ Modelos Pydantic validados
✓ Harness de evaluación
✓ Documentación completa
✓ Latencia 2.3s
✓ Endpoint /chat funcional
✓ Docs Swagger listos
✓ Sistema desplegable
✓ Ready para Sprint 2
✓ CI/CD pasando
✓ GitHub Actions OK

Walking Skeleton: ✓ Usuario puede enviar mensaje y recibir respuesta

![preencoded.png](Image0.jpg)

### Notes:

<!-- Slide number: 6 -->
⚡ Cambio de Alcance: Abandonamos RAG Tradicional

Situación
Solución Adoptada (ADR-003)
Catálogo: 15 productos
Solo cambian 1-2 parámetros
→ RAG confunde entre similares
→ Tasa alucination alta
File Inputs (LLM nativo)
Descargamos PDF de S3
→ Lo adjuntamos a la llamada
→ LLM ve documento completo
→ Sin confusión entre modelos

Problema

Solución
ChromaDB + RAG = ERROR
File Inputs = PRECISIÓN

Reversible
✅ Costo: tokens vs complexity
✅ Trade-off monitoreable
⚠️ Sprint 4: Reevaluar según uso
Si volumen crece 10x → Sprint 4: Migrar a RAG mejorado

### Notes:

<!-- Slide number: 7 -->
🏗️ Arquitectura: Infraestructura S3

arte-chatbot-data/ (AWS S3)
Flujo
Usuario pregunta
Backend → leer_ficha()
Descarga PDF desde S3
Adjunta a LLM (File Input)
LLM responde con contexto
Backend retorna

├── raw/
│   ├── paneles/
│   ├── inversores/
│   ├── controladores/
│   └── baterias/
│
└── [15 fichas técnicas PDF]

├── index/
│   └── catalog_index.json

Ventajas:
✓ Acceso estandarizado
✓ Multi-ambiente (dev, CI, prod)
✓ Credentials seguros
Docs: ADR-002, ADR-003

### Notes:

<!-- Slide number: 8 -->
🎯 Sprint 2 — Tareas Planificadas (1 Semana)

TASK-12: Integrar S3 descarga
1
DoD: leer_ficha() retorna PDF

TASK-13: Ingestar 15 fichas
2
DoD: 15 archivos en S3 listos

TASK-14: Integrar retrieval /chat
3
DoD: Endpoint usa PDFs reales

TASK-15: source_documents field
4
DoD: Response incluye metadata

TASK-16: Harness evaluación v2
5
DoD: Auto-log de docs usados
Métrica Base S1 → Meta S2

Precisión técnica
Alucinación
Latencia
Docs rastreables
- → 3.5/5
- → <20%
2.3s → <3s
0% → 100%

Cobertura catálogo
0% → 100%

### Notes:

<!-- Slide number: 9 -->
📈 Métricas Sprint 1 → Sprint 2

Métrica
S1
S2 Target
Método Evaluación

Precisión Técnica
-
3.5/5
Validación manual

Tasa Hallucination
-
<20%
Regex contra PDFs

Latencia p95
2.3s
<3s
Timing automático

Docs Rastreables
0%
100%
Parse response JSON

Cobertura Catálogo
0%
100%
Coverage test suite

Costo/conversación
-
<$0.05
OpenAI usage logs
Evaluación

✓ Automática
✓ Manual
Latencia, coverage, hallucination
5-8 ingenieros de Arte validan respuestas reales

### Notes:

<!-- Slide number: 10 -->
⏱️ Línea de Tiempo Acelerada

Plan Original: 6 sprints × 2 semanas = 12 semanas

![preencoded.png](Image0.jpg)
Plan Actual: Entrega en fecha X
Sprint 1
Sprint 3
1 SEMANA
✓ Completado hoy
Refinamiento
(1 semana)

1
2
3
4

Sprint 2
Sprint 4
1 SEMANA
Termina [fecha]
Evaluation y recomendaciones
(1 semana)
Impacto

Ritmo acelerado
Scope congelado
Prioridad
MVP correcto
Menos ceremonia, más ejecución
NO nuevas features hasta entrega
Calidad > perfección
> nada incompleto

### Notes:

<!-- Slide number: 11 -->
📦 Repositorio y Estado
GitHub: https://github.com/creep1ng/arte-chatbot

Commits Sprint 1
Estructura Repo
✓ backend/main.py: Endpoint /chat
✓ backend/app/s3_client.py: S3 integration
✓ backend/app/tools.py: leer_ficha_tecnica() helper
✓ docker-compose.yml: Orquestación
✓ .github/workflows/ci.yml: CI/CD pipeline
✓ docs/adr/002.md: S3 decision
✓ docs/adr/003.md: File Inputs decision

arte-chatbot/
├── backend/app/
│   ├── main.py (FastAPI)
│   ├── s3_client.py (AWS S3)
│   └── tools.py (LLM tools)
├── docs/adr/
│   (Architecture decisions)
├── .github/workflows/
│   (CI/CD)
└── README.md (Setup + docs)
CI/CD: ✓ GitHub Actions — Lint, Build, Health Check

### Notes:

<!-- Slide number: 12 -->
📋 Artefactos de Documentación

ADR-001: Arquitectura Inicial
Decisión: FastAPI + S3 + OpenAI
Justificación: Simplicidad, escalabilidad
Trade-offs: Self-hosted vs cloud

ADR-002: Infraestructura S3
Decisión: AWS S3 para datos + fichas técnicas
Justificación: Multi-ambiente, credenciales seguros
Trade-offs: Costo vs acceso estandarizado

ADR-003: File Inputs vs RAG CRÍTICO
Decisión: Procesamiento de archivos nativo de LLM

![preencoded.png](Image0.jpg)
Justificación: Alta similitud de documentos → RAG propenso a errores
Trade-offs: Tokens vs complejidad
Reversible: Reevaluar en Sprint 4 según volumen
Ubicación: /docs/adr/
Formato: Contexto, Decisión, Justificación, Consecuencias, Riesgos

### Notes:

<!-- Slide number: 13 -->
⚠️ Riesgos y Próximos Pasos
Riesgos identificados (Sprint 2)

1
2
3
Límite tamaño archivo
Costo de tokens (File Inputs)
Latencia S3
Si PDF > 100MB, el LLM podría rechazarlo.
Cada PDF adjunto implica un mayor consumo de tokens que el enfoque RAG.
La descarga de PDFs desde AWS S3 podría añadir hasta 500ms a la respuesta.
Mitigación: Normalizar fichas técnicas a un estándar en la fase de ingesta.
Mitigación: Monitorear el costo por mensaje, con una meta de <$0.05.
Mitigación: Implementar caching local para los PDFs más solicitados.
Bloqueos a resolver esta semana
¿Credenciales AWS asignadas al equipo de desarrollo?
¿Fichas técnicas de productos formalizadas en formato estándar?
¿Acceso a Nextcloud de Arte validado para la gestión de documentos?
Próximas semanas: Hoja de ruta

1
2
3
Sprint 2
Sprint 3
Sprint 4
Integración de datos reales en producción.
Mejora continua de la precisión y el contexto de las respuestas.
Evaluación completa del sistema y recomendaciones estratégicas.

### Notes:

<!-- Slide number: 14 -->

![preencoded.png](Image0.jpg)
🎯 CIERRE Y PREGUNTAS
Logros Clave del Sprint 1

✅ Walking Skeleton
✅ Decisión Arquitectónica
Funcional (usuario → respuesta)
Informada (ADR-003: File Inputs)

✅ Infraestructura Declarada
✅ Metodología Adaptada
Docker, GitHub Actions, S3
TDSP + Scrum a la realidad del equipo
Enfoque para el Sprint 2

![preencoded.png](Image1.jpg)

![preencoded.png](Image2.jpg)

Conectar Datos Reales
Validar Precisión Técnica
Integrar el catálogo de productos actual
Asegurar la calidad de las respuestas

![preencoded.png](Image3.jpg)

Mantener Línea de Tiempo
Preservar el ritmo acelerado de entrega

### Notes:
