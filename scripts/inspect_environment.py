"""Record an allowlist of tool/version evidence, never the process environment."""

import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
from datetime import datetime, timezone


def main():
    output = Path("results/environment")
    output.mkdir(parents=True, exist_ok=True)
    commands = {
        "java": ["java", "-version"],
        "javac": ["javac", "-version"],
        "python": ["python3", "--version"],
        "git": ["git", "--version"],
        "perl": ["perl", "-e", "print $^V"],
        "defects4j_commit": ["git", "-C", os.environ["D4J_HOME"], "rev-parse", "HEAD"],
        "gzoltar_help": ["java", "-jar", os.environ["GZOLTAR_CLI"], "--help"],
        "gzoltar_version": ["java", "-jar", os.environ["GZOLTAR_CLI"], "version"],
        "java_user_properties": ["java", "-XshowSettings:properties", "-version"],
    }
    evidence = {}
    for name, command in commands.items():
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        evidence[name] = {"command": command, "returncode": result.returncode,
                          "stdout": result.stdout, "stderr": result.stderr}
        if result.returncode:
            raise RuntimeError(f"Version inspection failed: {name}")
    hashes = {}
    for name in ("GZOLTAR_CLI", "GZOLTAR_AGENT"):
        path = Path(os.environ[name])
        hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {"recorded_at_utc": datetime.now(timezone.utc).isoformat(),
                "platform": platform.platform(), "timezone": os.environ["TZ"],
                "defects4j_release": "v2.0.0", "gzoltar_release": "1.7.3",
                "commands": evidence, "artifact_sha256": hashes}
    (output / "versions.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (output / "packages.tsv").write_bytes(Path("/opt/environment/packages.tsv").read_bytes())
    if Path("/opt/python-deps/installed.json").exists():
        (output / "python-container-dependencies.json").write_bytes(Path("/opt/python-deps/installed.json").read_bytes())
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
