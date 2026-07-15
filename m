#!/usr/bin/env python3
"""montage-is-open — OpenMontage Pipeline Orchestrator.

Usage (human entry point):
  uv run m                       # Setup + guide (original behavior)
  uv run m help                  # This message

Setup & maintenance:
  uv run m setup                 # Install deps, create venv
  uv run m update                # Update OpenMontage submodule
  uv run m preflight             # Run capability preflight

Pipeline workflow:
  uv run m list-pipelines        # List available pipelines
  uv run m init <name> [topic]   # Init a new project
  uv run m status [project]      # Show pipeline progress
  uv run m run <project>         # Execute pipeline (resume-aware)
  uv run m stage <project> <s>   # Execute one stage

Stages (executed in order): research → proposal → script → scene_plan
→ assets → edit → compose → publish

Stages 1-3 (research, proposal, script): you provide artifact JSONs.
Stages 4-8: automated via OpenMontage tools.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
HERE = Path(__file__).resolve().parent
OM = HERE / "OpenMontage"
OM_AGENT_GUIDE = OM / "AGENT_GUIDE.md"
PIPELINE_DEFS_DIR = OM / "pipeline_defs"
PROJECTS_DIR = HERE / "projects"

# ---------------------------------------------------------------------------
# OpenMontage bootstrap — apply om_patch, add paths
# ---------------------------------------------------------------------------
def _bootstrap_openmontage():
    """Ensure OpenMontage modules are importable.

    Applies om_patch exactly once — reloading it re-patches and causes
    infinite recursion in schema loaders.
    """
    if str(OM) not in sys.path:
        sys.path.insert(0, str(OM))
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    # Import and apply om_patch exactly once
    if "om_patch" not in sys.modules:
        import importlib
        importlib.import_module("om_patch")
    try:
        from lib.env_loader import load_env as _le
        _le(HERE)
    except ImportError:
        pass  # env_loader is optional; tools load .env themselves


def _ensure_om_imports():
    """Lazy-import OpenMontage modules needed for pipeline execution."""
    _bootstrap_openmontage()


# ---------------------------------------------------------------------------
# Terminal helpers
# ---------------------------------------------------------------------------
def banner():
    width = shutil.get_terminal_size().columns
    print("=" * width)
    print("  montage-is-open — OpenMontage Pipeline Runner")
    print("=" * width)


def run_cmd(cmd, cwd=None, capture=False, check=False):
    """Run a shell command with optional capture."""
    print(f"  $ {cmd}")
    method = subprocess.run if not capture else (
        lambda *a, **kw: subprocess.run(*a, **kw, capture_output=True, text=True)
    )
    if capture:
        return method(cmd, cwd=cwd or HERE, shell=True)
    return method(cmd, cwd=cwd or HERE, shell=True, check=check)


def _project_path(name: str) -> Path:
    return PROJECTS_DIR / name


def _artifact_path(proj: Path) -> Path:
    return proj / "artifacts"


def _checkpoint_path(proj: Path) -> Path:
    return proj


def _assets_path(proj: Path) -> Path:
    return proj / "assets"


def _renders_path(proj: Path) -> Path:
    return proj / "renders"


STAGE_ORDER = [
    "research", "proposal", "script", "scene_plan",
    "assets", "edit", "compose", "publish",
]

STAGE_LABELS = {
    "research": "Research",
    "proposal": "Proposal",
    "script": "Script",
    "scene_plan": "Scene Plan",
    "assets": "Assets",
    "edit": "Edit",
    "compose": "Compose",
    "publish": "Publish",
}

STAGE_ARTIFACTS = {
    "research": "research_brief.json",
    "proposal": "proposal_packet.json",
    "script": "script.json",
    "scene_plan": "scene_plan.json",
    "assets": "asset_manifest.json",
    "edit": "edit_decisions.json",
    "compose": "render_report.json",
    "publish": "publish_log.json",
}


# ---------------------------------------------------------------------------
# Legacy maintenance commands
# ---------------------------------------------------------------------------
def cmd_update():
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


def cmd_setup():
    """Create venv, install deps, bootstrap Remotion."""
    venv = HERE / ".venv"
    if not venv.exists():
        print("  Creating uv virtual environment...")
        subprocess.run("uv venv", cwd=HERE, shell=True)

    print("  Installing Python dependencies (via uv)...")
    run_cmd("uv pip install -r requirements.txt", cwd=OM)
    print("  Installing Remotion composer (bun)...")
    run_cmd("bun install", cwd=OM / "remotion-composer")
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


def cmd_preflight():
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


def cmd_guide():
    """Print the agent guide for AI-assisted video production."""
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
      uv run m               — re-run setup/update

    Pipeline CLI (automated stages):
      uv run m list-pipelines
      uv run m init <project-name> [topic]
      uv run m run <project-name>
    """)
    print(guide)


# ---------------------------------------------------------------------------
# Pipeline commands
# ---------------------------------------------------------------------------
def cmd_list_pipelines():
    """List available pipeline manifests."""
    _ensure_om_imports()
    from lib.pipeline_loader import list_pipelines
    names = list_pipelines()
    print(f"\n  Available pipelines ({len(names)}):\n")
    for n in sorted(names):
        print(f"    - {n}")
    print()

