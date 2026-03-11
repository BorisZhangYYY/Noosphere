# API /api/auth/register - TODOs

## Security & Validation
- Enforce password policy (length/complexity) and username constraints.
- Normalize and validate username (case rules, allowed characters, trimming).
- Return consistent error codes and error body schema.
- Avoid leaking raw database errors in responses.

## Database & Consistency
- Use SQLSTATE-based duplicate detection (23505) instead of string matching.
- Wrap insert and related operations into an explicit transaction.
- Add indexes and constraints as the schema grows (email, status, etc.).
- Add a migration strategy/versioning instead of "create-if-not-exists" only.

## Auth & Tokens
- Add refresh tokens and token rotation strategy.
- Add logout/token revocation list if required.
- Add access token verification middleware/decorator for protected endpoints.
- Consider secret rotation and key management strategy.

## API Design
- Add OpenAPI/Swagger documentation.
- Add request/response examples and error catalog.
- Add rate limiting for registration endpoint.

## Testing & Observability
- Add unit tests for validators and password hashing.
- Add integration tests for register endpoint against a test database.
- Add structured logging and request correlation IDs.
