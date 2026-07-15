# montage-is-open

AI-powered video production powered by [OpenMontage](https://github.com/calesthio/OpenMontage).

## Quick Start

```bash
# First time — install everything
uv run m

# Then open this directory in your AI coding assistant and say:
#   "Make a 45-second animated explainer about why the sky is blue"
```

The script auto-updates OpenMontage, installs dependencies, and shows available tools.

## Prerequisites

- Python 3.10+
- FFmpeg — `sudo apt install ffmpeg` / `brew install ffmpeg`
- Node.js 18+
- uv — `curl -LsSf https://astral.sh/uv/install.sh | sh`

## Usage

```bash
# Re-run setup / update / check tools
uv run m

# Or manually:
git submodule update --remote OpenMontage    # get latest
uv pip install -r OpenMontage/requirements.txt
```

Then tell your AI assistant what video you want. The agent drives the full pipeline through OpenMontage: research → script → scene_plan → assets → edit → compose.

Output lands in `projects/` (gitignored).

## API Keys (Optional)

Copy `.env` and add keys for the providers you want:

```bash
# More keys = more capabilities (all optional)
FAL_KEY=           # FLUX images + Kling, Veo, MiniMax video
OPENAI_API_KEY=    # DALL-E 3 images + TTS
ELEVENLABS_API_KEY= # Premium TTS + music
GOOGLE_API_KEY=    # Imagen images + TTS
PEXELS_API_KEY=    # Free stock footage/images
```

## Resources

- [OpenMontage Agent Guide](OpenMontage/AGENT_GUIDE.md) — full operating guide
- [OpenMontage README](OpenMontage/README.md) — overview, prompt gallery, pipelines
- [OpenMontage Providers](OpenMontage/docs/PROVIDERS.md) — pricing & free tiers
