Review the most recent changes for bugs and security issues.

1. Run `git diff HEAD~1` to see what changed
2. For each changed file, check:
   - SQL injection (any string interpolation in queries?)
   - Missing input validation on API endpoints
   - Hardcoded secrets or credentials
   - Missing error handling (bare except, missing try/catch)
   - Type safety issues (any `any` types in TS, missing type hints in Python)
   - Missing `useEffect` cleanup in React components
3. Be concise. Only report actual bugs and vulnerabilities, not style preferences.
4. If everything looks clean, say so in one sentence.
