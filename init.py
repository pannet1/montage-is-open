#!/usr/bin/env python3
"""Initialize a new project workspace.

Without arguments, runs first-time setup (setup, update, preflight).
With a project name, creates a new project directory.
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from main import cmd_init, banner

HERE = Path(__file__).resolve().parent
OM = HERE / "OpenMontage"


def run_cmd(cmd, cwd=None, capture=False, check=False):
    """Run a shell command with optional capture."""
    print(f"  $ {cmd}")
    method = subprocess.run if not capture else (
        lambda *a, **kw: subprocess.run(*a, **kw, capture_output=True, text=True)
    )
    if capture:
        return method(cmd, cwd=cwd or HERE, shell=True)
    return method(cmd, cwd=cwd or HERE, shell=True, check=check)


def _setup():
    """Create venv, install deps, bootstrap Remotion."""
    venv = HERE / ".venv"
    if not venv.exists():
        print("  Creating uv virtual environment...")
        subprocess.run("uv venv", cwd=HERE, shell=True)

    print("  Installing Python dependencies (via uv)...")
    run_cmd("uv pip install -r requirements.txt", cwd=OM)
    print("  Installing Remotion composer (npm)...")
    run_cmd("npm install", cwd=OM / "remotion-composer")
    run_cmd(
        "uv pip install piper-tts 2>/dev/null || "
        "echo '  [skip] piper-tts — cloud TTS still works'"
    )

    env_path = HERE / ".env"
    example = OM / ".env.example"
    if not env_path.exists() and example.exists():
        shutil.copy(example, env_path)
        print("  Created .env from .env.example — add your API keys.")

    print("  Setup done.")


def _update():
    """Update OpenMontage submodule to latest."""
    r = subprocess.run(
        "git submodule update --remote OpenMontage",
        cwd=HERE, shell=True, capture_output=True, text=True,
    )
    if r.returncode == 0:
        print("  OpenMontage updated to latest.")
        print("  Commit:  git add OpenMontage && git commit -m 'Update OpenMontage'")
    else:
        print("  Update failed. Check network / submodule state.")
        print(r.stderr.strip() or r.stdout.strip())


def _preflight():
    """Discover and display tool capabilities."""
    print("  Running preflight (discovering tools)...")
    r = subprocess.run(
        ["uv", "run", "python", "-c",
         "from tools.tool_registry import registry; import json; "
         "registry.discover(); print(json.dumps(registry.provider_menu_summary(), indent=2))"],
        cwd=OM, capture_output=True, text=True,
    )
    if r.returncode == 0:
        print(r.stdout)
    else:
        print("  Preflight failed:")
        print(r.stderr.strip() or r.stdout.strip())


def main():
    parser = argparse.ArgumentParser(
        prog="uv run init",
        description="Initialize a new project workspace",
        add_help=False,
    )
    parser.add_argument("name", nargs="?", default=None, help="Project name (directory under projects/)")
    parser.add_argument("topic", nargs="?", default=None, help="Video topic")
    args = parser.parse_args()

    if args.name is None:
        # First-time setup mode
        banner()
        print("  First-time setup — installing dependencies and checking tools...\n")
        _setup()
        _update()
        _preflight()
        print()
        print("  ── READY ──")
        print()
        print("  Create a project:")
        print("    uv run init <project-name>")
        print()
        return

    cmd_init(args)


if __name__ == "__main__":
    main()
