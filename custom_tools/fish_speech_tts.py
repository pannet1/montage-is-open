from __future__ import annotations

import os
import time
import urllib.request
import urllib.error
import json
from pathlib import Path
from typing import Any

from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    RetryPolicy,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)

class FishSpeechTTS(BaseTool):
    name = "fish_speech_tts"
    version = "0.1.0"
    tier = ToolTier.VOICE
    capability = "tts"
    provider = "fish_speech"
    stability = ToolStability.EXPERIMENTAL
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.HYBRID

    dependencies = []
    install_instructions = (
        "To use Fish Speech (Cloud API):\n"
        "  Set FISH_API_KEY in your .env file.\n"
        "To use Fish Speech (Local/Offline server):\n"
        "  Start a local server and set FISH_API_BASE to your server endpoint (e.g., http://localhost:8000/v1).\n"
        "  No API key is required for local runs."
    )
    fallback = "piper_tts"
    fallback_tools = ["piper_tts"]
    agent_skills = ["text-to-speech"]

    capabilities = [
        "text_to_speech",
        "voice_selection",
        "voice_cloning",
    ]
    supports = {
        "voice_cloning": True,
        "multilingual": True,
        "offline": True,
        "native_audio": True,
    }
    best_for = [
        "high-quality expressive TTS generation",
        "zero-shot voice cloning",
        "local and cloud deployment options",
    ]
    not_good_for = [
        "extremely low-resource systems without internet or local server set up",
    ]

    input_schema = {
        "type": "object",
        "required": ["text"],
        "properties": {
            "text": {"type": "string"},
            "voice": {
                "type": "string",
                "default": "default",
                "description": "Voice/Reference model ID (for Cloud API, e.g., standard voice ID; for local, the model/speaker tag).",
            },
            "format": {
                "type": "string",
                "default": "wav",
                "enum": ["mp3", "wav", "opus"],
            },
            "output_path": {"type": "string"},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=256, vram_mb=0, disk_mb=50, network_required=True
    )
    retry_policy = RetryPolicy(max_retries=2, retryable_errors=["rate_limit", "timeout"])
    idempotency_key_fields = ["text", "voice", "format"]
    side_effects = ["writes audio file to output_path", "calls Fish Speech API"]
    user_visible_verification = ["Listen to generated audio for quality and inflection"]

    def get_status(self) -> ToolStatus:
        if os.environ.get("FISH_API_KEY") or os.environ.get("FISH_API_BASE"):
            return ToolStatus.AVAILABLE
        return ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        # Free for local, minimal cost for API
        if os.environ.get("FISH_API_KEY") and not os.environ.get("FISH_API_BASE"):
            return round(len(inputs.get("text", "")) * 0.0001, 4)
        return 0.0

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        if self.get_status() != ToolStatus.AVAILABLE:
            return ToolResult(success=False, error="Fish Speech is not configured. " + self.install_instructions)

        start = time.time()
        try:
            result = self._generate(inputs)
        except Exception as exc:
            return ToolResult(success=False, error=f"Fish Speech TTS generation failed: {exc}")

        result.duration_seconds = round(time.time() - start, 2)
        result.cost_usd = self.estimate_cost(inputs)
        return result

    def _generate(self, inputs: dict[str, Any]) -> ToolResult:
        from tools.analysis.audio_probe import probe_duration

        text = inputs["text"]
        voice = inputs.get("voice", "default")
        fmt = inputs.get("format", "wav")
        output_path = Path(inputs.get("output_path", f"fish_speech_tts.{fmt}"))
        output_path.parent.mkdir(parents=True, exist_ok=True)

        api_key = os.environ.get("FISH_API_KEY")
        api_base = os.environ.get("FISH_API_BASE", "https://api.fish.audio/v1")
        if api_base.endswith("/"):
            api_base = api_base[:-1]

        url = f"{api_base}/tts"
        headers = {
            "Content-Type": "application/json",
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        # Fish Speech API request body format:
        body = {
            "text": text,
            "format": fmt,
        }
        if voice != "default":
            body["reference_id"] = voice
            body["voice"] = voice

        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                content = response.read()
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"API Error (HTTP {e.code}): {error_body}")
        except Exception as e:
            raise RuntimeError(f"Connection failed: {e}")

        with open(output_path, "wb") as f:
            f.write(content)

        audio_duration = probe_duration(output_path)

        return ToolResult(
            success=True,
            data={
                "provider": self.provider,
                "voice": voice,
                "format": fmt,
                "text_length": len(text),
                "audio_duration_seconds": round(audio_duration, 2) if audio_duration else None,
                "output": str(output_path),
            },
            artifacts=[str(output_path)],
            model="fish-speech-v1",
        )
