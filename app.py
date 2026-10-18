import os
import re
import subprocess
import sys
import tempfile

from flask import Flask, render_template_string, request

app = Flask(__name__)
MAX_CHARS = 10000
PASS_SCORE = 7.0

FLAKE_RE = re.compile(r"^.*?:(\d+):(\d+): ([A-Z]\d+) (.*)$")
PYLINT_RE = re.compile(r"^.*?:(\d+):(\d+): ([A-Z]\d+): (.*?)(?: \(([\w-]+)\))?$")
SCORE_RE = re.compile(r"rated at (-?[\d.]+)/10")

SEVERITY = {"E": "Error", "F": "Fatal", "W": "Warning", "C": "Convention", "R": "Refactor"}

PAGE = r'''
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Code Quality Checker</title>
  <style>
    :root {
      --bg: #0b1020;
      --panel: #121a2e;
      --panel2: #0f1628;
      --line: #23304d;
      --text: #e6ebf5;
      --muted: #8b97b5;
      --accent: #7c5cff;
      --accent2: #22d3ee;
      --ok: #22c55e;
      --bad: #ef4444;
      --warn: #f59e0b;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: "Segoe UI", Inter, Roboto, Arial, sans-serif;
      color: var(--text);
      background:
        radial-gradient(900px 500px at 10% -10%, rgba(124, 92, 255, 0.35), transparent 60%),
        radial-gradient(800px 500px at 110% 10%, rgba(34, 211, 238, 0.25), transparent 60%),
        var(--bg);
    }
    .wrap { max-width: 1040px; margin: 0 auto; padding: 32px 20px 60px; }

    nav { display: flex; align-items: center; justify-content: space-between; margin-bottom: 36px; }
    .brand { display: flex; align-items: center; gap: 10px; font-weight: 700; }
    .logo {
      width: 36px; height: 36px; border-radius: 10px; display: grid; place-items: center;
      background: linear-gradient(135deg, var(--accent), var(--accent2)); font-size: 14px;
    }
    .pill {
      font-size: 13px; color: var(--muted); border: 1px solid var(--line);
      padding: 6px 12px; border-radius: 999px;
    }

    .hero { text-align: center; margin-bottom: 32px; }
    .hero h1 {
      margin: 0 0 10px; font-size: 2.4rem; letter-spacing: -0.02em;
      background: linear-gradient(90deg, #fff, #c4b5fd, #67e8f9);
      -webkit-background-clip: text; background-clip: text; color: transparent;
    }
    .hero p { margin: 0 auto; max-width: 620px; color: var(--muted); font-size: 1.05rem; }

    .card {
      background: rgba(18, 26, 46, 0.85); border: 1px solid var(--line);
      border-radius: 18px; padding: 22px; box-shadow: 0 25px 60px rgba(0, 0, 0, 0.35);
      backdrop-filter: blur(8px);
    }

    .toolbar { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 14px; }
    .toolbar .group { display: flex; gap: 8px; flex-wrap: wrap; }
    .ghost {
      background: transparent; color: var(--muted); border: 1px solid var(--line);
      padding: 8px 14px; border-radius: 9px; font-size: 13px; font-weight: 600; cursor: pointer;
    }
    .ghost:hover { color: var(--text); border-color: var(--accent); }

    .editor-wrap {
      position: relative; border-radius: 12px; border: 1px solid var(--line);
      background: var(--panel2); overflow: hidden;
    }
    .editor-wrap::before {
      content: "main.py"; display: block; padding: 10px 14px; font-size: 12px; color: var(--muted);
      border-bottom: 1px solid var(--line); font-family: Consolas, monospace;
    }
    textarea {
      width: 100%; min-height: 320px; padding: 16px; border: none; outline: none; resize: vertical;
      background: transparent; color: #e2e8f0; font-family: Consolas, "Courier New", monospace;
      font-size: 14px; line-height: 1.6; tab-size: 4;
    }
    textarea:focus { box-shadow: inset 0 0 0 2px rgba(124, 92, 255, 0.6); }

    .footer-row { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-top: 16px; flex-wrap: wrap; }
    .muted { color: var(--muted); font-size: 13px; }
    .submit {
      background: linear-gradient(90deg, var(--accent), #4f8cff); color: #fff; border: none;
      padding: 12px 26px; border-radius: 11px; font-size: 15px; font-weight: 700; cursor: pointer;
      box-shadow: 0 10px 25px rgba(124, 92, 255, 0.35);
    }
    .submit:hover { filter: brightness(1.08); }

    .error {
      margin-top: 18px; padding: 14px 16px; border-radius: 12px;
      background: rgba(239, 68, 68, 0.12); border: 1px solid rgba(239, 68, 68, 0.4); color: #fecaca;
    }

    .summary { display: grid; grid-template-columns: 1.2fr 1fr 1fr 1fr; gap: 14px; margin-top: 26px; }
    @media (max-width: 760px) { .summary { grid-template-columns: 1fr 1fr; } }
    .tile {
      background: var(--panel2); border: 1px solid var(--line); border-radius: 14px; padding: 18px;
      display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center;
    }
    .tile .big { font-size: 26px; font-weight: 800; }
    .tile .label { color: var(--muted); font-size: 13px; margin-top: 4px; }
    .verdict { font-size: 22px; font-weight: 800; letter-spacing: 0.04em; }
    .verdict.pass { color: var(--ok); }
    .verdict.fail { color: var(--bad); }

    .ring {
      width: 96px; height: 96px; border-radius: 50%; display: grid; place-items: center; margin-bottom: 8px;
      background: conic-gradient(var(--c) calc(var(--p) * 1%), #1e293b 0);
    }
    .ring span {
      width: 76px; height: 76px; border-radius: 50%; background: var(--panel2);
      display: grid; place-items: center; font-weight: 800; font-size: 18px;
    }

    h3 { margin: 30px 0 12px; font-size: 1.05rem; }
    table { width: 100%; border-collapse: collapse; font-size: 14px; }
    th, td { text-align: left; padding: 11px 12px; border-bottom: 1px solid var(--line); vertical-align: top; }
    th { color: var(--muted); font-weight: 600; font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em; }
    td.msg { line-height: 1.45; }
    .code { font-family: Consolas, monospace; color: #c4b5fd; }
    .badge {
      display: inline-block; padding: 3px 9px; border-radius: 999px; font-size: 12px; font-weight: 700;
    }
    .badge.E, .badge.F { background: rgba(239, 68, 68, 0.18); color: #fca5a5; }
    .badge.W { background: rgba(245, 158, 11, 0.18); color: #fcd34d; }
    .badge.C { background: rgba(34, 211, 238, 0.15); color: #67e8f9; }
    .badge.R { background: rgba(124, 92, 255, 0.2); color: #c4b5fd; }
    .empty {
      text-align: center; padding: 26px; border-radius: 12px; background: rgba(34, 197, 94, 0.08);
      color: #86efac; border: 1px dashed rgba(34, 197, 94, 0.4);
    }

    details { margin-top: 14px; background: var(--panel2); border: 1px solid var(--line); border-radius: 12px; padding: 12px 16px; }
    summary { cursor: pointer; color: var(--muted); font-weight: 600; }
    pre {
      margin: 12px 0 4px; white-space: pre-wrap; overflow-x: auto; font-size: 13px; line-height: 1.55;
      color: #cbd5e1; font-family: Consolas, monospace;
    }

    footer { text-align: center; color: var(--muted); margin-top: 36px; font-size: 13px; }
  </style>
</head>
<body>
  <div class="wrap">
    <nav>
      <div class="brand"><div class="logo">CQ</div>CodeCheck</div>
      <span class="pill">flake8 + pylint</span>
    </nav>

    <section class="hero">
      <h1>Automated Code Quality Checker</h1>
      <p>Paste your Python code and get instant style, bug, and quality feedback, the same checks that run in our GitHub Actions pipeline.</p>
    </section>

    <div class="card">
      <form method="post" id="checkForm">
        <div class="toolbar">
          <div class="group">
            <button type="button" class="ghost" onclick="load('clean')">Clean example</button>
            <button type="button" class="ghost" onclick="load('messy')">Messy example</button>
            <button type="button" class="ghost" onclick="load('syntax')">Syntax error</button>
          </div>
          <button type="button" class="ghost" onclick="clearBox()">Clear</button>
        </div>

        <div class="editor-wrap">
          <textarea id="code" name="code" spellcheck="false" placeholder="# Paste your Python code here...">{{ code }}</textarea>
        </div>

        <div class="footer-row">
          <span class="muted" id="count">0 / {{ max_chars }} characters · Ctrl + Enter to check</span>
          <button type="submit" class="submit">Check code</button>
        </div>
      </form>

      {% if error %}
        <div class="error">{{ error }}</div>
      {% endif %}

      {% if result %}
        <div class="summary">
          <div class="tile">
            <div class="verdict {{ 'pass' if result.passed else 'fail' }}">{{ 'PASSED' if result.passed else 'FAILED' }}</div>
            <div class="label">Overall result</div>
          </div>
          <div class="tile">
            <div class="ring" style="--p: {{ result.pct }}; --c: {{ result.color }};"><span>{{ result.score_text }}</span></div>
            <div class="label">Pylint score out of 10</div>
          </div>
          <div class="tile">
            <div class="big">{{ result.flake_count }}</div>
            <div class="label">Style issues (flake8)</div>
          </div>
          <div class="tile">
            <div class="big">{{ result.pylint_count }}</div>
            <div class="label">Quality issues (pylint)</div>
          </div>
        </div>

        <h3>Issues found</h3>
        {% if result.issues %}
          <table>
            <thead>
              <tr><th>Line</th><th>Tool</th><th>Code</th><th>Severity</th><th>Message</th></tr>
            </thead>
            <tbody>
              {% for issue in result.issues %}
              <tr>
                <td>{{ issue.line }}</td>
                <td>{{ issue.tool }}</td>
                <td class="code">{{ issue.code }}</td>
                <td><span class="badge {{ issue.letter }}">{{ issue.severity }}</span></td>
                <td class="msg">{{ issue.msg }}{% if issue.symbol %} <span class="muted">({{ issue.symbol }})</span>{% endif %}</td>
              </tr>
              {% endfor %}
            </tbody>
          </table>
        {% else %}
          <div class="empty">No issues found. Your code is clean.</div>
        {% endif %}

        <details>
          <summary>Raw flake8 output</summary>
          <pre>{{ result.raw_flake }}</pre>
        </details>
        <details>
          <summary>Raw pylint output</summary>
          <pre>{{ result.raw_pylint }}</pre>
        </details>
      {% endif %}
    </div>

    <footer>Built with Python, Flask, flake8, and pylint</footer>
  </div>

  <script>
    const MAX = {{ max_chars }};
    const EXAMPLES = {
      clean: `"""Add two numbers and print the result."""


def add(first, second):
    """Return the sum of two numbers."""
    return first + second


if __name__ == "__main__":
    print(add(5, 10))
`,
      messy: `import os
def add(a,b):
    unused = 5
    return a+b
x=add(1,2)
`,
      syntax: `def greet(name)
    print("Hello", name
`
    };

    const box = document.getElementById("code");
    const counter = document.getElementById("count");

    function update() {
      counter.textContent = box.value.length + " / " + MAX + " characters · Ctrl + Enter to check";
    }
    function load(key) { box.value = EXAMPLES[key]; update(); box.focus(); }
    function clearBox() { box.value = ""; update(); box.focus(); }

    box.addEventListener("input", update);
    box.addEventListener("keydown", (e) => {
      if (e.ctrlKey && e.key === "Enter") { document.getElementById("checkForm").submit(); }
    });
    update();
  </script>
</body>
</html>
'''