def cmd_list_projects():
    """List existing projects in projects/."""
    if not PROJECTS_DIR.exists():
        print("  No projects directory found.")
        return
    dirs = sorted(d.name for d in PROJECTS_DIR.iterdir()
                  if d.is_dir() and not d.name.startswith("."))
    if not dirs:
        print("  No projects yet. Create one: uv run m init <name>")
        return
    print(f"\n  Existing projects ({len(dirs)}):\n")
    for name in dirs:
        cp_dir = _project_path(name) / name
        ckpts = list(cp_dir.glob("checkpoint_*.json")) if cp_dir.exists() else []
        stages_done = len(ckpts)
        print(f"    {name}{'  (' + str(stages_done) + '/8 stages)' if ckpts else ''}")
    print()
    print("  Run: uv run m status <name>  to see details")
    print()


def cmd_init(args):
    """Initialize a new project workspace with artifacts directory."""
    project_name = args.name
    topic = args.topic

    proj_dir = _project_path(project_name)
    if proj_dir.exists():
        print(f"  Project '{project_name}' already exists at {proj_dir}")
        if not args.force:
            return
        print("  (--force: overwriting checkpoints only)")

    # Create directory structure
    for d in [proj_dir, _artifact_path(proj_dir), _assets_path(proj_dir),
              _assets_path(proj_dir) / "images",
              _assets_path(proj_dir) / "audio",
              _assets_path(proj_dir) / "video",
              _assets_path(proj_dir) / "music",
              _renders_path(proj_dir)]:
        d.mkdir(parents=True, exist_ok=True)

    # Print init info and stage guidance
    print(f"\n  Project '{project_name}' initialized at: {proj_dir}\n")
    print(f"  Pipeline: animated-explainer (default)\n")
    print(f"  Topic: {topic or '(not specified)'}\n")
    print(f"  Next steps — provide creative artifacts, then run:\n")
    print(f"    uv run m status {project_name}")
    print(f"    uv run m run {project_name}")
    print()

    # Create a topic hint file so stages can reference it
    if topic:
        info = {"project": project_name, "topic": topic, "pipeline": "animated-explainer"}
        with open(proj_dir / "project.json", "w") as f:
            json.dump(info, f, indent=2)


def cmd_status(args):
    """Show pipeline progress for a project."""
    _ensure_om_imports()
    from lib.checkpoint import get_completed_stages

    project_name = args.name or _find_latest_project()
    if not project_name:
        print("  No projects found in projects/")
        return

    proj_dir = _project_path(project_name)
    if not proj_dir.exists():
        print(f"  Project '{project_name}' not found")
        return

    completed_raw = get_completed_stages(proj_dir, project_name)
    # Filter to only stages we track
    completed = [s for s in STAGE_ORDER if s in completed_raw]

    # Determine next stage from our order
    next_stage = None
    for s in STAGE_ORDER:
        if s not in completed:
            next_stage = s
            break

    print(f"\n  Project: {project_name}")
    print(f"  Directory: {proj_dir}\n")

    for s in STAGE_ORDER:
        label = STAGE_LABELS.get(s, s)
        if s in completed:
            print(f"    ✅ {label}")
        elif s == next_stage:
            print(f"    ⏳ {label}  ← next")
        else:
            print(f"    ⬜ {label}")

    if next_stage is None:
        print("\n  🎉 Pipeline complete!")
    else:
        print(f"\n  Next stage: {STAGE_LABELS.get(next_stage, next_stage)}")
        print(f"  Run: uv run m stage {project_name} {next_stage}")
    print()


# ---------------------------------------------------------------------------
# Stage execution
def _write_checkpoint(proj_dir, project_name, stage, status, artifacts_dict):
    """Write a checkpoint via OpenMontage's checkpoint lib."""
    _ensure_om_imports()
    from lib.checkpoint import write_checkpoint
    return write_checkpoint(
        pipeline_dir=proj_dir,
        project_id=project_name,
        stage=stage,
        status=status,
        artifacts=artifacts_dict,
    )


def _read_checkpoint(proj_dir, project_id, stage):
    """Read checkpoint data for a stage directly (avoids schema validation)."""
    path = proj_dir / project_id / f"checkpoint_{stage}.json"
    if not path.exists():
        return None
    try:
        with open(path) as f:
            cp = json.load(f)
        if cp and "artifacts" in cp:
            return cp["artifacts"]
    except Exception:
        pass
    return None


def _read_artifact(proj_dir, artifact_name):
    """Read a JSON artifact from the project's artifacts dir."""
    path = _artifact_path(proj_dir) / artifact_name
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)

def _check_artifact_exists(proj_dir, stage):
    """Check if the canonical artifact for this stage exists."""
    art_name = STAGE_ARTIFACTS.get(stage)
    if not art_name:
        return True  # no artifact expected
    path = _artifact_path(proj_dir) / art_name
    exists = path.exists()
    if not exists:
        print(f"  ⚠ Artifact missing: {art_name}")
        print(f"    Expected at: {path}")
    return exists


def _get_project_id(proj_dir):
    """Derive project_id from directory name."""
    return proj_dir.name


