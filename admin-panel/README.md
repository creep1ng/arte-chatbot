# Arte Admin Panel

Panel administrativo Next.js para revisar métricas, configuración, S3, catálogo,
guías y logs de conversación del chatbot.

## Quick path local

1. Configura el backend con `ADMIN_API_KEY` en el `.env` raíz.
2. Configura el frontend con `NEXT_PUBLIC_API_URL=http://localhost:8000`.
3. Ejecuta `npm run dev` dentro de `admin-panel/`.
4. Abre `http://localhost:3001/admin/login` e ingresa la API key administrativa.

## Checklist de integración

- [ ] Backend responde `GET /health` en `http://localhost:8000`.
- [ ] Backend tiene `ADMIN_API_KEY` definido y no se expone en el bundle frontend.
- [ ] Admin panel usa `NEXT_PUBLIC_API_URL=http://localhost:8000` para navegador local.
- [ ] Login funciona en `/admin/login`.
- [ ] Logs se revisan en `/admin/logs` sin ejecutar builds locales.

> Nota Docker local: aunque el contenedor `admin-panel` comparte red con `backend`,
> `NEXT_PUBLIC_API_URL` lo consume el navegador. Por eso en `docker-compose.yml` se
> usa `http://localhost:8000`, no `http://backend:8000`.
