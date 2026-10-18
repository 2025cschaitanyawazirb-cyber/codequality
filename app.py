import os
import re
import subprocess
import sys
import tempfile

from flask import Flask, render_template_string, request

app = Flask(__name__)
MAX_CHARS = 10000

PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Code Quality Checker</title>
  <style>
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: "Segoe UI", Roboto, Arial, sans-serif;
      background: linear-gradient(135deg, #1e3a8a, #7c3aed);
      color: #1f2937;
    }
    .wrap { max-width: 960px; margin: 0 auto; padding: 40px 20px; }
    header { color: #fff; text-align: center; margin-bottom: 28px; }
    header h1 { margin: 0 0 8px; font-size: 2rem; }
    header p { margin: 0; opacity: 0.85; }
    .card {
      background: #fff; border-radius: 14px; padding: 28px;
      box-shadow: 0 20px 40px rgba(0, 0, 0, 0.25);
    }
    label { font-weight: 600; display: block; margin-bottom: 8px; }
    textarea {
      width: 100%; min-height: 300px; padding: 14px; border: none; border-radius: 10px;
      background: #0f172a; color: #e2e8f0; font-family: Consolas, monospace; font-size: 14px;
      line-height: 1.5; resize: vertical;
    }
    textarea:focus { outline: 3px solid #a78bfa; }
    .actions { margin-top: 16px; display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
    .hint { color: #6b7280; font-size: 14px; }
    button {
      background: linear-gradient(90deg, #2563eb, #7c3aed); color: #fff; border: none;
      padding: 12px 28px; font-size: 16px; font-weight: 600; border-radius: 10px; cursor: pointer;
    }
    button:hover { opacity: 0.9; }
    .error { background: #fee2e2; color: #991b1b; padding: 12px 16px; border-radius: 10px; margin-top: 20px; }
    .status {
      margin-top: 28px; padding: 14px; border-radius: 10px; text-align: center;
      font-size: 20px; font-weight: 700; color: #fff;
    }
    .pass { background: #16a34a; }
    .fail { background: #dc2626; }
    .stats { display: flex; gap: 16px; margin-top: 16px; flex-wrap: wrap; }
    .stat {
      flex: 1; min-width: 180px; background: #f3f4f6; border-radius: 10px;
      padding: 16px; text-align: center; color: #4b5563;
    }
    .stat strong { display: block; font-size: 28px; color: #1f2937; }
    h3 { margin: 26px 0 8px; }
    pre {
      background: #0f172a; color: #e2e8f0; padding: 16px; border-radius: 10px;
      white-space: pre-wrap; overflow-x: auto; font-size: 13px; line-height: 1.5;
    }
    footer { text-align: center; color: #e0e7ff; margin-top: 24px; font-size: 14px; }
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <h1>Automated Code Quality Checker</h1>
      <p>Paste Python code and get style and quality results instantly</p>
    </header>

    <div class="card">
      <form method="post">
        <label for="code">Your Python code</label>
        <textarea id="code" name="code" placeholder="Paste your code here...">{{ code }}</textarea>
        <div class="actions">
          <span class="hint">Max {{ max_chars }} characters</span>
          <button type="submit">Check code</button>
        </div>
      </form>

      {% if error %}
        <div class="error">{{ error }}</div>
      {% endif %}

      {% if result %}
        <div class="status {{ 'pass' if result.passed else 'fail' }}">
          {{ 'PASSED' if result.passed else 'FAILED' }}
        </div>
        <div class="stats">
          <div class="stat"><strong>{{ result.flake_count }}</strong>style issues (flake8)</div>
          <div class="stat"><strong>{{ result.score_text }}</strong>quality score (pylint, out of 10)</div>
        </div>
        <h3>flake8 report</h3>
        <pre>{{ result.flake_text }}</pre>
        <h3>pylint report</h3>
        <pre>{{ result.pylint_text }}</pre>
      {% endif %}
    </div>

    <footer>Built with Python, Flask, flake8, and pylint</footer>
  </div>
</body>
</html>
"""


def run_checks(code):
    # Save the pasted code to a temporary file, adding a newline at the end
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
                f.write(code.replace("\r\n", "\n").replace("\r", "\n").rstrip() + "\n")
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

    # Remove the temporary file path from the output so the report stays readable
    flake_lines = [line for line in flake.stdout.splitlines() if line.strip()]
    flake_lines = [line.split(":", 1)[-1].strip() if ":" in line else line for line in flake_lines]

    # Check both output streams, since pylint sometimes prints to stderr
    pylint_all = pylint.stdout + "\n" + pylint.stderr
    match = re.search(r"rated at (-?[\d.]+)/10", pylint_all)
    score = float(match.group(1)) if match else None

    pylint_text = "\n".join(
        line for line in pylint_all.splitlines() if line.strip()
    )

    return {
        "flake_count": len(flake_lines),
        "flake_text": "\n".join(flake_lines) or "No style issues found.",
        "pylint_text": pylint_text or "No issues found.",
        "score_text": f"{score:.2f}" if score is not None else "n/a",
        "passed": len(flake_lines) == 0 and score is not None and score >= 7,
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