COLORS = {"E": "#ef4444", "F": "#ef4444", "W": "#f59e0b", "C": "#22d3ee", "R": "#7c5cff"}


def run_checks(code):
    normalized = code.replace("\r\n", "\n").replace("\r", "\n").rstrip() + "\n"
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(normalized)
        path = f.name
    try:
        flake = subprocess.run(
            [sys.executable, "-m", "flake8", path],
            capture_output=True, text=True, timeout=30,
        )
        pylint = subprocess.run(
            [sys.executable, "-m", "pylint", path],
            capture_output=True, text=True, timeout=60,
        )
    finally:
        os.remove(path)

    issues = []
    for line in flake.stdout.splitlines():
        m = FLAKE_RE.match(line)
        if m:
            line_no, _col, code_id, msg = m.groups()
            issues.append({"tool": "flake8", "line": int(line_no), "code": code_id,
                           "msg": msg, "symbol": ""})

    for line in pylint.stdout.splitlines():
        m = PYLINT_RE.match(line)
        if m:
            line_no, _col, code_id, msg, symbol = m.groups()
            issues.append({"tool": "pylint", "line": int(line_no), "code": code_id,
                           "msg": msg, "symbol": symbol or ""})

    for issue in issues:
        letter = issue["code"][0]
        issue["letter"] = letter
        issue["severity"] = SEVERITY.get(letter, "Other")
    issues.sort(key=lambda i: i["line"])

    combined = pylint.stdout + "\n" + pylint.stderr
    match = SCORE_RE.search(combined)
    score = float(match.group(1)) if match else None

    flake_count = sum(1 for i in issues if i["tool"] == "flake8")
    pylint_count = sum(1 for i in issues if i["tool"] == "pylint")
    passed = flake_count == 0 and score is not None and score >= PASS_SCORE

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
        "pylint_count": pylint_count,
        "score_text": f"{score:.1f}" if score is not None else "n/a",
        "pct": int(score * 10) if score is not None else 0,
        "color": color,
        "passed": passed,
        "raw_flake": flake.stdout.strip() or "No style issues found.",
        "raw_pylint": combined.strip() or "No output.",
    }


@app.route("/", methods=["GET", "POST"])
def index():
    code = ""
    result = None
    error = ""
    if request.method == "POST":
        code = request.form.get("code", "")
        if not code.strip():
            error = "Please paste some code first."
        elif len(code) > MAX_CHARS:
            error = f"Code is too long. The limit is {MAX_CHARS} characters."
        else:
            result = run_checks(code)
    return render_template_string(
        PAGE, code=code, result=result, error=error, max_chars=MAX_CHARS
    )


if __name__ == "__main__":
    app.run(debug=False)
