import io
import json
import re

import pycodestyle
from pyflakes.api import check as pyflakes_check
from pyflakes.reporter import Reporter
from radon.complexity import cc_visit

COMPLEXITY_LIMIT = 10
LINE_RE = re.compile(r"^.*?:(\d+):\d+: (.*)$")


class Collector(pycodestyle.BaseReport):
    """Collects pycodestyle results instead of printing them."""

    def __init__(self, options):
        super().__init__(options)
        self.found = []

    def error(self, line_number, offset, text, check):
        self.found.append((line_number, text[:4], text[5:]))
        return text[:4]


def normalize(code):
    return code.replace("\r\n", "\n").replace("\r", "\n").rstrip() + "\n"


def analyze(raw_code):
    code = normalize(raw_code)
    issues = []
    has_syntax_error = False

    # 1. Syntax and logic errors (pyflakes)
    out, err = io.StringIO(), io.StringIO()
    pyflakes_check(code, "main.py", Reporter(out, err))
    for line in (err.getvalue() + out.getvalue()).splitlines():
        m = LINE_RE.match(line)
        if m:
            line_no, msg = m.groups()
            is_syntax = "syntax" in msg.lower() or "EOF" in msg
            has_syntax_error = has_syntax_error or is_syntax
            issues.append({
                "line": int(line_no),
                "tool": "pyflakes",
                "code": "SYNTAX" if is_syntax else "LOGIC",
                "letter": "E" if is_syntax else "F",
                "label": "Syntax error" if is_syntax else "Logic",
                "msg": msg,
            })

    # 2. Style issues (pycodestyle, the engine behind flake8). Advisory only.
    style = pycodestyle.StyleGuide(quiet=True)
    collector = Collector(style.options)
    checker = pycodestyle.Checker(
        "main.py", lines=code.splitlines(True),
        options=style.options, report=collector,
    )
    checker.check_all()
    for line_no, code_id, msg in collector.found:
        issues.append({
            "line": line_no,
            "tool": "pycodestyle",
            "code": code_id,
            "letter": "C",
            "label": "Style",
            "msg": msg,
        })

    # 3. Complexity (radon). Advisory only.
    if not has_syntax_error:
        try:
            for block in cc_visit(code):
                if block.complexity > COMPLEXITY_LIMIT:
                    issues.append({
                        "line": block.lineno,
                        "tool": "radon",
                        "code": "CC",
                        "letter": "R",
                        "label": "Complexity",
                        "msg": f"'{block.name}' has complexity {block.complexity} (limit {COMPLEXITY_LIMIT})",
                    })
        except SyntaxError:
            pass

    issues.sort(key=lambda i: i["line"])

    blocking = sum(1 for i in issues if i["letter"] in ("E", "F"))
    passed = blocking == 0

    return json.dumps({
        "issues": issues,
        "blocking": blocking,
        "style": sum(1 for i in issues if i["letter"] == "C"),
        "complexity": sum(1 for i in issues if i["letter"] == "R"),
        "passed": passed,
    })
