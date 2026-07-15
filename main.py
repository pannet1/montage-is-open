#!/usr/bin/env python3
"""montage-is-open — OpenMontage Pipeline Orchestrator.

Setup & maintenance:
  uv run init                   # First-time setup (setup + update + preflight)
Pipeline workflow:
  uv run list                    # List projects, pipelines, stages
  uv run init <name> [topic]     # Init a new project
  uv run status [project]        # Show pipeline progress
  uv run main <name>              # Run all remaining stages
  uv run stage <project> <s>     # Execute one stage
  uv run main                    # Show setup guide


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

def _get_pipeline_type(proj_dir):
    """Read pipeline_type from any existing checkpoint."""
    cp_dir = proj_dir / proj_dir.name
    if cp_dir.is_dir():
        for f in sorted(cp_dir.glob("checkpoint_*.json")):
            try:
                data = json.loads(f.read_text())
                pt = data.get("pipeline_type")
                if pt:
                    return pt
            except Exception:
                continue
    return None


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

STAGE_MODE = {
    "research":     "human",
    "proposal":     "human",
    "script":       "human",
    "scene_plan":   "mixed",
    "assets":       "ai",
    "edit":         "ai",
    "compose":      "ai",
    "publish":      "ai",
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




# ---------------------------------------------------------------------------
# Pipeline commands
# ---------------------------------------------------------------------------
def cmd_list():
    """List projects, available pipelines, and all stages."""
    _ensure_om_imports()
    from lib.checkpoint import get_completed_stages
    from lib.pipeline_loader import list_pipelines

    # Section 1: Projects
    print(f"\n  {'─' * 50}")
    print("  PROJECTS")
    print(f"  {'─' * 50}\n")

    if not PROJECTS_DIR.exists():
        print("  No projects directory yet.\n")
    else:
        dirs = sorted(d.name for d in PROJECTS_DIR.iterdir()
                      if d.is_dir() and not d.name.startswith("."))
        if not dirs:
            print("  No projects yet.  Create one:  uv run init <name>\n")
        else:
            for name in dirs:
                proj_dir = _project_path(name)
                pt = _get_pipeline_type(proj_dir)
                cp_dir = proj_dir / proj_dir.name
                if pt is None and not (cp_dir.is_dir() and any(cp_dir.glob("checkpoint_*.json"))):
                    completed = []
                else:
                    try:
                        completed_raw = get_completed_stages(proj_dir, name, pt)
                        completed = [s for s in STAGE_ORDER if s in completed_raw]
                    except Exception:
                        completed = []

                count = len(completed)
                if count >= len(STAGE_ORDER):
                    continue
                if count == 0:
                    status = "not started"
                else:
                    curr = STAGE_LABELS.get(completed[-1], completed[-1])
                    nxt = STAGE_LABELS.get(STAGE_ORDER[count], STAGE_ORDER[count])
                    status = f"{curr} done  (next: {nxt})"

                print(f"    {name:24s}  {count}/{len(STAGE_ORDER)}  {status}")

    # Section 2: Pipelines
    print(f"\n  {'─' * 50}")
    print("  PIPELINES")
    print(f"  {'─' * 50}\n")
    try:
        names = list_pipelines()
        if names:
            for n in sorted(names):
                print(f"    • {n}")
        else:
            print("  (none found)")
    except Exception:
        print("  (unavailable — OpenMontage not initialized)")
    print()

    # Section 3: Stages
    print(f"  {'─' * 50}")
    print("  STAGES")
    print(f"  {'─' * 50}\n")
    for i, s in enumerate(STAGE_ORDER, 1):
        label = STAGE_LABELS.get(s, s)
        artifact = STAGE_ARTIFACTS.get(s, "")
        mode = STAGE_MODE.get(s, "")
        mode_tag = f"[{mode}]" if mode else ""
        print(f"    {i}. {label:12s}  {artifact:24s}  {mode_tag}")
    print()


def cmd_init(args):
    """Initialize a new project workspace with artifacts directory."""
    project_name = args.name
    topic = args.topic

    proj_dir = _project_path(project_name)
    if proj_dir.exists():
        print(f"  Project '{project_name}' already exists at {proj_dir}")
        return

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
    print(f"    uv run status {project_name}")
    print(f"    uv run main {project_name}")
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

    pt = _get_pipeline_type(proj_dir)
    completed_raw = get_completed_stages(proj_dir, project_name, pt)
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
        print(f"  Run: uv run stage {project_name} {next_stage}")
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
    section_wavs = []

    # --- Narration (TTS) ---
    print("  Generating narration (TTS)...")

    # Use local Piper TTS (Fish Speech requires API key — skip it)
    tts = None
    try:
        from tools.audio.piper_tts import PiperTTS as _PiperTTS
        tts = _PiperTTS()
        print("    Using Piper TTS")
    except Exception as e:
        print(f"    ⚠ No local TTS available: {e}")
        print("    Install piper-tts: pip install piper-tts")

    if tts:
        for sec in sections:
            sec_id = sec.get("id", "unknown")
            text = sec.get("text", "")
            if not text.strip():
                continue

            output_wav = audio_dir / f"narration_{sec_id}.wav"
            try:
                result = tts.execute({"text": text, "output_path": str(output_wav)})
                if result.success:
                    section_wavs.append(str(output_wav))
                    print(f"    ✅ {sec_id}: generated ({len(text)} chars)")
                else:
                    print(f"    ⚠ {sec_id}: TTS failed — {result.error}")
            except Exception as e:
                print(f"    ⚠ {sec_id}: TTS error — {e}")

    # Concatenate section WAVs into single narration.wav
    narration_wav = audio_dir / "narration.wav"
    narration_ready = False
    if section_wavs:
        try:
            import subprocess
            concat_txt = audio_dir / ".concat_list.txt"
            with open(concat_txt, "w") as f:
                for w in section_wavs:
                    f.write(f"file '{w}'\n")
            subprocess.run(
                ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                 "-i", str(concat_txt), "-c", "copy", str(narration_wav)],
                capture_output=True, text=True, timeout=120
            )
            if narration_wav.exists():
                narration_ready = True
                print(f"    ✅ Concatenated narration: {narration_wav}")
            concat_txt.unlink(missing_ok=True)
        except Exception as e:
            print(f"    ⚠ Narration concatenation failed: {e}")

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


    # --- Image Assets (from assets/images/) ---
    print("\n  Registering image assets...")
    img_dir = _assets_path(proj_dir) / "images"
    image_assets = []
    if img_dir.exists():
        for img_path in sorted(img_dir.iterdir()):
            if img_path.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                # Derive scene_id from filename: scene-1-hook.jpg → scene-1-hook
                scene_id = img_path.stem
                asset_id = f"img_{scene_id}"
                image_assets.append({
                    "id": asset_id,
                    "type": "image",
                    "path": str(img_path.relative_to(HERE)),
                    "source_tool": "placeholder",
                    "scene_id": scene_id,
                    "generation_summary": f"Placeholder image for {scene_id}",
                })
                print(f"    ✅ Image: {img_path.name} -> {asset_id}")
    print(f"  Image assets: {len(image_assets)}")

    # --- Build Asset Manifest ---
    assets = []
    if narration_ready:
        assets.append({
            "id": "a_narration",
            "type": "narration",
            "path": str(narration_wav.relative_to(HERE)),
            "source_tool": "piper_tts",
            "scene_id": "global",
            "generation_summary": "Generated Piper voice narration",
        })
    assets.extend(image_assets)
    if music_success:
        assets.append({
            "id": "a_music",
            "type": "music",
            "path": str(music_path.relative_to(HERE)),
            "source_tool": "pixabay_music",
            "scene_id": "global",
            "generation_summary": "Downloaded background music",
        })

    asset_manifest = {
        "version": "1.0",
        "assets": assets,
    }

    print(f"\n  Manifest: {len(assets)} assets ({len(image_assets)} images, {'1 narration' if narration_ready else '0 narration'}, {'1 music' if music_success else '0 music'})")

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
    assets_list = asset_manifest.get("assets", [])

    # Build asset lookup by id
    asset_by_id = {a["id"]: a for a in assets_list if "id" in a}

    # Find narration, music, and image assets
    narration_asset = next((a for a in assets_list if a.get("type") == "narration"), None)
    music_asset = next((a for a in assets_list if a.get("type") == "music"), None)
    image_assets = [a for a in assets_list if a.get("type") == "image"]

    cuts = []
    current_time = 0.0

    for i, scene in enumerate(scenes):
        scene_id = scene.get("id", f"cut-{i+1}")
        sec_id = scene.get("script_section_id", f"s{i+1}")
        dur = scene.get("end_seconds", 5.0) - scene.get("start_seconds", 0.0)
        if dur <= 0:
            dur = 5.0

        # Find matching image asset by scene_id
        img_asset = None
        for ia in image_assets:
            if scene_id in ia.get("id", "") or scene_id in ia.get("scene_id", ""):
                img_asset = ia
                break

        out_seconds = round(current_time + dur, 2)

        # Determine cut type based on scene position
        if i == 0:
            # First scene: hero title card
            overlay_notes = scene.get("overlay_notes", "")
            cut = {
                "id": f"cut_{scene_id}",
                "type": "hero_title",
                "source": "",
                "in_seconds": round(current_time, 2),
                "out_seconds": out_seconds,
                "text": sec_id.replace("-", " ").title(),
                "heroSubtitle": overlay_notes[:200] if overlay_notes else scene.get("description", "")[:200],
                "backgroundVideo": None,
                "backgroundOverlay": 0.4,
            }
            if img_asset:
                cut["backgroundImage"] = img_asset["path"]
        elif i == len(scenes) - 1:
            # Last scene: callout recap
            cut = {
                "id": f"cut_{scene_id}",
                "type": "callout",
                "source": "",
                "in_seconds": round(current_time, 2),
                "out_seconds": out_seconds,
                "text": scene.get("overlay_notes", scene.get("description", ""))[:300],
                "title": sec_id.replace("-", " ").title(),
                "callout_type": "info",
                "backgroundOverlay": 0.5,
            }
            if img_asset:
                cut["backgroundImage"] = img_asset["path"]
        else:
            # Middle scenes: image with ken-burns animation
            cut = {
                "id": f"cut_{scene_id}",
                "type": "Img",
                "in_seconds": round(current_time, 2),
                "out_seconds": out_seconds,
                "animation": "ken-burns",
            }
            if img_asset:
                cut["source"] = img_asset["id"]
            else:
                cut["source"] = ""

        cuts.append(cut)
        current_time += dur

    # Audio config: use narration.src (single mixed file) + music
    audio_config = {}
    if narration_asset:
        audio_config["narration"] = {
            "src": narration_asset["path"],
            "volume": 1.0,
            "segments": [],
        }
    if music_asset:
        audio_config["music"] = {
            "asset_id": music_asset["id"],
            "volume": 0.3,
            "ducking": {"enabled": True, "reduction_db": 6.0},
        }

    edit_decisions = {
        "version": "1.0",
        "cuts": cuts,
        "audio": audio_config,
        "render_runtime": "remotion",
        "renderer_family": "explainer-data",
        "metadata": {"generated_by": "run.py edit stage"},
    }

    art_dir = _artifact_path(proj_dir)
    with open(art_dir / "edit_decisions.json", "w") as f:
        json.dump(edit_decisions, f, indent=2)

    print(f"  Cuts in timeline: {len(cuts)}")
    print(f"  Total duration: {round(current_time, 2)}s")

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

    cuts = edit_decisions.get("cuts", [])
    audio_config = edit_decisions.get("audio", {})
    music_config = audio_config.get("music", {}) if isinstance(audio_config, dict) else {}
    narration_config = audio_config.get("narration", {}) if isinstance(audio_config, dict) else {}

    total_duration = cuts[-1]["out_seconds"] if cuts else 0

    # --- Audio Mix ---
    print("  Mixing audio...")
    try:
        from tools.audio.audio_mixer import AudioMixer
        mixer = AudioMixer()
        final_mix = audio_dir / "final_mix.wav"

        mix_tracks = []

        # Support both narration.src (single file) and narration.segments (per-section)
        narration_src = narration_config.get("src") if isinstance(narration_config, dict) else None
        if narration_src:
            # Single mixed narration file
            abs_path = str((HERE / narration_src).resolve())
            if os.path.exists(abs_path):
                mix_tracks.append({
                    "path": abs_path,
                    "role": "speech",
                    "volume": narration_config.get("volume", 1.0),
                    "start_seconds": 0,
                })
        else:
            for seg in narration_config.get("segments", []):
                asset_id = seg.get("asset_id")
                if not asset_id:
                    continue
                for a in asset_manifest.get("assets", []):
                    if a.get("id") == asset_id:
                        abs_path = str((HERE / a["path"]).resolve())
                        if os.path.exists(abs_path):
                            mix_tracks.append({
                                "path": abs_path,
                                "role": "speech",
                                "volume": 0.8,
                                "start_seconds": seg.get("start_seconds", 0),
                            })
                        break

        music_asset_id = music_config.get("asset_id") if isinstance(music_config, dict) else None
        if music_asset_id:
            for a in asset_manifest.get("assets", []):
                if a.get("id") == music_asset_id:
                    music_path = str((HERE / a["path"]).resolve())
                    if os.path.exists(music_path):
                        mix_tracks.append({
                            "path": music_path,
                            "role": "music",
                            "volume": music_config.get("volume", 0.3),
                        })
                    break

        mix_config = {
            "operation": "full_mix",
            "output_path": str(final_mix),
            "tracks": mix_tracks,
        }
        ducking = music_config.get("ducking", {}) if isinstance(music_config.get("ducking"), dict) else {"enabled": bool(music_config.get("ducking", True))}
        if any(t["role"] == "speech" for t in mix_tracks):
            mix_config["ducking"] = ducking

        mix_result = mixer.execute(mix_config)
        if mix_result.success:
            print(f"    ✅ Audio mixed: {final_mix}")
            # Update edit_decisions to point to final_mix for rendering
            if "audio" not in edit_decisions or not isinstance(edit_decisions.get("audio"), dict):
                edit_decisions["audio"] = {}
            edit_decisions["audio"]["narration"] = {
                "src": str(final_mix.relative_to(HERE)),
                "volume": 1.0,
                "segments": [],
            }
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
            "operation": "render",
            "edit_decisions": edit_decisions,
            "asset_manifest": asset_manifest,
            "output_path": str(output_path),
        }

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
        "outputs": [
            {
                "path": str(output_path),
                "format": "mp4",
                "codec": "h264",
                "resolution": "1920x1080",
                "fps": 30.0,
                "duration_seconds": round(total_duration, 2),
                "file_size_bytes": file_size,
            }
        ],
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
    from datetime import datetime, timezone
    publish_log = {
        "version": "1.0",
        "entries": [
            {
                "platform": "export",
                "status": "exported",
                "timestamp": datetime.now(timezone.utc).isoformat(),
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
    return projects[0].name if projects else None


def cmd_stage(args):
    """Execute a single pipeline stage."""
    _ensure_om_imports()
    project_name = args.project
    stage_name = args.stage

    proj_dir = _project_path(project_name)
    if not proj_dir.exists():
        print(f"  Project '{project_name}' not found at {proj_dir}")
        print(f"  Run: uv run init {project_name}")
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
        print(f"  Run: uv run init {project_name}")
        return

    print(f"\n  Pipeline run for: {project_name}\n")

    pt = _get_pipeline_type(proj_dir)
    completed_raw = get_completed_stages(proj_dir, project_name, pt)
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
        add_help=False,
    )
    parser.add_argument("name", nargs="?", default=None, help="Project name")
    args = parser.parse_args()

    if args.name is not None:
        cmd_run(argparse.Namespace(project=args.name))
        return

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

    _default_guide()


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
    print("  0. First-time setup (run once)")
    print()
    print("       uv run init")
    print()
    print("     This runs setup, update, and preflight for you.")
    print()
    print("  1. Create a project")
    print()
    print("       uv run init my-video")
    print()
    print("     Creates  projects/my-video/  with subdirectories:")
    print("       artifacts/    — your hand-crafted JSON files (stages 1-3)")
    print("       assets/      — generated images, audio, video")
    print("       renders/     — final video output")
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
          '         ]\n'
          '       }')
    print()
    print("  3. Run the pipeline (resumes where you left off)")
    print()
    print("       uv run main my-video")
    print()
    print("     Stages 4-8 auto-generate: scene plan, assets (TTS, images),")
    print("     edit decisions, video composition, and export.")
    print()
    print("    uv run init                    First-time setup (setup + update + preflight)")
    print("    uv run init <name>             Create a new project")
    print("    uv run list                    List projects, pipelines, stages")
    print("    uv run status <name>           Show stage progress")
    print("    uv run main <name>              Run all remaining stages")
    print("    uv run stage <name> <stage>    Execute one stage")
    print("    uv run main                    Show setup guide")
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




def check_submodule():
    if not OM.exists():
        print("[!] OpenMontage submodule not found. Run: git submodule update --init --recursive")
        sys.exit(1)
    if not OM_AGENT_GUIDE.exists():
        print("[!] OpenMontage is incomplete. Try: git submodule update --init --recursive")
        sys.exit(1)


if __name__ == "__main__":
    main()
