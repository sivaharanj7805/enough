Write tests for: $ARGUMENTS

1. Read the target code and understand what it does
2. Identify edge cases, error paths, and happy paths
3. Write tests following existing patterns:
   - Backend: pytest + asyncio in `backend/tests/`. Use fixtures for DB connections.
   - Frontend: vitest + React Testing Library in `frontend/src/__tests__/`
4. Run the tests: `make test`
5. Fix any failures until all tests pass
6. Commit with: `test: add tests for <description>`
