# arte-chatbot

## CI Integration Test API Key Configuration

- Secret Name: `LLM_API_KEY`
- Add the API key for the LLM provider to GitHub Actions Secrets as `LLM_API_KEY`.
- The CI pipeline loads this secret for integration test execution.

Example usage in workflow:

```yaml
env:
  LLM_API_KEY: ${{ secrets.LLM_API_KEY }}
```

Ensure the secret is set in your repository settings under GitHub > Settings > Secrets and variables > Actions.
