# Person A shared Java parser

`person_a_java.py` is the original `fl/java.py` from the team's repository at commit `99e7b385023f5d601f8cca01125c52ca02cba674`, retained to reproduce canonical method IDs, source ranges and hashes. Source URL and SHA-256 are recorded in `real/evidence/SOURCES.json`.

Dependencies: tree-sitter 0.25.2, tree-sitter-java 0.23.5. This module is imported only for `import_person_a.py --reparse`; scoring and ordinary data import use the Python standard library. Original Apache Commons Lang source snapshots retained under `real/data/buggy_sources/` preserve their source license headers.
