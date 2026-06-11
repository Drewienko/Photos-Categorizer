import subprocess
import sys


def check() -> None:
    steps = [
        ["ruff", "format", "src/", "tests/"],
        ["ruff", "check", "src/", "tests/"],
        ["pyright"],
        ["pytest"],
    ]
    for step in steps:
        result = subprocess.run(["uv", "run", *step])
        if result.returncode != 0:
            sys.exit(result.returncode)
