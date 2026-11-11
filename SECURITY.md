# Security Policy

## Supported versions

PyPOS is in **alpha** (0.1.x). Only the latest release/main branch receives fixes.

## Reporting a vulnerability

Please **do not** open a public issue. Report privately to `lilg_19` or use GitHub's *Report a vulnerability* feature
(Settings → Security → enable private vulnerability reporting). Include a description, steps to
reproduce, affected version and impact. We aim to acknowledge reports promptly and to coordinate
disclosure with you.

## Scope notes

- PyPOS never stores full card numbers or CVV, and its models have no fields for them.
- Secrets (`PYPOS_SECRET_KEY`, database URLs) belong in the environment, never in the repository.
- See [docs/security.md](docs/security.md) for the security model and production checklist.