def stage_research(proj_dir):
    """Stage 1: research — validate research_brief.json exists."""
    project_id = _get_project_id(proj_dir)
    print(f"\n  🎬 Stage: Research")

    if not _check_artifact_exists(proj_dir, "research"):
        print(f"  Create research_brief.json in {_artifact_path(proj_dir)}")
        print(f"  Schema: OpenMontage/schemas/artifacts/research_brief.schema.json\n")
        print(f"  Required fields: topic, data_points[], angles_discovered[], sources[], research_summary")
        return False

    brief = _read_artifact(proj_dir, "research_brief.json")
    print(f"  Topic: {brief.get('topic', 'unknown')}")
    print(f"  Data points: {len(brief.get('data_points', []))}")
    print(f"  Angles: {len(brief.get('angles_discovered', []))}")
    print(f"  Sources: {len(brief.get('sources', []))}")

    _write_checkpoint(proj_dir, project_id, "research", "completed",
                       {"research_brief": brief})
    print(f"  ✅ Research checkpoint written\n")
    return True


def stage_proposal(proj_dir):
    """Stage 2: proposal — validate proposal_packet.json exists with approval."""
    project_id = _get_project_id(proj_dir)
    print(f"\n  🎬 Stage: Proposal")

    if not _check_artifact_exists(proj_dir, "proposal"):
        print(f"  Create proposal_packet.json in {_artifact_path(proj_dir)}")
        print(f"  Schema: OpenMontage/schemas/artifacts/proposal_packet.schema.json\n")
        print(f"  Required: concept_options[], selected_concept, production_plan, cost_estimate, approval")
        return False

    packet = _read_artifact(proj_dir, "proposal_packet.json")
    selected = packet.get("selected_concept", {})
    approval = packet.get("approval", {})
    print(f"  Selected concept: {selected.get('concept_id', '?')}")
    print(f"  Approval status: {approval.get('status', 'pending')}")
    print(f"  Budget: ${approval.get('approved_budget_usd', '?')}")

    approval_status = approval.get("status", "pending")
    if approval_status not in ("approved", "approved_with_changes"):
        print(f"\n  ⛔ Proposal not yet approved (status: {approval_status})")
        print(f"  Set approval.status to 'approved' or 'approved_with_changes' to proceed.\n")
        # Still write checkpoint so status command reflects state
        _write_checkpoint(proj_dir, project_id, "proposal", "awaiting_human",
                           {"proposal_packet": packet})
        return False

    _write_checkpoint(proj_dir, project_id, "proposal", "completed",
                       {"proposal_packet": packet})
    print(f"  ✅ Proposal checkpoint written\n")
    return True


def stage_script(proj_dir):
    """Stage 3: script — validate script.json exists."""
    project_id = _get_project_id(proj_dir)
    print(f"\n  🎬 Stage: Script")

    if not _check_artifact_exists(proj_dir, "script"):
        print(f"  Create script.json in {_artifact_path(proj_dir)}")
        print(f"  Schema: OpenMontage/schemas/artifacts/script.schema.json\n")
        print(f"  Required: sections[] with id, text, duration_seconds, enhancement_cues[]")
        return False

    script = _read_artifact(proj_dir, "script.json")
    sections = script.get("sections", [])
    total_words = sum(len(s.get("text", "").split()) for s in sections)
    total_dur = sum(s.get("duration_seconds", 0) for s in sections)
    print(f"  Sections: {len(sections)}")
    print(f"  Words: {total_words}, Estimated duration: {total_dur}s")

    _write_checkpoint(proj_dir, project_id, "script", "completed",
                       {"script": script})
    print(f"  ✅ Script checkpoint written\n")
    return True


def stage_scene_plan(proj_dir):
    """Stage 4: scene_plan — generate from script or validate existing."""
    project_id = _get_project_id(proj_dir)
    print(f"\n  🎬 Stage: Scene Plan")

    # Use existing scene_plan if present
    if _check_artifact_exists(proj_dir, "scene_plan"):
        plan = _read_artifact(proj_dir, "scene_plan.json")
        print(f"  Using existing scene plan")
    else:
        # Auto-generate from script
        script = _read_artifact(proj_dir, "script.json")
        if not script:
            print(f"  ⚠ No script.json found — cannot generate scene plan")
            print(f"  Complete the Script stage first, or create scene_plan.json manually.\n")
            return False

        sections = script.get("sections", [])
        print(f"  Generating scene plan from {len(sections)} script sections...")

        scenes = []
        for i, sec in enumerate(sections):
            section_id = sec.get("id", f"s{i+1}")
            text = sec.get("text", "")
            dur = sec.get("duration_seconds", 5.0)
            cues = sec.get("enhancement_cues", [])

            # Determine scene type from cues or default
            scene_type = "explainer"
            if any("stat" in (c.get("type","") or "") for c in cues):
                scene_type = "stat"
            elif any("code" in (c.get("type","") or "") for c in cues):
                scene_type = "code_snippet"
            elif any("diagram" in (c.get("type","") or "") for c in cues):
                scene_type = "diagram"

            scenes.append({
                "id": f"scene-{section_id}",
                "script_section_id": section_id,
                "type": scene_type,
                "duration_seconds": dur,
                "narration_text": text,
                "required_assets": [
                    {"type": "image", "description": f"Visual for: {text[:80]}"},
                    {"type": "narration", "section_id": section_id},
                ],
                "visual_description": f"Animated explainer scene illustrating: {text[:120]}",
                "transitions": {"in": "fade", "out": "fade"},
            })

        plan = {
            "version": "1.0",
            "scenes": scenes,
            "total_duration_seconds": sum(s["duration_seconds"] for s in scenes),
            "metadata": {
                "generated_by": "run.py scene_plan stage",
                "source": "auto-generated from script",
            },
        }

        # Write scene_plan.json
        art_dir = _artifact_path(proj_dir)
        with open(art_dir / "scene_plan.json", "w") as f:
            json.dump(plan, f, indent=2)
        print(f"  Generated {len(scenes)} scenes")

    print(f"  Scenes: {len(plan.get('scenes', []))}")
    print(f"  Total duration: {plan.get('total_duration_seconds', '?')}s")

    _write_checkpoint(proj_dir, project_id, "scene_plan", "completed",
                       {"scene_plan": plan})
    print(f"  ✅ Scene Plan checkpoint written\n")
    return True


