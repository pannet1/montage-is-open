#!/usr/bin/env python3
"""montage-is-open — entry point for OpenMontage video production."""

import subprocess, shutil, os, sys, textwrap
from pathlib import Path

HERE = Path(__file__).parent
OM = HERE / "OpenMontage"
OM_AGENT_GUIDE = OM / "AGENT_GUIDE.md"


def banner():
    width = shutil.get_terminal_size().columns
    print("=" * width)
    print("  montage-is-open — OpenMontage Consumer Project")
    print("=" * width)


def check_submodule():
    if not OM.exists():
        print("[!] OpenMontage submodule not found. Run: git submodule update --init --recursive")
        sys.exit(1)
    if not OM_AGENT_GUIDE.exists():
        print("[!] OpenMontage is incomplete. Try: git submodule update --init --recursive")
        sys.exit(1)


def run(cmd, cwd=None):
    print(f"  $ {cmd}")
    return subprocess.run(cmd, cwd=cwd or HERE, shell=True)


def step_update():
    r = subprocess.run(
        "git submodule update --remote OpenMontage",
        cwd=HERE, shell=True, capture_output=True, text=True,
    )
    if r.returncode == 0:
        print("  OpenMontage updated to latest.")
        print("  Commit:  git add OpenMontage && git commit -m 'Update OpenMontage'")
    else:
        print("  Update failed. Check network / submodule state.")


def step_setup():
    venv = HERE / ".venv"
    if not venv.exists():
        print("  Creating uv virtual environment...")
        subprocess.run("uv venv", cwd=HERE, shell=True)

    print("  Installing Python dependencies (via uv)...")
    run("uv pip install -r requirements.txt", cwd=OM)
    print("  Installing Remotion composer (bun)...")
    run("bun install", cwd=OM / "remotion-composer")
    run("uv pip install piper-tts 2>/dev/null || echo '  [skip] piper-tts — cloud TTS still works'")

    env_path = HERE / ".env"
    example = OM / ".env.example"
    if not env_path.exists() and example.exists():
        shutil.copy(example, env_path)
        print("  Created .env from .env.example — add your API keys.")

    print("  Setup done.")


def step_preflight():
    print("  Running preflight (discovering tools)...")
    r = subprocess.run(
        ["uv", "run", "python", "-c",
         "from tools.tool_registry import registry; import json; "
         "registry.discover(); print(json.dumps(registry.provider_menu(), indent=2))"],
        cwd=OM, capture_output=True, text=True,
    )
    if r.returncode == 0:
        print(r.stdout)
    else:
        print("  Preflight failed:")
        print(r.stderr.strip() or r.stdout.strip())


def step_guide():
    guide = textwrap.dedent("""\
    ─── HOW TO MAKE A VIDEO WITH OPENMONTAGE ───

    Open THIS directory in your AI coding assistant and tell it what you want:

      "Make a 45-second animated explainer about why the sky is blue"
      "Create a cinematic 30-second trailer for a sci-fi concept"
      "Turn this YouTube link into a video like it, but about my topic"

    The agent reads OpenMontage/AGENT_GUIDE.md and drives the full pipeline:
    research → script → scene_plan → assets → edit → compose.

    Output goes to projects/ (gitignored). Docs:
      OpenMontage/AGENT_GUIDE.md  — full operating guide
      OpenMontage/README.md       — overview + prompt gallery
      uv run run.py               — re-run setup/update
    """)
    print(guide)


def main():
    check_submodule()
    banner()

    pinned = ""
    try:
        r = subprocess.run(
            "git -C OpenMontage log --oneline -1",
            cwd=HERE, shell=True, capture_output=True, text=True,
        )
        if r.returncode == 0:
            pinned = f"   (pinned at {r.stdout.strip()})"
    except Exception:
        pass

    print(f"\n  OpenMontage: submodule at {OM.resolve()}{pinned}\n")

    print("  [1/3] Updating OpenMontage to latest...")
    step_update()

    print("  [2/3] Running setup...")
    step_setup()

    print("  [3/3] Running preflight...")
    step_preflight()

    print("\n  Ready! OpenMontage is set up and updated.\n")
    step_guide()


if __name__ == "__main__":
    main()
