import sys
import json
import subprocess
from pathlib import Path

# Add OpenMontage to sys.path first if not already present
HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE / "OpenMontage"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Now import modules from OpenMontage
from tools.base_tool import ToolResult
from tools.video.video_compose import VideoCompose
import schemas.artifacts

# 1. Patch load_schema to allow additional properties in edit_decisions
original_load_schema = schemas.artifacts.load_schema

def patched_load_schema(name: str) -> dict:
    schema = original_load_schema(name)
    if name == "edit_decisions":
        if "properties" in schema and "cuts" in schema["properties"]:
            cuts_schema = schema["properties"]["cuts"]
            if "items" in cuts_schema:
                cuts_schema["items"]["additionalProperties"] = True
    return schema

schemas.artifacts.load_schema = patched_load_schema
print("[OM Patch] In-memory edit_decisions schema patched to allow additional properties.")


# 2. Patch VideoCompose._remotion_render to handle 'projects/' paths and catch CalledProcessError
def patched_remotion_render(self, inputs: dict) -> ToolResult:
    import shutil
    if not shutil.which("npx"):
        return ToolResult(
            success=False,
            error="npx not found. Install Node.js to use Remotion rendering.",
        )

    composition_data = inputs.get("edit_decisions") or inputs.get("composition_data")
    if not composition_data:
        return ToolResult(
            success=False,
            error="edit_decisions or composition_data required for remotion_render",
        )

    output_path = Path(inputs.get("output_path", "renders/remotion_output.mp4"))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path = output_path.resolve()

    props = json.loads(json.dumps(composition_data))

    for cut in props.get("cuts", []):
        source = cut.get("source", "")
        if source and not source.startswith(("http://", "https://", "file://")):
            if source.startswith("projects/"):
                continue
            resolved = Path(source).resolve()
            if resolved.exists():
                posix = resolved.as_posix()
                cut["source"] = f"file:///{posix}" if not posix.startswith("/") else f"file://{posix}"

    if "themeConfig" not in props:
        playbook_name = (
            props.get("playbook")
            or props.get("theme")
            or props.get("metadata", {}).get("playbook")
        )
        theme_config = self._build_theme_from_playbook(playbook_name, composition_data)
        if theme_config:
            props["themeConfig"] = theme_config

    props_path = output_path.parent / ".remotion_props.json"
    with open(props_path, "w", encoding="utf-8") as f:
        json.dump(props, f)

    composer_dir = PROJECT_ROOT / "remotion-composer"
    if not composer_dir.exists():
        return ToolResult(
            success=False,
            error=f"Remotion composer project not found at {composer_dir}",
        )

    renderer_family = (composition_data or {}).get("renderer_family", "explainer-data")
    composition_id = self._get_composition_id(renderer_family)

    cmd = [
        "npx", "remotion", "render",
        str(composer_dir / "src" / "index.tsx"),
        composition_id,
        str(output_path),
        "--props", str(props_path),
    ]

    profile_name = inputs.get("profile")
    if profile_name:
        try:
            from lib.media_profiles import get_profile
            p = get_profile(profile_name)
            cmd.extend(["--width", str(p.width), "--height", str(p.height)])
        except (ImportError, ValueError):
            pass

    try:
        self.run_command(cmd, timeout=1800, cwd=composer_dir)
    except subprocess.CalledProcessError as e:
        error_msg = f"Remotion render failed: {e}\nStdout: {e.stdout}\nStderr: {e.stderr}"
        return ToolResult(success=False, error=error_msg)
    except Exception as e:
        return ToolResult(success=False, error=f"Remotion render failed: {e}")

    return ToolResult(success=True, data={"output_path": str(output_path)})

VideoCompose._remotion_render = patched_remotion_render
print("[OM Patch] VideoCompose._remotion_render patched to handle projects/ path routing.")

# 3. Register custom FishSpeechTTS tool
try:
    from tools.tool_registry import registry
    from custom_tools.fish_speech_tts import FishSpeechTTS
    registry.register(FishSpeechTTS())
    print("[OM Patch] Custom FishSpeechTTS registered successfully in ToolRegistry.")
except Exception as e:
    print(f"[OM Patch] Failed to register custom FishSpeechTTS: {e}")
