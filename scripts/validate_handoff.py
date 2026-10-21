"""Validate an extracted B/C profile or its ZIP without executing benchmark tests."""

import argparse
import json
from pathlib import Path
import sys

# Validation must leave the inventoried delivery tree unchanged, even when the
# validator itself runs from inside that freshly extracted tree.
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fl.handoff import validate_archive, validate_b_profile, validate_c_profile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--check-source", action="store_true", help="Reparse C's production source using the pinned Java parser")
    args = parser.parse_args()
    if args.path.is_file():
        manifest = validate_archive(args.path)
        print(json.dumps({"status": "passed", "profile": manifest["profile"], "bugs": manifest["bugs"]}, indent=2))
    else:
        manifest = json.loads((args.path / "manifest.json").read_text())
        validation = (validate_b_profile(args.path) if manifest["profile"] == "B"
                      else validate_c_profile(args.path, args.check_source))
        print(json.dumps(validation, indent=2))


if __name__ == "__main__":
    main()
