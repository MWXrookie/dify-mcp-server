# Teammate reference: jwave-dify-langchain

This directory is a cleaned copy of `jwave_codeagent.zip`. It is reference
material only and is not imported by the running MCP server.

## What was kept

- `jwave_flow/` source modules
- `docs/MAPPING.md` Dify-to-LangGraph mapping
- `kb/` organized knowledge base and patch notes
- `tools/`, `examples/`, and `tests/`
- package and dependency manifests

## What was removed

- `.git`, `__pycache__`, and `.pytest_cache`
- `.vscode/`
- generated `run/` history files
- the unused Dify workflow export
- duplicate knowledge-base backup

## What was ported into this project

The useful ideas were ported into the current MCP gateway instead of adopting
the LangGraph backend:

- `app/static_check.py` was added with focused unit tests. It is not yet wired into
  `run_jwave_code_with_retry`; production integration belongs to the quality-gate work.
- The semantic-gate idea was wired into `tools.py`: an exit code of zero is no
  longer considered success unless `analysis._analyze_impl` returns
  `verdict == "normal"`.
- `analysis.py` now compares optional `f0` and field-shape metadata with the
  requested `params_json` when those values are available.

The LangGraph orchestrator and its subprocess/jupyter/mcp executors are not
used. The current Docker jwave executor remains the execution boundary.
