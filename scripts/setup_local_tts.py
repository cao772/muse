"""One-time model/runtime download; synthesis thereafter runs offline without a key."""

import subprocess
from pathlib import Path

from integrations.local_tts import MODEL, REVISION


def main():
    runtime = Path.home() / ".cache/muse-toolchains/tts"
    subprocess.run(["uv", "venv", str(runtime), "--python", "3.12", "--allow-existing"], check=True)
    python = str(runtime / "bin/python")
    subprocess.run(
        ["uv", "pip", "install", "--python", python, "mlx-audio==0.5.8", "soundfile==0.14.0"],
        check=True,
    )
    # Model identifiers are fixed constants; no user text or secrets in this command.
    subprocess.run(
        [
            python,
            "-c",
            "from huggingface_hub import snapshot_download; "
            f"snapshot_download({MODEL!r}, revision={REVISION!r})",
        ],
        check=True,
    )
    print("Ready: uv run muse-tts --provider qwen-local --audition")


if __name__ == "__main__":
    main()
