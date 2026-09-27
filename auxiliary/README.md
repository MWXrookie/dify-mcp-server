# Auxiliary Content

This directory contains material that is useful for development but is not part
of the deployed AcouAgent service:

- `reference/`: teammate or external reference implementations
- `work/`: plugin evaluations, one-off experiments, test reports, and temporary
  review artifacts

The `auxiliary/` directory is excluded from the Docker build context. Runtime
code lives under `app/`; the Dify knowledge-base material remains outside this
repository.

Historical experiment documents may still reference the pre-reorganization
paths (`server_safe.py`, `tools.py`, `reference/`, or `work/`). Those references
describe the original test snapshot and are not the current runtime layout.