def stage_assets(proj_dir):
    """Stage 5: assets — generate TTS narration and background music."""
    _ensure_om_imports()
    project_id = _get_project_id(proj_dir)
    print(f"\n  🎬 Stage: Assets")

    # Read required artifacts
    script = _read_artifact(proj_dir, "script.json")
    scene_plan = _read_artifact(proj_dir, "scene_plan.json")

    if not script:
        print("  ⚠ No script.json found. Complete the Script stage first.\n")
        return False
    if not scene_plan:
        print("  ⚠ No scene_plan.json found. Complete the Scene Plan stage first.\n")
        return False

    audio_dir = _assets_path(proj_dir) / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    music_dir = _assets_path(proj_dir) / "music"
    music_dir.mkdir(parents=True, exist_ok=True)

    sections = script.get("sections", [])
    audio_files = []

    # --- Narration (TTS) ---
    print("  Generating narration (TTS)...")

    # Try FishSpeechTTS first, fall back to PiperTTS
    tts = None
    is_fish = False

    try:
        from custom_tools.fish_speech_tts import FishSpeechTTS
        fish = FishSpeechTTS()
        fish_status = fish.get_status()
        from tools.base_tool import ToolStatus
        if fish_status == ToolStatus.AVAILABLE:
            tts = fish
            is_fish = True
            print("    Using Fish Speech TTS")
    except Exception:
        pass

    if tts is None:
        try:
            from tools.audio.piper_tts import PiperTTS as _PiperTTS
            tts = _PiperTTS()
            print("    Using Piper TTS")
        except Exception as e:
            print(f"    ⚠ No local TTS available: {e}")
            print("    Set FISH_API_KEY in .env for cloud TTS, or install piper-tts")

    # Generate TTS per section
    if tts:
        for sec in sections:
            sec_id = sec.get("id", "unknown")
            text = sec.get("text", "")
            if not text.strip():
                continue

            output_wav = audio_dir / f"narration_{sec_id}.wav"
            try:
                tts_args = {
                    "text": text,
                    "output_path": str(output_wav),
                }
                if is_fish:
                    tts_args["voice"] = "default"
                result = tts.execute(tts_args)
                if result.success:
                    audio_files.append(str(output_wav))
                    print(f"    ✅ {sec_id}: generated ({len(text)} chars)")
                else:
                    print(f"    ⚠ {sec_id}: TTS failed — {result.error}")
            except Exception as e:
                print(f"    ⚠ {sec_id}: TTS error — {e}")

    # --- Background Music ---
    print("\n  Downloading background music...")
    music_path = music_dir / "background.mp3"
    music_success = False

    try:
        from tools.audio.pixabay_music import PixabayMusic
        pm = PixabayMusic()
        music_result = pm.execute({
            "query": "calm background corporate",
            "output_path": str(music_path),
            "duration_seconds": 120,
        })
        if music_result.success:
            music_success = True
            print(f"    ✅ Background music: {music_path}")
        else:
            print(f"    ⚠ Pixabay music failed: {music_result.error}")
    except Exception as e:
        print(f"    ⚠ Music generation unavailable: {e}")

    # If no music from Pixabay, try music_gen
    if not music_success:
        try:
            from tools.audio.music_gen import MusicGen
            mg = MusicGen()
            mg_result = mg.execute({
                "prompt": "ambient corporate background music",
                "duration_seconds": 120,
                "output_path": str(music_path),
            })
            if mg_result.success:
                music_success = True
                print(f"    ✅ Background music (via MusicGen): {music_path}")
        except Exception:
            pass

    print(f"\n  Audio files: {len(audio_files)}")
    print(f"  Background music: {'yes' if music_success else 'no'}")

    # Build asset manifest
    assets = []
    for af in audio_files:
        p = Path(af)
        assets.append({
            "id": p.stem,
            "type": "audio",
            "subtype": "narration",
            "path": str(p.relative_to(proj_dir)),
            "format": "wav",
        })
    if music_success:
        assets.append({
            "id": "background_music",
            "type": "audio",
            "subtype": "music",
            "path": str(music_path.relative_to(proj_dir)),
            "format": "mp3",
        })

    asset_manifest = {
        "version": "1.0",
        "project": project_id,
        "assets": assets,
        "metadata": {"generated_by": "run.py assets stage"},
    }

    art_dir = _artifact_path(proj_dir)
    with open(art_dir / "asset_manifest.json", "w") as f:
        json.dump(asset_manifest, f, indent=2)

    _write_checkpoint(proj_dir, project_id, "assets", "completed",
                       {"asset_manifest": asset_manifest})
    print(f"  ✅ Assets checkpoint written\n")
    return True


