import sys
import json
import subprocess
import shutil
import os
from pathlib import Path

# Browser Path Overrides for Playwright/Mule browser
os.environ["PRODUCER_HEADLESS_SHELL_PATH"] = "/home/pannet1/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome"
os.environ["PUPPETEER_EXECUTABLE_PATH"] = "/home/pannet1/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome"


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

# 1.5. Patch load_playbook to load custom playbooks from the parent styles folder
import styles.playbook_loader
original_load_playbook = styles.playbook_loader.load_playbook

def patched_load_playbook(name: str, styles_dir=None) -> dict:
    parent_styles_dir = Path(__file__).resolve().parent / "styles"
    path = parent_styles_dir / f"{name}.yaml"
    if path.exists():
        return original_load_playbook(name, styles_dir=parent_styles_dir)
    return original_load_playbook(name, styles_dir=styles_dir)

styles.playbook_loader.load_playbook = patched_load_playbook
print("[OM Patch] In-memory load_playbook patched to search parent styles directory first.")

# 2. Patch VideoCompose._remotion_available to support bunx
original_remotion_available = VideoCompose._remotion_available

def patched_remotion_available(self) -> bool:
    npx_bin = shutil.which("npx")
    bunx_bin = "/home/pannet1/.bun/bin/bunx" if Path("/home/pannet1/.bun/bin/bunx").exists() else shutil.which("bunx")
    
    if not (npx_bin or bunx_bin):
        return False
        
    composer_dir = PROJECT_ROOT / "remotion-composer"
    if not composer_dir.exists() or not (composer_dir / "package.json").exists():
        return False
    if not (composer_dir / "node_modules").exists():
        return False
    return True

VideoCompose._remotion_available = patched_remotion_available
print("[OM Patch] VideoCompose._remotion_available patched to support bunx.")

# 3. Patch VideoCompose._remotion_render to handle 'projects/' paths and use bunx if npx is missing
def patched_remotion_render(self, inputs: dict) -> ToolResult:
    npx_bin = shutil.which("npx")
    bunx_bin = "/home/pannet1/.bun/bin/bunx" if Path("/home/pannet1/.bun/bin/bunx").exists() else shutil.which("bunx")
    runner = npx_bin or bunx_bin
    
    if not runner:
        return ToolResult(
            success=False,
            error="npx or bunx not found. Install Node.js or Bun to use Remotion rendering.",
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
        for field in ("source", "backgroundImage"):
            value = cut.get(field, "")
            if value and not value.startswith(("http://", "https://", "file://")):
                if value.startswith("projects/"):
                    continue
                resolved = Path(value).resolve()
                if resolved.exists():
                    posix = resolved.as_posix()
                    cut[field] = f"file:///{posix}" if not posix.startswith("/") else f"file://{posix}"

    if "themeConfig" not in props:
        playbook_name = (
            props.get("playbook")
            or props.get("theme")
            or props.get("metadata", {}).get("playbook")
        )
        theme_config = self._build_theme_from_playbook(playbook_name, composition_data)
        if theme_config:
            if playbook_name == "custom-ecomsense":
                theme_config["surfaceColor"] = "#0f172a"
                theme_config["mutedTextColor"] = "#94a3b8"
                theme_config["headingFont"] = "Inter, system-ui, sans-serif"
                theme_config["bodyFont"] = "Inter, system-ui, sans-serif"
                theme_config["captionHighlightColor"] = "#34d399"
                theme_config["captionBackgroundColor"] = "rgba(2, 6, 23, 0.85)"
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
        runner, "remotion", "render",
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
print("[OM Patch] VideoCompose._remotion_render patched to handle projects/ path routing and support Bun/bunx.")

# 4. Patch HyperFramesCompose to support global Bun-installed hyperframes execution
try:
    from tools.video.hyperframes_compose import HyperFramesCompose
    
    HyperFramesCompose._NODE_FLOOR_MAJOR = 20
    original_runtime_check = HyperFramesCompose._runtime_check
    original_run_hf = HyperFramesCompose._run_hf
    
    def patched_runtime_check(self) -> dict:
        check = original_runtime_check(self)
        bun_hf = Path("/home/pannet1/.bun/bin/hyperframes")
        if bun_hf.exists():
            check["runtime_available"] = check["ffmpeg_available"]
            check["npx_available"] = True
            check["reasons"] = [r for r in check["reasons"] if "ffmpeg" in r]
        return check
        
    def patched_run_hf(self, args, *, cwd, timeout, check):
        bun_hf = Path("/home/pannet1/.bun/bin/hyperframes")
        if bun_hf.exists():
            cmd = [str(bun_hf), *args]
            try:
                return subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=str(cwd) if cwd else None,
                    check=False,
                )
            except Exception:
                pass
        return original_run_hf(self, args, cwd=cwd, timeout=timeout, check=check)
        
    HyperFramesCompose._runtime_check = patched_runtime_check
    HyperFramesCompose._run_hf = patched_run_hf
    print("[OM Patch] HyperFramesCompose runtime check and CLI run patched for Bun-installed hyperframes.")
