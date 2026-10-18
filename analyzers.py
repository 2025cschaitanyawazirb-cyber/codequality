"""Code analysis engine: flake8 (style), pylint (quality), bandit (security), radon (complexity)."""
import json
import os
import re
import subprocess
import sys
import tempfile

FLAKE_RE = re.compile(r"^.*?:(\d+):(\d+): ([A-Z]\d+) (.*)$")
PYLINT_RE = re.compile(r"^.*?:(\d+):(\d+): ([A-Z]\d+): (.*?)(?: \(([\w-]+)\))?$")
SCORE_RE = re.compile(r"rated at (-?[\d.]+)/10")

PASS_SCORE = 7.0
COMPLEXITY_LIMIT = 10
STYLE_SEVERITY = {"E": "Error", "F": "Fatal", "W": "Warning", "C": "Convention", "R": "Refactor"}
BANDIT_LETTER = {"HIGH": "E", "MEDIUM": "W", "LOW": "C"}


def _module(args, timeout=60):
    """Run a Python tool as a module, using the same Python as the app."""
    return subprocess.run(
        [sys.executable, "-m", *args],
        capture_output=True, text=True, timeout=timeout,
    )


def _issue(tool, line, code, letter, msg, severity, symbol=""):
    return {
        "tool": tool, "line": line, "code": code, "letter": letter,
        "msg": msg, "severity": severity, "symbol": symbol,
    }


def _flake8(path):
    proc = _module(["flake8", path], 30)
    issues = []
    for line in proc.stdout.splitlines():
        m = FLAKE_RE.match(line)
        if m:
            line_no, _col, code, msg = m.groups()
            issues.append(_issue("flake8", int(line_no), code, code[0], msg,
                                 STYLE_SEVERITY.get(code[0], "Other")))
    return issues, proc.stdout.strip()


def _pylint(path):
    proc = _module(["pylint", path])
    issues = []
    for line in proc.stdout.splitlines():
        m = PYLINT_RE.match(line)
        if m:
            line_no, _col, code, msg, symbol = m.groups()
            issues.append(_issue("pylint", int(line_no), code, code[0], msg,
                                 STYLE_SEVERITY.get(code[0], "Other"), symbol or ""))
    combined = proc.stdout + "\n" + proc.stderr
    match = SCORE_RE.search(combined)
    score = float(match.group(1)) if match else None
    return issues, score, combined.strip()


def _bandit(path):
    proc = _module(["bandit", "-q", "-f", "json", path])
    issues = []
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return issues
    for item in data.get("results", []):
        sev = item.get("issue_severity", "LOW").upper()
        issues.append(_issue(
            "bandit", item.get("line_number", 0), item.get("test_id", ""),
            BANDIT_LETTER.get(sev, "C"), item.get("issue_text", ""),
            f"Security: {sev.title()}",
        ))
    return issues


def _radon(path):
    proc = _module(["radon", "cc", "-j", path], 30)
    issues = []
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return issues
    for blocks in data.values():
        if not isinstance(blocks, list):
            continue
        for block in blocks:
            cc = block.get("complexity", 0)
            if cc > COMPLEXITY_LIMIT:
                issues.append(_issue(
                    "radon", block.get("lineno", 0), "CC", "R",
                    f"'{block.get('name')}' has complexity {cc} (limit {COMPLEXITY_LIMIT})",
                    "Complexity",
                ))
    return issues


def run_checks(code):
    normalized = code.replace("\r\n", "\n").replace("\r", "\n").rstrip() + "\n"
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(normalized)
        path = f.name
    try:
        flake_issues, raw_flake = _flake8(path)
        pylint_issues, score, raw_pylint = _pylint(path)
        bandit_issues = _bandit(path)
        radon_issues = _radon(path)
    finally:
        os.remove(path)

    issues = flake_issues + pylint_issues + bandit_issues + radon_issues
    issues.sort(key=lambda i: i["line"])

    flake_count = len(flake_issues)
    security_high = sum(1 for i in bandit_issues if i["letter"] == "E")
    passed = (
        flake_count == 0
        and security_high == 0
        and score is not None
        and score >= PASS_SCORE
    )

    if score is None:
        color = "#64748b"
    elif score >= 8:
        color = "#22c55e"
    elif score >= 5:
        color = "#f59e0b"
    else:
        color = "#ef4444"

    return {
        "issues": issues,
        "flake_count": flake_count,
        "pylint_count": len(pylint_issues),
        "security_count": len(bandit_issues),
        "complexity_count": len(radon_issues),
        "score_text": f"{score:.1f}" if score is not None else "n/a",
        "pct": int(score * 10) if score is not None else 0,
        "color": color,
        "passed": passed,
        "raw_flake": raw_flake or "No style issues found.",
        "raw_pylint": raw_pylint or "No output.",
    }
