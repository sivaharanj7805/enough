Fix issue #$ARGUMENTS.

1. Read the issue description and any linked files
2. Enter Plan Mode — propose the fix, list affected files, and ask me to confirm before coding
3. Implement the fix following the coding standards in CLAUDE.md
4. Run `make lint && make test` to verify
5. Commit with conventional commit format: `fix: <description> (#$ARGUMENTS)`
