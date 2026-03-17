# arte-chatbot

## CI Integration Test Configuration

Required secrets:
- `OPENAI_API_KEY` — API key for the OpenAI LLM provider
- `CHAT_API_KEY` — API key for authenticating with the /chat endpoint

Add these secrets to GitHub Actions Secrets.

Example usage in workflow:

```yaml
env:
  OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
  CHAT_API_KEY: ${{ secrets.CHAT_API_KEY }}
```

Ensure the secrets are set in your repository settings under GitHub > Settings > Secrets and variables > Actions.
