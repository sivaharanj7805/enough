Run a quick health check on the project:

1. `git status` — any uncommitted changes?
2. `git log --oneline -5` — recent commits
3. `make lint` — any lint errors?
4. `make test` — any failing tests?
5. `python backend/migrate.py --status` — any pending migrations?

Report results concisely. Flag anything that needs attention.
