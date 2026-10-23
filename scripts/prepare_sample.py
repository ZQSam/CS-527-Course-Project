"""Validate the published B inputs or prepare the compressed C dataset."""

import argparse
import json
from pathlib import Path
import sys
import tempfile
import zipfile

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fl.handoff import (digest, repo_path, require, validate_archive,
                        validate_b_profile, validate_c_profile, validate_profile)


def prepare(repository: Path, profile: str, check_source: bool = False,
            release_path: str = "data/sample/release.json") -> dict:
    release = json.loads(repo_path(repository, release_path).read_text(encoding="utf-8"))
    if profile == "B":
        root = repo_path(repository, release["B"]["directory"])
        require(digest((root / "manifest.json").read_bytes()) == release["B"]["manifest_sha256"],
                "B manifest does not match the published release")
        result = validate_b_profile(root)
    else:
        archive_path = repo_path(repository, release["C"]["archive"])
        require(digest(archive_path.read_bytes()) == release["C"]["sha256"],
                "C archive does not match the published release")
        manifest = validate_archive(archive_path)
        root = repo_path(repository, release["C"].get("directory", ".work/sample/C"))
        require(root.is_relative_to((repository / ".work").resolve()), "C extraction must stay in .work/")
        if root.exists():
            require(validate_profile(root) == manifest,
                    "Existing C dataset differs from this release; preserve it and move it before preparing a new release")
            result = validate_c_profile(root, check_source=check_source)
        else:
            root.parent.mkdir(parents=True, exist_ok=True)
            # Validate in a new sibling directory before publishing the target.
            with tempfile.TemporaryDirectory(prefix="prepare-c-", dir=root.parent) as temporary:
                staging = Path(temporary) / "C"
                staging.mkdir()
                with zipfile.ZipFile(archive_path) as archive:
                    for name in archive.namelist():
                        destination = repo_path(staging, name)
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        destination.write_bytes(archive.read(name))
                result = validate_c_profile(staging, check_source=check_source)
                staging.rename(root)
    require(release["bugs"] == [entry if isinstance(entry, str) else entry["bug_id"] for entry in result["bugs"]],
            "Prepared cohort does not match the release")
    return {**result, "directory": root.relative_to(repository).as_posix(),
            "release_id": release["release_id"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("B", "C"), required=True)
    parser.add_argument("--release", default="data/sample/release.json",
                        help="Repository-relative release manifest; defaults to the original pilot")
    parser.add_argument("--check-source", action="store_true",
                        help="Reparse C source using pinned Java parser dependencies")
    args = parser.parse_args()
    if args.check_source and args.profile != "C":
        parser.error("--check-source applies to C")
    repository = Path(__file__).resolve().parents[1]
    print(json.dumps(prepare(repository, args.profile, args.check_source, args.release), indent=2))


if __name__ == "__main__":
    main()
