# Development and test scripts

These scripts are intentionally kept outside the runtime image. They are useful
for local workflow construction and regression testing, but are not copied by
the gateway `Dockerfile`.

## workflow

Utilities that used to construct or patch the exported Dify workflow JSON.
They operate on a graph file passed as an argument.

```bash
python scripts/workflow/_build_graph.py draft_graph.json > new_graph.json
python scripts/workflow/_build_t009.py published_graph.json > expanded_graph.json
python scripts/workflow/_apply_heatmap.py workflow_graph.json > patched_graph.json
```

These are historical tooling and do not affect the MCP server runtime.

## tests

End-to-end regression and stability scripts. They require a running gateway and
the appropriate API keys/URLs.

```bash
python scripts/tests/run_50_tests_new.py
python scripts/tests/run_t012_multiturn.py
python scripts/tests/test_multiturn_stability.py
```

Most of these tests still call the legacy Dify workflow API. Keep them only if
that workflow is part of the current environment; otherwise use the direct MCP
tools for runtime testing.

# 统一场数据与点传感器输出契约
python scripts/workflow/_apply_result_contract.py workflow_graph.json > patched_graph.json
