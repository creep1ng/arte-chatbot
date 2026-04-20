# UX Checklist — Chatbot Conversacional Arte

Checklist basada en principios de diseño conversacional y heurísticas de usabilidad para interfaces conversacionales. Usar para auditar experiencias de usuario en el chatbot.

---

## 1. Transparencia y Expectativas

- [ ] El bot se identifica como "Arte, asistente de Arte Soluciones Energéticas" desde el primer mensaje
- [ ] Los límites del bot son claros: el usuario sabe qué puede y no puede hacer el asistente
- [ ] El bot no simula ser humano ni oculta que es una IA
- [ ] Los tiempos de espera (typing indicators) son visibles durante procesamiento
- [ ] El bot indica cuándo no puede acceder a información específica (ej. precios exactos, stock)

---

## 2. Flujo y Degradación Elegante (Fallback)

- [ ] El bot tiene respuestas para queries fuera de dominio que redirigen útilmente
- [ ] Los mensajes de fallback no son genéricos ("Lo siento, no entiendo") sino orientan al usuario hacia temas disponibles
- [ ] El bot hace clarification preguntas antes de asumir intenciones ambiguas
- [ ] Existe un límite de intentos de recuperación antes de ofrecer escalar a humano
- [ ] Los mensajes de error no culpabilizan al usuario ("Tu consulta no fue válida" → "Puedo ayudarte con...")

---

## 3. Retención de Contexto

- [ ] El bot recuerda el historial de la conversación actual (sesión)
- [ ] Referencias como "el panel que mencionaste" o "esa consulta" son resueltas correctamente
- [ ] El contexto de la consulta previa se mantiene al menos 5 turnos de conversación
- [ ] No se pierden datos de sesión ante errores temporales

---

## 4. Cualificación de Consulta

- [ ] El bot hace preguntas de cualificación cuando necesita datos para responder (consumo energético, ubicación, etc.)
- [ ] Las preguntas siguen un orden lógico (de básico a específico)
- [ ] El bot evita hacer más de 3 preguntas seguidas sin dar valor
- [ ] Las preguntas ayudan al usuario a tomar decisiones informadas
- [ ] El bot recommienda productos basados en la información recopilada

---

## 5. Escalamiento a Humanos

- [ ] El bot detecta correctamente cuándo una consulta requiere intervención humana (ventas, soporte técnico especializado)
- [ ] La transición a agente humano es fluida y no requiere que el usuario repita información
- [ ] El bot comunica claramente qué tipo de agente recibirá la consulta (ventas vs. soporte técnico)
- [ ] Existe un mecanismo para escalar urgentemente (problemas de seguridad eléctrica, equipos dañados)
- [ ] El usuario recibe confirmación de que su consulta fue escalda y un canal de seguimiento

---

## 6. Tono y Profesionalismo

- [ ] El tono es consistente con la identidad de marca (B2B solar, profesional pero accesible)
- [ ] El bot usa lenguaje técnico apropiado para la audiencia (evitar jerga innecesaria)
- [ ] Las respuestas son concisas (máximo 3-4 oraciones para info directa)
- [ ] El bot muestra empatía en situaciones de problema/queja
- [ ] No hay errores gramaticales en las respuestas
- [ ] Se usan formularios de cortesía apropiados sin ser excesivos

---

## 7. Accesibilidad

- [ ] Las respuestas funcionan en pantallas pequeñas (mobile-first)
- [ ] El contenido es escaneable (párrafos cortos, listas cuando hay múltiples opciones)
- [ ] Se evitan caracteres especiales o emojis que puedan no renderizar correctamente
- [ ] Los links y referencias a fichas técnicas son clickeables

---

## 8. Privacidad y Seguridad (UX)

- [ ] El bot no pide datos sensibles innecesarios (números de tarjeta, contraseñas)
- [ ] Se informa al usuario cómo se usan sus datos de conversación
- [ ] El proceso de escalamiento no expone información sensible en logs

---

## Referencias
- NeuronUX: UX Design Best Practices for Conversational AI (2026)
- BotHero: 12 Proven Tips for Chatbot UX (2026)
- Smashing Magazine: How to Design Effective Conversational AI Experiences (2024)
- Eleken: Conversational UI 9 Must-Follow Principles (2026)