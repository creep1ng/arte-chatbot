# Security Checklist — LLM Chatbot Arte

Checklist de seguridad para el chatbot Arte basada en OWASP Top 10 for Large Language Model Applications y MITRE ATLAS. Usar para auditar código y arquitectura.

---

## LLM01: Prompt Injection

- [ ] Los inputs del usuario son sanitizados antes de ser procesados
- [ ] No se permite inyección de prompts через usuario (el system prompt no es modificable por usuario)
- [ ] Las herramientas (`leer_ficha_tecnica`) validan sus argumentos antes de ejecutarse
- [ ] Se implementa rate limiting por IP/usuario para prevenir flooding de prompts
- [ ] Los logs no exponen contenido de prompts del sistema
- [ ] Las respuestas del LLM son validadas para detectar posible prompt leakage

**Referencias**: OWASP LLM01, MITRE ATLAS: LLM Injection Techniques

---

## LLM02: Insecure Output Handling

- [ ] Las respuestas del LLM son tratadas como no confiables y sanitizadas antes de enviarse al cliente
- [ ] Se valida que las respuestas no contengan información sensible que no deba ser expuesta
- [ ] No se permite rendering de contenido HTML/JS sin sanitización en respuestas del chatbot
- [ ] Los outputs de herramientas son validados contra esquemas esperados antes de procesarse
- [ ] Se limita el tamaño de respuestas del LLM para evitar disclosure de datos del sistema

**Referencias**: OWASP LLM02

---

## LLM03: Training Data Poisoning

- [ ] Los documentos de fichas técnicas en S3 son la única fuente de información factual
- [ ] No se usa fine-tuning con datos de conversaciones reales de usuarios
- [ ] El índice de catálogo (`catalog_index.json`) es versionado y auditable
- [ ] Existe validación de que las fichas técnicas descargadas no hayan sido modificadas (checksums)

**Referencias**: OWASP LLM03, MITRE ATLAS: Data Poisoning

---

## LLM04: Model Denial of Service

- [ ] Se implementa rate limiting en el endpoint `/chat` (máx X requests/min por IP)
- [ ] Existe límite de tokens por request (máx 2000 tokens en, 1000 tokens out)
- [ ] Los PDFs se limitan en tamaño antes de procesarse (máx 10MB)
- [ ] Se implementa timeout en llamadas al LLM (máx 30 segundos)
- [ ] Existe circuit breaker para detectar patrones de DoS y responder con 503 temporal
- [ ] El número máximo de sesiones concurrentes está limitado

**Referencias**: OWASP LLM04, MITRE ATLAS: LLM DoS Techniques

---

## LLM05: Supply Chain Vulnerabilities

- [ ] Las dependencias del proyecto están bloqueadas a versiones específicas
- [ ] Se usa únicamente PyPI oficial (no mirrors)
- [ ] Los docker images base están hardenizadas y minimalistas
- [ ] Existe SBOM (Software Bill of Materials) documentado
- [ ] Las API keys de servicios externos no están hardcodeadas en el código

**Referencias**: OWASP LLM05

---

## LLM06: Sensitive Information Disclosure

- [ ] El bot no expone datos de sessões anteriores a otros usuarios
- [ ] Los logs no contienen PII ( personally identifiable information) de usuarios
- [ ] Las credenciales AWS se gestionan via environment variables, nunca en código
- [ ] Se implementa sanitización de outputs para filtrar PII accidental del LLM
- [ ] Existe política de retención de logs (máx 30 días)
- [ ] Los archivos temporales de PDFs se borran después de cada procesamiento

**Referencias**: OWASP LLM06, MITRE ATLAS: PII Extraction

---

## LLM07: Insecure Plugin Design

- [ ] Las tools de File Inputs validan que el archivo solicitado existe antes de descargarlo
- [ ] Los paths de S3 son normalizados para evitar path traversal (`../`)
- [ ] La tool `leer_ficha_tecnica` solo permite acceso a la carpeta `raw/` del bucket, no a otros directorios
- [ ] Los timeouts de herramientas son estrictos y no permiten ejecución indefinida
- [ ] Los errores de herramientas no exponen información interna del sistema al LLM

**Referencias**: OWASP LLM07, MITRE ATLAS: Tool Exploitation

---

## LLM08: Excessive Agency

- [ ] El bot no puede ejecutar acciones destructivas sin confirmación explícita del usuario
- [ ] Las tools tienen permisos limitados (solo lectura en S3, sin escritura)
- [ ] No existe capacidad de enviar emails o mensajes externos desde el chatbot
- [ ] El bot solo puede recomendar próximos pasos, no ejecutarlos
- [ ] Se audita regularmente qué tools están activas y sus permisos

**Referencias**: OWASP LLM08, MITRE ATLAS: Overtrusting Tools

---

## LLM09: Overreliance

- [ ] Las respuestas del bot citan la fuente de información (ficha técnica específica cuando aplica)
- [ ] Existe disclaimer cuando el modelo no está seguro de la precisión de una respuesta
- [ ] El bot indica cuando está proporcionando información general vs. específica de una ficha técnica
- [ ] Se implementa monitoreo de alucinaciones (`evaluation/hallucination_check.py`)
- [ ] Existe canal para que usuarios reporten respuestas incorrectas

**Referencias**: OWASP LLM09, MITRE ATLAS: Overreliance Failures

---

## LLM10: Model Theft

- [ ] No se exponen endpoints que permitan extraer información del modelo o prompt
- [ ] Las llamadas al LLM se hacen vía APIs oficialessolo (no llamadas directas a modelos desplegados)
- [ ] Los logs de auditoría permiten detectar patrones de extracción
- [ ] El acceso a documentación interna del sistema está restringido

**Referencias**: OWASP LLM10

---

## Checklist General de Seguridad

- [ ] Secrets (API keys, credenciales) están en `.env` y `.env` está en `.gitignore`
- [ ] Todas las comunicaciones son sobre HTTPS (incluir reverse proxy en docker-compose)
- [ ] El backend no corre como root dentro del contenedor
- [ ] Los headers de seguridad (CSP, X-Frame-Options, etc.) están configurados si hay frontend
- [ ] Se realiza scanning de dependencias con `pip-audit` o herramienta similar
- [ ] Existe documento de respuesta a incidentes (incident response plan)
- [ ] Los logs de error no exponen stack traces en producción

---

## Referencias Cruzadas

| OWASP LLM | MITRE ATLAS Táticas | Arte Chatbot Componente |
|-----------|---------------------|------------------------|
| LLM01 | Prompt Injection, Context Manipulation | `backend/app/chat.py`, prompt construction |
| LLM02 | Output Exfiltration | Response sanitization layer |
| LLM04 | Resource Exhaustion | Rate limiting, timeouts |
| LLM06 | PII Extraction, Training Data Extraction | S3 client, log sanitization |
| LLM07 | Tool Poisoning, Tool Injection | `leer_ficha_tecnica` tool definition |
| LLM08 | Overtrusting Tools | Tool permissions, agent scope |

---

## Referencias
- OWASP Top 10 for LLM Applications v1.1 (2024) — https://genai.owasp.org/llm-top-10/
- MITRE ATLAS (Adversarial Threat Landscape) — https://atlas.mitre.org/
- OWASP WebGoat LLM Lab Exercises