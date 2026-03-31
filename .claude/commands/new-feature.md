Implement a new feature: $ARGUMENTS

Follow this workflow:

1. **Research**: Read relevant existing code. Check ARCHITECTURE.md for system context. Check lib/types.ts for existing interfaces. Check lib/copy.ts for existing copy patterns.

2. **Plan**: Before writing any code, propose:
   - Which files will be created or modified
   - New API endpoints (if any)
   - New database tables or columns (if any)
   - New frontend components (if any)
   - Any migration files needed
   Wait for my approval before proceeding.

3. **Implement**: Write the code following CLAUDE.md standards. Commit after each logical unit with conventional commits.

4. **Verify**: Run `make lint && make test && make build`. Fix any failures.

5. **Summary**: List what was created/changed and any follow-up items.
