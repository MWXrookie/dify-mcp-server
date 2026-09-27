"""Static AST checks for generated jwave code.

Ported and adapted from the teammate project's ``jwave_flow/static_check.py``.
The goal is to catch known jwave API misuse before spending an execution attempt
in the Docker sandbox.  This module is pure standard library and deterministic.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field


@dataclass
class StaticIssue:
    rule: str
    line: int
    message: str
    hint: str = ""

    def render(self) -> str:
        text = f"[{self.rule}] line {self.line}: {self.message}"
        return f"{text} (fix: {self.hint})" if self.hint else text


@dataclass
class StaticReport:
    issues: list[StaticIssue] = field(default_factory=list)
    rules_run: int = 0
    parse_error: str | None = None

    @property
    def ok(self) -> bool:
        return not self.issues and not self.parse_error

    def feedback(self) -> str:
        if self.parse_error:
            return f"[SYNTAX] code cannot be parsed: {self.parse_error}"
        return "\n".join(issue.render() for issue in self.issues)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "parse_error": self.parse_error,
            "issues": [issue.render() for issue in self.issues],
            "codes": [issue.rule for issue in self.issues],
        }


def _dotted(node: ast.AST) -> str | None:
    parts: list[str] = []
    current: ast.AST | None = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
        return ".".join(reversed(parts))
    return None


def _callee_name(node: ast.Call) -> str | None:
    return _dotted(node.func) or (node.func.id if isinstance(node.func, ast.Name) else None)


def _looks_like_dt(node: ast.AST) -> bool:
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return False
    name = _dotted(node)
    if name is None:
        return False
    return name == "dt" or name.endswith(".dt")


def check_code(code: str) -> StaticReport:
    """Run deterministic static rules. Never raises."""
    report = StaticReport()
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        report.parse_error = f"{exc.msg} (line {exc.lineno})"
        return report

    sim_result_vars: set[str] = set()
    positions_assignments: list[tuple[int, ast.AST]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            callee = _callee_name(node.value)
            if callee and callee.endswith("simulate_wave_propagation"):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        sim_result_vars.add(target.id)
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "positions":
                    positions_assignments.append((node.lineno, node.value))

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            callee = _callee_name(node)
            short = (callee or "").split(".")[-1]

            if short == "tone_burst" and node.args and _looks_like_dt(node.args[0]):
                report.issues.append(
                    StaticIssue(
                        "R1_TONE_BURST_DT",
                        node.lineno,
                        "tone_burst first argument is sampling rate, not dt",
                        "use tone_burst(1/time_axis.dt, frequency, cycles)",
                    )
                )

            if short == "pressure_from_density" and node.args:
                arg = node.args[0]
                name = _dotted(arg)
                direct = isinstance(arg, ast.Call) and (
                    (_callee_name(arg) or "").endswith("simulate_wave_propagation")
                )
                if direct or (name in sim_result_vars):
                    report.issues.append(
                        StaticIssue(
                            "R2_DOUBLE_PRESSURE",
                            node.lineno,
                            "simulate_wave_propagation already returns a pressure field",
                            "use the returned field directly",
                        )
                    )

            if short == "Sources":
                if node.keywords:
                    bad = ", ".join(keyword.arg or "**" for keyword in node.keywords)
                    report.issues.append(
                        StaticIssue(
                            "R4_SOURCES_KEYWORDS",
                            node.lineno,
                            f"Sources does not accept keyword arguments: {bad}",
                            "use Sources(positions, signals, dt, domain)",
                        )
                    )

                def positional(index: int, keyword: str):
                    if len(node.args) > index:
                        return node.args[index]
                    for keyword_node in node.keywords:
                        if keyword_node.arg == keyword:
                            return keyword_node.value
                    return None

                signals_arg = positional(1, "signals")
                if isinstance(signals_arg, ast.List):
                    report.issues.append(
                        StaticIssue(
                            "R9_SIGNALS_LIST",
                            node.lineno,
                            "Sources signals must be a 2D jnp array, not a list",
                            "use signals = jnp.expand_dims(signal_1d, 0)",
                        )
                    )

                positions_arg = positional(0, "positions")
                if isinstance(positions_arg, ast.List):
                    report.issues.append(
                        StaticIssue(
                            "R10_POSITIONS_LIST",
                            node.lineno,
                            "Sources positions must be a tuple of 1D integer arrays",
                            "use positions = (jnp.array([x]), jnp.array([y]))",
                        )
                    )

            dotted = _dotted(node.func) or ""
            if dotted.endswith("FourierSeries.from_array"):
                report.issues.append(
                    StaticIssue(
                        "R7_FOURIER_FROM_ARRAY",
                        node.lineno,
                        "FourierSeries has no from_array classmethod",
                        "use FourierSeries(data, domain)",
                    )
                )

        if isinstance(node, ast.Attribute) and node.attr == "np":
            dotted = _dotted(node)
            if dotted and dotted.startswith("jw.np"):
                report.issues.append(
                    StaticIssue(
                        "R5_JW_NP",
                        node.lineno,
                        f"{dotted} does not exist",
                        "import jax.numpy as jnp and use jnp.*",
                    )
                )

        if isinstance(node, ast.Attribute) and node.attr in ("t", "time"):
            if isinstance(node.value, ast.Name) and node.value.id == "time_axis":
                report.issues.append(
                    StaticIssue(
                        "R6_TIME_AXIS_T",
                        node.lineno,
                        f"time_axis.{node.attr} does not exist",
                        "use time_axis.to_array()",
                    )
                )

        if isinstance(node, ast.Attribute) and node.attr in (
            "show_field",
            "display_complex_field",
        ):
            if isinstance(node.value, ast.Name) and node.value.id == "jw":
                report.issues.append(
                    StaticIssue(
                        "R8_TOPLEVEL_UTILS",
                        node.lineno,
                        f"jwave top level has no {node.attr}",
                        f"use jw.utils.{node.attr}(...)",
                    )
                )

    for lineno, value in positions_assignments:
        floats = [
            node
            for node in ast.walk(value)
            if isinstance(node, ast.Constant) and isinstance(node.value, float)
        ]
        if floats:
            report.issues.append(
                StaticIssue(
                    "R3_FLOAT_POSITIONS",
                    lineno,
                    f"positions contains {len(floats)} float literal(s)",
                    "use integer coordinates, e.g. positions = (jnp.array([64]), jnp.array([64]))",
                )
            )

    report.rules_run = 10
    seen: set[tuple[str, int]] = set()
    unique: list[StaticIssue] = []
    for issue in sorted(report.issues, key=lambda item: (item.line, item.rule)):
        key = (issue.rule, issue.line)
        if key not in seen:
            seen.add(key)
            unique.append(issue)
    report.issues = unique
    return report
