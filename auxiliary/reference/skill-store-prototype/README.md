# Skill-store prototype reference

This directory preserves the isolated 2026-09-23 prototype, its test contract,
and three independent review passes. It is reference evidence for the production
SQLite skill store; it is excluded from the runtime image.

Do **not** copy the prototype directly into production. The reviews require the
production implementation to add trusted validation receipts, task/parameter/code
binding, explicit schema migration and rollback, server-owned storage injection,
and replay-resistant feedback tokens with cleanup.

The executable prototype remains useful for contract exploration. Its passing
tests prove only the isolated prototype behavior, not AcouAgent production quality.