except Exception as e:
    print(f"[OM Patch] Failed to patch HyperFramesCompose: {e}")

# 5. Register custom FishSpeechTTS tool
try:
    from tools.tool_registry import registry
    from custom_tools.fish_speech_tts import FishSpeechTTS
    registry.register(FishSpeechTTS())
    print("[OM Patch] Custom FishSpeechTTS registered successfully in ToolRegistry.")
except Exception as e:
    print(f"[OM Patch] Failed to register custom FishSpeechTTS: {e}")

# 6. Patch LocalDiffusion to use local SDXL .safetensors model automatically
#    No config needed — drops in place of external API image providers.
try:
    import os as _os
    from pathlib import Path as _Path
    from tools.base_tool import ToolResult, ToolStatus
    from tools.graphics.local_diffusion import LocalDiffusion

    # Default local SDXL model path — override via SDXL_MODEL_PATH env var
    _SDXL_DEFAULT = _os.environ.get(
        "SDXL_MODEL_PATH",
        _os.path.expanduser("~/Downloads/DreamShaperXL_Lightning.safetensors"),
    )
    _SDXL_PATH = _Path(_SDXL_DEFAULT)

    # Patch get_status — AVAILABLE when model file exists + diffusers installed
    _orig_status = LocalDiffusion.get_status

    def _patched_status(self) -> ToolStatus:
        if not _SDXL_PATH.exists():
            return _orig_status(self)
        try:
            import diffusers  # noqa: F401
            import torch  # noqa: F401
            return ToolStatus.AVAILABLE
        except ImportError:
            return ToolStatus.UNAVAILABLE

    LocalDiffusion.get_status = _patched_status

    # Patch input_schema default model to local SDXL path
    LocalDiffusion.input_schema["properties"]["model"]["default"] = str(_SDXL_PATH)

    # Patch execute — use SDXL from single file when model is a .safetensors path
    _orig_exec = LocalDiffusion.execute

    def _patched_exec(self, inputs: dict) -> ToolResult:
        model_id = inputs.get("model", str(_SDXL_PATH))
        prompt = inputs["prompt"]
        negative = inputs.get("negative_prompt", "")
        width = inputs.get("width", 1024)
        height = inputs.get("height", 1024)
        seed = inputs.get("seed")
        steps = inputs.get("num_inference_steps", 8)
        guidance = inputs.get("guidance_scale", 5.0)

        if model_id.endswith(".safetensors"):
            import time
            import torch
            from diffusers import StableDiffusionXLPipeline, DPMSolverMultistepScheduler

            model_path = _Path(model_id)
            if not model_path.exists():
                return ToolResult(
                    success=False,
                    error=f"Model file not found: {model_id}",
                )
            try:
                start = time.time()
                pipe = StableDiffusionXLPipeline.from_single_file(
                    str(model_path),
                    torch_dtype=torch.float16,
                    use_safetensors=True,
                )
                pipe.scheduler = DPMSolverMultistepScheduler.from_config(pipe.scheduler.config)
                pipe.set_progress_bar_config(disable=True)
                pipe.enable_model_cpu_offload()

                generator = None
                if seed is not None:
                    generator = torch.Generator(device="cuda").manual_seed(seed)

                image = pipe(
                    prompt,
                    negative_prompt=negative,
                    width=width,
                    height=height,
                    num_inference_steps=steps,
                    guidance_scale=guidance,
                    generator=generator,
                ).images[0]

                output_path = _Path(inputs.get("output_path", "generated_image.png"))
                output_path.parent.mkdir(parents=True, exist_ok=True)
                image.save(str(output_path))

                return ToolResult(
                    success=True,
                    data={
                        "provider": "local_diffusion",
                        "model": model_id,
                        "prompt": prompt,
                        "output": str(output_path),
                    },
                    artifacts=[str(output_path)],
                    cost_usd=0.0,
                    duration_seconds=round(time.time() - start, 2),
                    seed=seed,
                    model=model_id,
                )
            except Exception as e:
                return ToolResult(success=False, error=f"SDXL local generation failed: {e}")

        # Fall through to original for hub models
        return _orig_exec(self, inputs)

    LocalDiffusion.execute = _patched_exec
    print("[OM Patch] LocalDiffusion patched — auto-uses local SDXL .safetensors model.")
except Exception as e:
    print(f"[OM Patch] Failed to patch LocalDiffusion: {e}")
