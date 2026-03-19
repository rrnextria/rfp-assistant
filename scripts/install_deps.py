#!/usr/bin/env python3
"""Read pyproject.toml and pip install all dependencies except 'common'."""
import subprocess, sys, tomllib, pathlib

toml_path = pathlib.Path("pyproject.toml")
if not toml_path.exists():
    print("No pyproject.toml found", file=sys.stderr)
    sys.exit(1)

data = tomllib.load(toml_path.open("rb"))
deps = [d for d in data["project"]["dependencies"] if d != "common"]
if not deps:
    print("No dependencies to install.")
    sys.exit(0)

print(f"Installing: {deps}")
subprocess.run(["pip", "install", "--no-cache-dir"] + deps, check=True)
