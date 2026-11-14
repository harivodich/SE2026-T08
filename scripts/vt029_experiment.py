"""Run the required exception-swallow mutation in an isolated temporary backend.

No checkout/stage/commit or source-tree mutation. Requires cached Maven dependencies.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--maven-repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    source = root / "backend/src/main/java/vn/vietdoc/document/DocumentController.java"
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    needle = "    return documents.list(user.id(), type, status, cursor, limit, q);"
    replacement = """    try {
      return documents.list(user.id(), type, status, cursor, limit, q);
    } catch (RuntimeException ignored) {
      return new DocumentService.Page<>(List.of(), null);
    }"""
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="vt029-mutant-") as directory:
        copy = Path(directory) / "backend"
        shutil.copytree(root / "backend", copy, ignore=shutil.ignore_patterns("target", "runtime"))
        mutant = copy / source.relative_to(root / "backend")
        original = mutant.read_text()
        if original.count(needle) != 1:
            raise RuntimeError("Mutation target changed; review the experiment before running")
        mutant.write_text(original.replace(needle, replacement))
        command = ["bash", str(copy / "mvnw"), "-o", "-B", "-ntp",
                   f"-Dmaven.repo.local={args.maven_repo.resolve()}",
                   "-Dtest=DocumentSearchContractTest#tc12_providerFailureIsNotSuccessfulEmptyPage", "test"]
        with (args.output / "mutation.txt").open("w") as log:
            result = subprocess.run(command, cwd=copy, stdout=log, stderr=subprocess.STDOUT,
                                    timeout=180, env=os.environ.copy(), check=False)
        report = copy / "target/surefire-reports/TEST-vn.vietdoc.DocumentSearchContractTest.xml"
        tree = ET.parse(report)
        cases = tree.findall(".//testcase")
        failures = tree.findall(".//failure")
        killed = (result.returncode != 0 and len(cases) == 1 and len(failures) == 1
                  and "Status expected:<500> but was:<200>" in failures[0].attrib.get("message", ""))
        (args.output / "mutation-result.json").write_text(json.dumps({
            "mutation": "swallow RuntimeException and return Page(empty, null)",
            "isolation": "temporary backend copy, no commit or branch mutation",
            "exit_code": result.returncode, "test_count": len(cases), "killed": killed,
            "failure": failures[0].attrib.get("message") if failures else None,
            "controller_sha256_before": before,
            "controller_sha256_after": hashlib.sha256(source.read_bytes()).hexdigest(),
        }, indent=2) + "\n")
        assert killed, "Mutation was not killed for the expected reason; inspect mutation.txt"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    print("Mutation KILLED by TC12: expected HTTP 500, mutant returned HTTP 200; source unchanged")


if __name__ == "__main__":
    main()
