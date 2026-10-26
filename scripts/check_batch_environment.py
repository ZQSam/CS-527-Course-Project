"""Record the original Docker environment before collecting a frozen cohort."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--results-root", type=Path, required=True)
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[1]
    cohort = json.loads((repository / args.cohort).read_text(encoding="utf-8"))
    root = repository / args.results_root
    output = root / "environment"
    if output.exists():
        parser.error("Environment evidence already exists; preserve it rather than overwrite it")
    image = cohort["environment"]["image"]
    observed = json.loads(subprocess.run(["docker", "image", "inspect", image], check=True,
                                        capture_output=True, text=True).stdout)
    if observed[0]["Id"] != cohort["environment"]["expected_image_id"]:
        raise ValueError("Docker image differs from the preregistered environment")
    catalog = subprocess.run(["docker", "run", "--rm", image, "cat",
                              "/opt/defects4j/framework/projects/Lang/active-bugs.csv"],
                             check=True, capture_output=True).stdout
    if hashlib.sha256(catalog).hexdigest() != cohort["catalog"]["sha256"]:
        raise ValueError("Active bug catalog differs from preregistration")
    output.mkdir(parents=True)
    (output / "image-inspect.json").write_text(json.dumps(observed, indent=2) + "\n", encoding="utf-8")
    (output / "active-bugs.csv").write_bytes(catalog)
    inspected = subprocess.run(["bash", "scripts/run.sh", "python3", "scripts/inspect_environment.py",
                                "--output", output.relative_to(repository).as_posix()],
                               cwd=repository, capture_output=True, text=True, timeout=120)
    (output / "inspection.stdout.log").write_text(inspected.stdout, encoding="utf-8")
    (output / "inspection.stderr.log").write_text(inspected.stderr, encoding="utf-8")
    inspected.check_returncode()
    versions = json.loads((output / "versions.json").read_text(encoding="utf-8"))
    if versions["commands"]["defects4j_commit"]["stdout"].strip() != cohort["catalog"]["defects4j_commit"]:
        raise ValueError("Defects4J revision differs from preregistration")
    (root / "environment-check.json").write_text(json.dumps({"status": "passed", "checks": {
        "image_id": observed[0]["Id"], "active_catalog": "matched", "defects4j_revision": "matched"}}, indent=2) + "\n", encoding="utf-8")
    print("Preregistered image, active catalog and Defects4J revision verified.")


if __name__ == "__main__":
    main()
