# Frontend — Next.js 14 (App Router)

## Directory Map

| Directory | What's there |
|-----------|-------------|
| `src/app/(dashboard)/` | Authenticated pages — paywall at layout level (redirects to /billing if unpaid) |
| `src/app/` (root) | Landing, login, signup, onboarding, privacy, terms, public report |
| `src/components/landscape/` | **PROTECTED.** Ecosystem viz (canvas + D3). Never delete without human approval. |
| `src/components/` | Feature folders: oracle, cannibalization, consolidation, dashboard, impact… |
| `src/lib/api.ts` | `apiFetch<T>()` with Bearer token. Appends `/v1` to base URL automatically. |
| `src/lib/hooks/useApi.ts` | All SWR data hooks — one per endpoint |
| `src/lib/hooks/useSWRFetch.ts` | Generic SWR fetcher via `apiFetch` + Supabase session |
| `src/lib/copy.ts` | 13K lines centralized microcopy — ALL user-facing strings live here |
| `src/lib/constants.ts` | Colors, ecosystem states, animation timings |
| `src/lib/types.ts` | Shared TypeScript interfaces |

## Before Writing Code

- Search `lib/copy.ts` before adding any user-facing text
- Check `lib/types.ts` before creating new interfaces
- Check `lib/hooks/useApi.ts` before adding a new data hook

## Patterns

- New SWR hooks → `lib/hooks/useApi.ts` using `useSWRFetch<T>`
- New authenticated pages → `app/(dashboard)/` (layout handles paywall)
- New components → feature folder under `components/`
- User-facing strings → `lib/copy.ts`, never inline

## Known Issues

- Landscape renderers were deleted in c0a296b — restore pending

## Testing

```bash
make test-frontend   # vitest run
```

Tests in `src/__tests__/`. Use vitest + React Testing Library.
