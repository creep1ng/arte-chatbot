# Diagnóstico de Fallos en Tool Calls - Arte Chatbot

## Resumen Ejecutivo

Durante la investigación de la PR #163 y los resultados del evaluation harness, se identificaron **4 bugs críticos** que causaban fallos sistemáticos en las tool calls del chatbot. Todos han sido corregidos y verificados en el branch `carbonated-leopon`.

---

## Bug 1: Catalog vacío por mismatch de clave JSON

**Archivo:** `backend/app/catalog.py:54-55`
**Severidad:** CRÍTICA

### Problema
El `catalog_index.json` en S3 usa la clave española `"productos"`, pero el código Python esperaba `"products"` (inglés). Esto causaba que el catálogo cargara con **0 productos**.

### Impacto
Todas las búsquedas de producto fallaban con:
```
No products found in catalog for categoria='paneles'...
```

### Fix
```python
# Antes (fallaba silenciosamente)
products_data = index_data.get("products", [])

# Después (soporta ambas claves)
products_data = index_data.get("productos", index_data.get("products", []))
```

### Verificación
```
Catalog loaded, products: 159  # Antes: 0
```

---

## Bug 2: Tool definitions en formato Chat Completions API

**Archivo:** `backend/app/tools.py`
**Severidad:** CRÍTICA

### Problema
Las definiciones de herramientas estaban anidadas bajo una clave `function` (formato Chat Completions API), pero el backend usa `client.responses.create()` (Responses API). OpenAI **ignoraba silenciosamente** los parámetros, permitiendo que el modelo emitiera objetos de argumentos vacíos `{}`.

### Impacto
El LLM no recibía el schema de parámetros, por lo que pasaba:
```
Tool call parameters: ruta_s3=None, categoria=None, fabricante=None, modelo=None
```

### Fix
Aplanar las definiciones al formato Responses API:
```python
# Antes (Chat Completions format - ignorado)
{"type": "function", "name": "...", "function": {"parameters": {...}}}

# Después (Responses API format - funciona)
{"type": "function", "name": "...", "parameters": {...}}
```

También se actualizó `backend/main.py` (`_log_tool_definitions`) y los tests.

### Verificación
Después del fix, el LLM ahora pasa parámetros reales:
```
Tool call parameters: categoria=paneles, fabricante=Eco Green, modelo=275W
```

---

## Bug 3: AttributeError en buscar_producto con BaseModel

**Archivo:** `backend/main.py:450-451, 533-534`
**Severidad:** ALTA

### Problema
Cuando `buscar_producto` encontraba productos e intentaba formatear los resultados, usaba `.get()` sobre objetos `ProductVariant` (Pydantic BaseModel). Los BaseModel **no tienen método `.get()`** — solo los dicts.

### Impacto
```
AttributeError: 'ProductVariant' object has no attribute 'get'
```
El tool call fallaba y el error se propagaba al usuario.

### Fix
Reemplazar `.get()` con `getattr()`:
```python
# Antes (AttributeError)
modelo = variante.get("modelo", "Sin nombre")
params = variante.get("parametros_clave", {})

# Después (funciona)
modelo = getattr(variante, "modelo", None) or "Sin nombre"
params = getattr(variante, "parametros_clave", None) or {}
```

---

## Bug 4: validate_s3_path rechaza rutas con prefijo raw/

**Archivo:** `backend/app/tools.py:26-50`
**Severidad:** ALTA

### Problema
El `catalog_index.json` almacena rutas S3 con prefijo `raw/` (ej: `raw/paneles/ECO GREEN 275-290W.pdf`), pero `validate_s3_path()` solo aceptaba categorías directamente (`paneles/...`).

### Impacto
Después de encontrar un producto en el catálogo, la validación de ruta fallaba:
```
Invalid category prefix in ruta_s3: 'raw'. Must start with one of: ['paneles', ...]
```

### Fix
Actualizar `validate_s3_path` para manejar el prefijo `raw/`:
```python
path_parts = ruta_s3.split("/")
if path_parts[0] == "raw" and len(path_parts) > 1:
    effective_prefix = path_parts[1]
else:
    effective_prefix = path_parts[0]
```

---

## Resultados de Pruebas End-to-End

### Query: "¿Cuáles son las especificaciones del panel Eco Green 275W?"
**Antes:** `- leer_ficha_tecnica: No products found in catalog...`
**Después:** Respuesta completa con datos técnicos del PDF, incluyendo:
- Potencia máxima: 275 W
- Eficiencia: 16.90%
- Dimensiones: 1640 x 992 x 35 mm
- Certificaciones: IEC 61215, IEC 61730, etc.

### Query: "hola! deseo conocer más sobre el ZnShineSolar 555W"
**Antes:** `- leer_ficha_tecnica: No products found...`
**Después:** El chatbot informa que no encontró la ficha exacta del ZnShineSolar 555W, pero lee una ficha similar (Trina Solar Vertex) y explica claramente que no corresponde al producto solicitado. La experiencia de usuario es transparente.

---

## Archivos Modificados

1. `backend/app/catalog.py` — Fix clave JSON `productos`
2. `backend/app/tools.py` — Flatten tool definitions + Fix validate_s3_path
3. `backend/main.py` — Fix BaseModel .get() + Fix _log_tool_definitions

---

## Recomendaciones Adicionales

### Dataset de Evaluación
El dataset actual (`evaluation/harness/dataset.json`) usa productos que **no existen** en el catálogo real (JA Solar JAM72S30-545/MR, ZnShineSolar 555W). Esto hace que las queries "successful" según el harness, pero en realidad representan fallos de tool calls.

**Recomendación:** Actualizar el dataset con productos reales del catálogo:
- ECO GREEN 275W (paneles)
- BATERIA AGM MAGNA 12V 150AH (baterias)
- GROWATT SPF 3000TL LVM (inversores)
- etc.

### Mejoras en el Harness
1. **Latencia:** El harness no captura `latency_ms` del endpoint — siempre reporta 0
2. **Escalated:** No verifica que `escalated` coincida con `should_escalate`
3. **Tool call errors:** Marca queries como "successful" aunque la respuesta contenga errores de tool call
4. **CONFIDENCE marker:** El LLM incluye `[CONFIDENCE: XX]` en el texto de respuesta — debería ser un campo separado en la API

### Error Handling UX
Cuando un producto no existe en el catálogo, el chatbot actualmente devuelve el error técnico al usuario. Según la decisión de diseño documentada, debería:
- **Escalar a humano** automáticamente, O
- **Responder con mensaje amigable** sin exponer detalles técnicos

---

*Documento generado el 2026-05-16 durante sesión de diagnóstico en branch carbonated-leopon.*
