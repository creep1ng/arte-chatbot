#!/bin/sh
set -e

# Generate config.js from environment variables
# This file is sourced by the frontend HTML to access runtime configuration
cat > /usr/share/nginx/html/config.js <<EOF
window.ARTE_CONFIG = {
  API_URL: "${API_URL:-http://localhost:8000}",
  CHAT_API_KEY: "${CHAT_API_KEY:-}",
  LLM_MODEL: "${LLM_MODEL:-unknown}",
  GIT_COMMIT_HASH: "${GIT_COMMIT_HASH:-unknown}"
};
EOF

echo "[entrypoint] config.js generated:"
echo "[entrypoint]   API_URL=${API_URL:-http://localhost:8000}"
echo "[entrypoint]   LLM_MODEL=${LLM_MODEL:-unknown}"
echo "[entrypoint]   GIT_COMMIT_HASH=${GIT_COMMIT_HASH:-unknown}"
if [ -n "${CHAT_API_KEY:-}" ]; then
  echo "[entrypoint]   CHAT_API_KEY=(set from environment)"
else
  echo "[entrypoint]   CHAT_API_KEY=(not set - requires manual input)"
fi

# Start nginx
exec nginx -g "daemon off;"
