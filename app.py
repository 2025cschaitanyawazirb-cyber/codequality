import os
import subprocess
import sys
import tempfile

from flask import Flask, render_template_string, request

app = Flask(__name__)
MAX_CHARS = 10000

PAGE = """
<!doctype html>
<html>
<head>
  <title>Code Quality Checker</title>
  <style>
    body { font-family: Arial, sans-serif; max-width: 900px; margin: 40px auto; padding: 0 20px; }
    textarea { width: 100%; font-family: monospace; font-size: 14px; }
    button { padding: 10px 20px; font-size: 16px; cursor: pointer; }
    pre { background: #f4f4f4; padding: 15px; white-space: pre-wrap; }
    .error { color: #b00020; }
  </style>
</head>
<body>
  <h2>Automated Code Quality Checker</h2>
  <p>Paste your Python code below and click <b>Check code</b>.</p>
  <form method="post">
    <textarea name="code" rows="20">{{ code }}</textarea><br><br>
    <button type="submit">Check code</button>
  </form>
  {% if error %}<p class="error">{{ error }}</p>{% endif %}
  {% if output %}<h3>Results</h3><pre>{{ output }}</pre>{% endif %}
</body>
</html>
"""


def check(code):
    # Save the pasted code to a temporary file, then run flake8 and pylint on it
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(code)
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
        return (
            "=== flake8 ===\n" + (flake.stdout or "No issues found.\n")
            + "\n=== pylint ===\n" + (pylint.stdout or "No issues found.\n")
        )
    finally:
        os.remove(path)


@app.route("/", methods=["GET", "POST"])
def index():
    code = ""
    output = ""
    error = ""
    if request.method == "POST":
        code = request.form.get("code", "")
        if not code.strip():
            error = "Please paste some code first."
        elif len(code) > MAX_CHARS:
            error = f"Code is too long. Limit is {MAX_CHARS} characters."
        else:
            output = check(code)
    return render_template_string(PAGE, code=code, output=output, error=error)


if __name__ == "__main__":
    app.run(debug=False)
