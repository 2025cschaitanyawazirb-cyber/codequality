import subprocess
import sys


def run(cmd):
    print(f"\n--- Running: {' '.join(cmd)} ---")
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout or "No issues found.")
    if result.stderr:
        print(result.stderr)
    return result.returncode


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "."
    failed = False

    # Check 1: style and syntax errors
    if run([sys.executable, "-m", "flake8", target]) != 0:
        failed = True

    # Check 2: code quality and bugs (score must be 7/10 or higher)
    if run([sys.executable, "-m", "pylint", target, "--fail-under=7"]) != 0:
        failed = True

    if failed:
        print("\nCode quality check FAILED.")
        sys.exit(1)

    print("\nCode quality check PASSED.")


if __name__ == "__main__":
    main()