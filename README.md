# Automated Code Quality Checker

[![Code Quality Check](https://github.com/2025cschaitanyawazirb-cyber/codequality/actions/workflows/code-quality.yml/badge.svg)](https://github.com/2025cschaitanyawazirb-cyber/codequality/actions/workflows/code-quality.yml)

A tool that automatically analyzes Python code for style errors, bugs, and quality issues. It runs on every push to GitHub using GitHub Actions, following CI/CD principles.

## Technologies
- Python
- Git and GitHub
- GitHub Actions
- flake8 and pylint

## How to run locally

```bash
pip install -r requirements.txt
python checker.py sample_code
```

## How it works
1. A developer pushes code to `main`.
2. GitHub Actions starts the workflow in `.github/workflows/code-quality.yml`.
3. The checker runs flake8 and pylint.
4. The pipeline passes or fails based on the results.
