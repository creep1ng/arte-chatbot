## ¿Qué hace este PR?

<!-- Describe en 2-3 oraciones qué cambio introduce este PR y por qué existe.
     No copies el título del issue — explica el razonamiento. -->

## Issues relacionados

<!-- Usa "Closes #XX" para cerrar automáticamente la tarea al hacer merge.
     Si el PR avanza un issue padre sin cerrarlo, usa "Part of #XX". -->

Closes #
Part of #

## Tipo de cambio

<!-- Marca con una X los que apliquen -->

- [ ] 🆕 Nueva funcionalidad (feature)
- [ ] 🐛 Corrección de bug
- [ ] ♻️ Refactor (sin cambio funcional)
- [ ] 🧪 Tests
- [ ] 📄 Documentación / configuración
- [ ] 🔧 Infra / CI

## Checklist antes de pedir review

- [ ] El código corre localmente sin errores (`uvicorn` levanta, tests pasan)
- [ ] Los criterios de aceptación del issue relacionado están cumplidos
- [ ] No hay credenciales, API keys ni rutas absolutas hardcodeadas
- [ ] Si agregué dependencias nuevas, actualicé `requirements.txt` / `pyproject.toml`
- [ ] Si modifiqué el schema del endpoint, verifiqué que `/docs` refleja los cambios
- [ ] Si modifiqué el harness o el dataset, corrí `python evaluation/harness.py` y el output es el esperado

## Cómo probar este PR

<!-- Pasos mínimos para que un reviewer pueda verificar el comportamiento.
     Si aplica, incluye el comando exacto y el output esperado. -->

1. 
2. 
3. 

## Notas para el reviewer

<!-- Decisiones de diseño no obvias, trade-offs asumidos, deuda técnica
     intencional (ej. "el dict en memoria se reemplaza en S2 con Redis").
     Si no hay nada especial, escribe "Sin notas". -->
