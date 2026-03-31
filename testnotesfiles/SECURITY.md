# Security Policy

## Reporting a Vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Email security reports to: security@tended.app

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

We'll acknowledge within 48 hours and aim to patch within 7 days for critical issues.

## Security Design Notes

### CSRF

Tended uses a stateless JWT API with `Authorization: Bearer <token>` headers.
CSRF does not apply because:
- Authentication credentials are sent via `Authorization` headers, not cookies
- Browsers don't automatically attach `Authorization` headers to cross-origin requests
- No session cookies are used

### Authentication

- Supabase JWT tokens are validated on every request
- Tokens are checked for expiry (`verify_exp: True`)
- User identity is extracted from the `sub` claim
- Site ownership is verified before every data access

### Encryption

- Google OAuth refresh tokens are encrypted at rest using AES via Fernet
- Encryption key is derived from `SECRET_KEY` using PBKDF2-HMAC-SHA256
- `SECRET_KEY` must be set to a secure random value in production — startup fails otherwise

### Rate Limiting

- Auth endpoints: 5-10 requests/minute per IP
- Oracle: 10 requests/minute per IP
- Global: 60 requests/minute per IP

### SSRF Protection

Site URLs (WordPress, sitemap) are validated to prevent Server-Side Request Forgery against internal infrastructure.
