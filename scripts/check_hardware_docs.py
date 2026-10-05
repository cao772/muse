"""Check local documentation links and pinned vendor artifacts without hardware."""

import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


def check(artifacts_dir: Path | None = None):
    errors = []
    documents = [ROOT / "README.md"]
    for directory in ("docs", "firmware", "project_context", "integrations"):
        documents.extend((ROOT / directory).rglob("*.md"))
    for document in documents:
        # Current docs use inline links; fenced command examples are not links.
        body = re.sub(r"```.*?```", "", document.read_text(), flags=re.S)
        for target in re.findall(r"\]\(([^\s)]+)\)", body):
            url = urlsplit(target)
            if url.scheme or url.netloc or not url.path:
                continue
            if not (document.parent / unquote(url.path)).exists():
                errors.append(f"{document.relative_to(ROOT)}: broken link {target}")

    manifest = json.loads((ROOT / "firmware/esp32/vendor-artifacts.json").read_text())
    if not re.fullmatch(r"[a-f0-9]{40}", manifest["commit"]):
        errors.append("Vendor commit must be a full SHA")
    repo = "https://github.com/waveshareteam/ESP32-S3-Touch-AMOLED-1.75C"
    if manifest["repository"] != repo:
        errors.append("Unexpected vendor repository")
    if not manifest["artifacts"]:
        errors.append("Empty artifact list")
    names = set()
    for entry in manifest["artifacts"]:
        path = Path(entry["path"])
        prefix = repo.replace("github.com", "raw.githubusercontent.com")
        expected = f"{prefix}/{manifest['commit']}/{entry['path']}"
        if path.is_absolute() or ".." in path.parts or entry["url"] != expected:
            errors.append(f"Unpinned or invalid path: {path}")
        if path.name in names:
            errors.append(f"Duplicate artifact filename: {path.name}")
        names.add(path.name)
        if not re.fullmatch(r"[a-f0-9]{64}", entry["sha256"]) or entry["bytes"] <= 0:
            errors.append(f"Invalid checksum or size: {path}")
        if artifacts_dir is not None:
            local = artifacts_dir / path.name
            if not local.is_file():
                errors.append(f"Missing artifact: {local}")
                continue
            with local.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if local.stat().st_size != entry["bytes"] or digest != entry["sha256"]:
                errors.append(f"Artifact integrity mismatch: {local}")
    if errors:
        raise ValueError("\n".join(errors))
    print(f"PASS: {len(documents)} Markdown files and pinned vendor manifest")
    if artifacts_dir is not None:
        print(f"PASS: {len(names)} downloaded artifacts match size and SHA-256")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts-dir", type=Path)
    try:
        check(parser.parse_args().artifacts_dir)
    except (ValueError, KeyError, TypeError, OSError) as error:
        raise SystemExit(str(error)) from error
