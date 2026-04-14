#!/bin/sh
set -e

# Generate config.js from environment variables
# This file is sourced by the frontend HTML to access runtime configuration
cat > /usr/share/nginx/html/config.js <<EOF
window.ARTE_CONFIG = {
  API_URL: "${API_URL:-http://localhost:8000}",
  CHAT_API_KEY: "",
  LLM_MODEL: "${LLM_MODEL:-unknown}"
};
EOF

echo "[entrypoint] config.js generated:"
echo "[entrypoint]   API_URL=${API_URL:-http://localhost:8000}"
echo "[entrypoint]   LLM_MODEL=${LLM_MODEL:-unknown}"
echo "[entrypoint]   CHAT_API_KEY=(not set - requires manual input)"

# Start nginx
exec nginx -g "daemon off;"