def stage_edit(proj_dir):
    """Stage 6: edit — generate edit_decisions from scene_plan + assets."""
    _ensure_om_imports()
    project_id = _get_project_id(proj_dir)
    print(f"\n  🎬 Stage: Edit")

    scene_plan = _read_artifact(proj_dir, "scene_plan.json")
    asset_manifest = _read_artifact(proj_dir, "asset_manifest.json")

    if not scene_plan:
        print("  ⚠ No scene_plan.json found\n")
        return False
    if not asset_manifest:
        print("  ⚠ No asset_manifest.json found\n")
        return False

    scenes = scene_plan.get("scenes", [])
    assets = asset_manifest.get("assets", [])

    # Map audio assets by section id
    audio_map = {}
    for a in assets:
        if a.get("subtype") == "narration":
            # Extract section id from filename: narration_s1.wav → s1
            stem = Path(a["path"]).stem
            parts = stem.split("_", 1)
            if len(parts) > 1:
                audio_map[parts[1]] = a["path"]

    timeline = []
    current_time = 0.0

    for i, scene in enumerate(scenes):
        sec_id = scene.get("script_section_id", f"s{i+1}")
        dur = scene.get("duration_seconds", 5.0)

        entry = {
            "scene_id": scene.get("id", f"scene-{sec_id}"),
            "start_time": round(current_time, 2),
            "end_time": round(current_time + dur, 2),
            "duration_seconds": dur,
            "type": scene.get("type", "explainer"),
            "narration_asset": audio_map.get(sec_id),
            "visuals": [],
        }

        if scene.get("required_assets"):
            for ra in scene["required_assets"]:
                if ra.get("type") == "image":
                    entry["visuals"].append({
                        "type": "image",
                        "description": ra.get("description", ""),
                        "duration_seconds": dur,
                    })

        timeline.append(entry)
        current_time += dur

    edit_decisions = {
        "version": "1.0",
        "project": project_id,
        "total_duration_seconds": round(current_time, 2),
        "timeline": timeline,
        "audio_mix": {
            "narration_volume": 0.8,
            "music_volume": 0.3,
            "music_ducking": True,
            "ducking_reduce_by_db": 6.0,
        },
        "subtitles": {"enabled": True, "style": "clean"},
        "render_runtime": "remotion",
        "metadata": {"generated_by": "run.py edit stage"},
    }

    art_dir = _artifact_path(proj_dir)
    with open(art_dir / "edit_decisions.json", "w") as f:
        json.dump(edit_decisions, f, indent=2)

    print(f"  Scenes in timeline: {len(timeline)}")
    print(f"  Total duration: {edit_decisions['total_duration_seconds']}s")

    _write_checkpoint(proj_dir, project_id, "edit", "completed",
                       {"edit_decisions": edit_decisions})
    print(f"  ✅ Edit checkpoint written\n")
    return True


def stage_compose(proj_dir):
    """Stage 7: compose — mix audio and render video via VideoCompose."""
    _ensure_om_imports()
    project_id = _get_project_id(proj_dir)
    print(f"\n  🎬 Stage: Compose")

    edit_decisions = _read_artifact(proj_dir, "edit_decisions.json")
    asset_manifest = _read_artifact(proj_dir, "asset_manifest.json")

    if not edit_decisions:
        print("  ⚠ No edit_decisions.json found\n")
        return False
    if not asset_manifest:
        print("  ⚠ No asset_manifest.json found\n")
        return False

    audio_dir = _assets_path(proj_dir) / "audio"
    renders_dir = _renders_path(proj_dir)
    renders_dir.mkdir(parents=True, exist_ok=True)

    # --- Audio Mix ---
    print("  Mixing audio...")
    try:
        from tools.audio.audio_mixer import AudioMixer
        mixer = AudioMixer()
        final_mix = audio_dir / "final_mix.wav"

        mix_config = {
            "output_path": str(final_mix),
            "narration_tracks": [],
            "music_track": None,
            "ducking": edit_decisions.get("audio_mix", {}).get("music_ducking", True),
        }

        for entry in edit_decisions.get("timeline", []):
            nar = entry.get("narration_asset")
            if nar:
                abs_path = str((proj_dir / nar).resolve())
                if os.path.exists(abs_path):
                    mix_config["narration_tracks"].append({
                        "path": abs_path,
                        "start_time": entry["start_time"],
                        "volume": edit_decisions.get("audio_mix", {}).get("narration_volume", 0.8),
                    })

        for a in asset_manifest.get("assets", []):
            if a.get("subtype") == "music":
                music_path = str((proj_dir / a["path"]).resolve())
                if os.path.exists(music_path):
                    mix_config["music_track"] = {
                        "path": music_path,
                        "volume": edit_decisions.get("audio_mix", {}).get("music_volume", 0.3),
                    }

        mix_result = mixer.execute(mix_config)
        if mix_result.success:
            print(f"    ✅ Audio mixed: {final_mix}")
        else:
            print(f"    ⚠ Audio mixing issue: {mix_result.error}")
    except Exception as e:
        print(f"    ⚠ Audio mix unavailable: {e}")

    # --- Video Composition ---
    print("\n  Rendering video...")
    output_path = renders_dir / "final.mp4"

    try:
        from tools.video.video_compose import VideoCompose
        composer = VideoCompose()

        compose_inputs = {
            "edit_decisions": edit_decisions,
            "asset_manifest": asset_manifest,
            "project_dir": str(proj_dir),
            "output_path": str(output_path),
        }

        # Check render_runtime from edit_decisions
        runtime = edit_decisions.get("render_runtime", "remotion")
        print(f"    Using runtime: {runtime}")

        compose_result = composer.execute(compose_inputs)
        if compose_result.success:
            print(f"    ✅ Video rendered: {output_path}")
        else:
            print(f"    ⚠ Composition failed: {compose_result.error}")
            print(f"    Output may not be available.\n")
            return False
    except Exception as e:
        print(f"    ⚠ Video composition unavailable: {e}")
        print(f"    Install Remotion dependencies: cd OpenMontage/remotion-composer && bun install\n")
        return False

    # --- Write Render Report ---
    file_size = output_path.stat().st_size if output_path.exists() else 0
    render_report = {
        "version": "1.0",
        "project": project_id,
        "output_path": str(output_path),
        "duration_seconds": edit_decisions.get("total_duration_seconds", 0),
        "file_size_bytes": file_size,
        "render_runtime": runtime,
        "status": "completed",
        "metadata": {"generated_by": "run.py compose stage"},
    }

    art_dir = _artifact_path(proj_dir)
    with open(art_dir / "render_report.json", "w") as f:
        json.dump(render_report, f, indent=2)

    _write_checkpoint(proj_dir, project_id, "compose", "completed",
                       {"render_report": render_report})
    print(f"  ✅ Compose checkpoint written\n")
    print(f"  📹 Final video: {output_path} ({file_size / 1024 / 1024:.1f} MB)")
    return True




