"""Install the two pinned parser wheels locally without system pip or sudo.

Only setup uses network access. Download hashes are verified against PyPI.
The parser packages have no mandatory Python dependencies.
"""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import platform
import sys
import urllib.request
import zipfile
from io import BytesIO

PINS = {"tree-sitter": "0.25.2", "tree-sitter-java": "0.23.5"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, default=Path(".deps"))
    args = parser.parse_args()
    if sys.platform != "linux" or platform.machine() != "x86_64":
        parser.error("This setup targets CPython on x86_64 Linux/WSL")
    target = args.target.resolve()
    marker = target / "installed.json"
    interpreter = f"cp{sys.version_info.major}{sys.version_info.minor}"
    if marker.exists():
        previous = json.loads(marker.read_text())
        if previous["pins"] != PINS or previous["interpreter"] != interpreter:
            parser.error("Dependency directory belongs to another version/interpreter; choose a fresh target")
        print(f"Pinned parser dependencies already installed in {target}")
        return
    target.mkdir(parents=True, exist_ok=True)
    artifacts = []
    for package, version in PINS.items():
        with urllib.request.urlopen(f"https://pypi.org/pypi/{package}/{version}/json", timeout=60) as response:
            metadata = json.load(response)
        tag = interpreter + "-" + interpreter if package == "tree-sitter" else "cp39-abi3"
        candidates = [item for item in metadata["urls"]
                      if item["filename"].endswith(".whl") and tag in item["filename"]
                      and "manylinux" in item["filename"] and "x86_64" in item["filename"]]
        if len(candidates) != 1:
            raise RuntimeError(f"Expected one compatible wheel for {package}: {[i['filename'] for i in candidates]}")
        artifact = candidates[0]
        with urllib.request.urlopen(artifact["url"], timeout=60) as response:
            data = response.read()
        digest = hashlib.sha256(data).hexdigest()
        if digest != artifact["digests"]["sha256"]:
            raise RuntimeError(f"Wheel hash mismatch: {package}")
        with zipfile.ZipFile(BytesIO(data)) as archive:
            for name in archive.namelist():
                path = PurePosixPath(name)
                if path.is_absolute() or ".." in path.parts:
                    raise RuntimeError("Invalid wheel path")
            archive.extractall(target)
        artifacts.append({"filename": artifact["filename"], "sha256": digest, "url": artifact["url"]})
        print(f"Installed {package}=={version} in {target}")
    marker.write_text(json.dumps({"pins": PINS, "interpreter": interpreter, "artifacts": artifacts}, indent=2) + "\n")


if __name__ == "__main__":
    main()