def _normalize_render_report(rr):
    """Unify render_report to flattened format (output_path)."""
    if rr is None:
        return None
    if "output_path" in rr:
        return rr  # already flattened
    outputs = rr.get("outputs", [])
    if outputs:
        return {
            "output_path": outputs[0].get("path", ""),
            "duration_seconds": outputs[0].get("duration_seconds", 0),
            "file_size_bytes": outputs[0].get("file_size_bytes", 0),
        }
    # Empty outputs — try to use rr as-is but set empty output_path
    return {"output_path": "", "duration_seconds": 0, "file_size_bytes": 0}


def stage_publish(proj_dir):
    """Stage 8: publish — create export package."""
    project_id = _get_project_id(proj_dir)
    print(f"\n  🎬 Stage: Publish")

    # Try to get render_report from artifact, then checkpoint
    raw_rr = _read_artifact(proj_dir, "render_report.json")
    if not raw_rr:
        cp_artifacts = _read_checkpoint(proj_dir, project_id, "compose")
        if cp_artifacts and "render_report" in cp_artifacts:
            raw_rr = cp_artifacts["render_report"]
            # Persist as artifact for future runs
            art_dir = _artifact_path(proj_dir)
            with open(art_dir / "render_report.json", "w") as f:
                json.dump(raw_rr, f, indent=2)
            print(f"  Recovered render_report from checkpoint")

    render_report = _normalize_render_report(raw_rr)

    if not render_report or not render_report.get("output_path"):
        print("  ⚠ No render_report found. Complete the Compose stage first.\n")
        return False

    output_path = render_report["output_path"]
    if not Path(output_path).exists():
        print(f"  ⚠ Output video not found at: {output_path}")
        return False

    # Create export package
    export_dir = proj_dir / "export"
    publish_log = {
        "version": "1.0",
        "entries": [
            {
                "platform": "export",
                "status": "exported",
                "timestamp": "",
                "export_path": str(export_dir),
            }
        ],
    }

    art_dir = _artifact_path(proj_dir)
    with open(art_dir / "publish_log.json", "w") as f:
        json.dump(publish_log, f, indent=2)

    _write_checkpoint(proj_dir, project_id, "publish", "completed",
                       {"publish_log": publish_log})
    print(f"  ✅ Publish checkpoint written\n")
    print(f"  📦 Export package: {export_dir}")
    return True


STAGE_FUNCS = {
    "research": stage_research,
    "proposal": stage_proposal,
    "script": stage_script,
    "scene_plan": stage_scene_plan,
    "assets": stage_assets,
    "edit": stage_edit,
    "compose": stage_compose,
    "publish": stage_publish,
}


def _find_latest_project():
    """Find the most recently modified project directory."""
    if not PROJECTS_DIR.exists():
        return None
    projects = sorted(PROJECTS_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    projects = [p for p in projects if p.is_dir() and not p.name.startswith(".")]
    return projects[0].name if projects else None


def cmd_stage(args):
    """Execute a single pipeline stage."""
    _ensure_om_imports()
    project_name = args.project
    stage_name = args.stage

    proj_dir = _project_path(project_name)
    if not proj_dir.exists():
        print(f"  Project '{project_name}' not found at {proj_dir}")
        print(f"  Run: uv run m init {project_name}")
        return False

    if stage_name not in STAGE_FUNCS:
        print(f"  Unknown stage: {stage_name}")
        print(f"  Available: {', '.join(STAGE_ORDER)}")
        return False

    func = STAGE_FUNCS[stage_name]
    return func(proj_dir)


def cmd_run(args):
    """Run pipeline from current state through completion."""
    project_name = args.project

    _ensure_om_imports()
    from lib.checkpoint import get_completed_stages

    proj_dir = _project_path(project_name)
    if not proj_dir.exists():
        print(f"  Project '{project_name}' not found at {proj_dir}")
        print(f"  Run: uv run m init {project_name}")
        return

    print(f"\n  Pipeline run for: {project_name}\n")

    completed_raw = get_completed_stages(proj_dir, project_name)
    completed = [s for s in STAGE_ORDER if s in completed_raw]

    # Find first incomplete stage in our order
    next_stage = None
    for s in STAGE_ORDER:
        if s not in completed:
            next_stage = s
            break

    if next_stage is None:
        print("  🎉 Pipeline already complete!")
        render = _read_artifact(proj_dir, "render_report.json")
        if render:
            print(f"  Final video: {render.get('output_path', '?')}")
        return

    if completed:
        print(f"  Resuming from: {STAGE_LABELS.get(next_stage, next_stage)}")
        print(f"  Completed stages: {', '.join(STAGE_LABELS.get(s,s) for s in completed)}\n")

    # Find start index
    start_idx = STAGE_ORDER.index(next_stage)

    for stage_name in STAGE_ORDER[start_idx:]:
        label = STAGE_LABELS.get(stage_name, stage_name)
        print(f"  ── {label} ──")

        func = STAGE_FUNCS[stage_name]
        success = func(proj_dir)

        if not success:
            print(f"\n  ⛔ Stopped at: {label}")
            print(f"  Fix the issue and run again to resume.\n")
            return

    print(f"\n  🎉 Pipeline complete for '{project_name}'!")
    render = _read_artifact(proj_dir, "render_report.json")
    if render and render.get("output_path"):
        out = render["output_path"]
        if Path(out).exists():
            sz = Path(out).stat().st_size
            print(f"  📹 {out} ({sz / 1024 / 1024:.1f} MB)")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    check_submodule()
    banner()

    parser = argparse.ArgumentParser(
        description="montage-is-open — OpenMontage Pipeline Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Stages (in order): research → proposal → script → scene_plan
            → assets → edit → compose → publish

            Creative stages (1-3): provide artifact JSONs in artifacts/.
            Automated stages (4-8): run via OpenMontage tools.
            """),
    )
    parser.add_argument("--version", action="version", version="montage-is-open 0.2")

    sub = parser.add_subparsers(dest="command", help="Sub-command")

    # Legacy commands
    sub.add_parser("setup", help="Install deps, create venv")
    sub.add_parser("update", help="Update OpenMontage submodule")
    sub.add_parser("preflight", help="Run capability preflight")
    sub.add_parser("guide", help="Show the AI agent guide")

    # Pipeline commands

    sub.add_parser("list", help="List existing projects")
    sub.add_parser("list-pipelines", help="List available pipeline manifests")

    p_init = sub.add_parser("init", help="Initialize a new project")
    p_init.add_argument("name", help="Project name (directory under projects/)")
    p_init.add_argument("topic", nargs="?", default=None, help="Video topic")
    p_init.add_argument("--force", action="store_true", help="Overwrite existing checkpoints")

    p_status = sub.add_parser("status", help="Show pipeline progress")
    p_status.add_argument("name", nargs="?", default=None, help="Project name (default: latest)")

    p_run = sub.add_parser("run", help="Execute pipeline (resume-aware)")
    p_run.add_argument("project", help="Project name")

    p_stage = sub.add_parser("stage", help="Execute a single stage")
    p_stage.add_argument("project", help="Project name")
    p_stage.add_argument("stage", choices=STAGE_ORDER, help="Stage to execute")

    # Show pinned submodule version
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

    args = parser.parse_args()

    if args.command is None:
        # Default: full setup + guide (original behavior)
        _default_guide()
        return

    # Dispatch
    dispatch = {
        "setup": lambda: _chain_or_standalone(cmd_setup),
        "update": cmd_update,
        "preflight": cmd_preflight,
        "guide": cmd_guide,
        "list": cmd_list_projects,
        "list-pipelines": cmd_list_pipelines,
        "init": lambda: cmd_init(args),
        "status": lambda: cmd_status(args),
        "run": lambda: cmd_run(args),
        "stage": lambda: cmd_stage(args),
    }

    handler = dispatch.get(args.command)
    if handler:
        handler()


def _default_guide():
    """Print a self-explanatory workflow guide for the human."""
    width = min(shutil.get_terminal_size().columns, 100)

    print()
    print("  ╭" + "─" * (width - 4) + "╮")
    print("  │" + "   MONTAGE-IS-OPEN  —  AI Video Production Pipeline".ljust(width - 4) + "│")
    print("  ╰" + "─" * (width - 4) + "╯")
    print()
    print("  This tool runs an 8-stage pipeline to produce animated explainer videos.")
    print("  Stages 1-3 are creative — you provide structured JSON files.")
    print("  Stages 4-8 are automated — the pipeline generates assets and renders.")
    print()
    print("  ── WORKFLOW ──")
    print()
    print("  1. Create a project")
    print()
    print("       uv run m init my-video")
    print()
    print("     Creates  projects/my-video/  with subdirectories:")
    print("       artifacts/    — your hand-crafted JSON files (stages 1-3)")
    print("       assets/      — generated images, audio, video")
    print("       renders/     — final video output")
    print()
    print("  2. Provide creative artifacts (stages 1-3 — manual)")
    print()
    print("     You create JSON files in  projects/my-video/artifacts/")
    print("     following the schemas in  OpenMontage/schemas/artifacts/")
    print()
    print("     ─── Stage 1: Research ───")
    print("     File: artifacts/research_brief.json")
    print("     Schema: OpenMontage/schemas/artifacts/research_brief.schema.json")
    print()
    print('       {\n'
          '         "version": "1.0",\n'
          '         "topic": "Your video topic",\n'
          '         "research_date": "2026-07-14",\n'
          '         "landscape": {\n'
          '           "existing_content": "What already exists",\n'
          '           "saturated_angles": ["tired angle"],\n'
          '           "underserved_gaps": ["fresh angle"]\n'
          '         },\n'
          '         "data_points": [\n'
          '           {"fact": "Key stat", "source": "url", "relevance": "why it matters"}\n'
          '         ],\n'
          '         "audience_insights": {\n'
          '           "target_demographic": "who",\n'
          '           "pain_points": [],\n'
          '           "desires": []\n'
          '         },\n'
          '         "angles_discovered": [\n'
          '           {"name": "Angle", "hook": "One-liner", "why_effective": "reason"}\n'
          '         ],\n'
          '         "sources": [{"title": "...", "url": "...", "credibility": "high|medium|low"}]\n'
          '       }')
    print()
    print("     ─── Stage 2: Proposal ───")
    print("     File: artifacts/proposal_packet.json")
    print("     Schema: OpenMontage/schemas/artifacts/proposal_packet.schema.json")
    print()
    print('       {\n'
          '         "version": "1.0",\n'
          '         "concept_options": [\n'
          '           {"id": "A", "title": "...", "hook": "...",\n'
          '            "narrative_structure": "...", "visual_approach": "...",\n'
          '            "target_duration_seconds": 45, "why_this_works": "..."}\n'
          '         ],\n'
          '         "selected_concept": {"concept_id": "A", "rationale": "..."},\n'
          '         "production_plan": {\n'
          '           "pipeline": "animated-explainer",\n'
          '           "stages": ["script","scene_plan","assets","edit","compose","publish"],\n'
          '           "render_runtime": "remotion"\n'
          '         },\n'
          '         "cost_estimate": {\n'
          '           "total_estimated_usd": 0,\n'
          '           "line_items": [],\n'
          '           "budget_verdict": "feasible"\n'
          '         },\n'
          '         "approval": {"status": "approved", "approved_by": "you", "date": "2026-07-14"}\n'
          '       }')
    print()
    print("     ─── Stage 3: Script ───")
    print("     File: artifacts/script.json")
    print("     Schema: OpenMontage/schemas/artifacts/script.schema.json")
    print()
    print('       {\n'
          '         "version": "1.0",\n'
          '         "title": "My Video",\n'
          '         "total_duration_seconds": 45,\n'
          '         "sections": [\n'
          '           {\n'
          '             "id": "intro",\n'
          '             "text": "Narration line spoken over this section.",\n'
          '             "start_seconds": 0,\n'
          '             "end_seconds": 10,\n'
          '             "enhancement_cues": [\n'
          '               {"type": "overlay", "description": "Text overlay: key stat"}\n'
          '             ]\n'
          '           }\n'
          '         ]\n'
          '       }')
    print()
    print("  3. Run the pipeline (resumes where you left off)")
    print()
    print("       uv run m run my-video")
    print()
    print("     Stages 4-8 auto-generate: scene plan, assets (TTS, images),")
    print("     edit decisions, video composition, and export.")
    print()
    print("  ── ALL COMMANDS ──")
    print()
    print("    uv run m setup                  Install deps, create venv")
    print("    uv run m update                 Update OpenMontage submodule")
    print("    uv run m preflight              Run capability preflight")
    print("    uv run m guide                  Show the AI agent guide")
    print("    uv run m init <name>            Create a new project")
    print("    uv run m status <name>          See what's done and what's next")
    print("    uv run m list                   List all projects")
    print("    uv run m list-pipelines         List available pipeline manifests")
    print("    uv run m run <name>             Run all remaining stages")
    print("    uv run m stage <name> <stage>   Run one stage (e.g. script)")
    print()
    print("  ── OR LET AN AI AGENT DO IT ──")
    print()
    print("  Open this directory in an AI coding assistant and say:")
    print('    "Make a 45-second animated explainer about [your topic]"')
    print()
    print("  The agent will read  OpenMontage/AGENT_GUIDE.md  and drive")
    print("  the full pipeline end-to-end, including artifact generation.")
    print()
    print("  ╭" + "─" * (width - 4) + "╮")
    print("  │" + "   Schemas:    OpenMontage/schemas/artifacts/".ljust(width - 4) + "│")
    print("  │" + "   Guide:      OpenMontage/AGENT_GUIDE.md".ljust(width - 4) + "│")
    print("  │" + "   Projects:   projects/<name>/".ljust(width - 4) + "│")
    print("  ╰" + "─" * (width - 4) + "╯")
    print()


def _chain_or_standalone(fn):
    """Run a single setup sub-command without chaining."""

    fn()


def check_submodule():
    if not OM.exists():
        print("[!] OpenMontage submodule not found. Run: git submodule update --init --recursive")
        sys.exit(1)
    if not OM_AGENT_GUIDE.exists():
        print("[!] OpenMontage is incomplete. Try: git submodule update --init --recursive")
        sys.exit(1)


if __name__ == "__main__":
    main()
