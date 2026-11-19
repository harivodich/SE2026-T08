"""Exercise a real noneditable AI wheel outside the checkout, without network."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


PROBE = """
import json, pathlib, sys
sys.path.insert(0, sys.argv[1])
import vietdoc.contracts.compute as compute
module = pathlib.Path(compute.__file__).resolve()
assert module.is_relative_to(pathlib.Path(sys.argv[1]).resolve()), module
contracts = compute.ComputeContracts()
fixtures = pathlib.Path(sys.argv[2])
for schema, name in ((compute.REQUEST_SCHEMA, 'compute-request.json'),
                     (compute.RESPONSE_SCHEMA, 'compute-response.json'),
                     (compute.ERROR_SCHEMA, 'compute-error.json')):
    contracts.validate(schema, json.loads((fixtures / name).read_text(encoding='utf-8')))
print(json.dumps({'installed_module': str(module), 'configured_fixtures_valid': 3}))
"""


def verify_installed(root: Path, directory: Path) -> dict:
    """Build/install locally; prove missing config fails and explicit schemas work."""
    root, directory = root.resolve(), directory.resolve()
    if directory.is_relative_to(root):
        raise ValueError("installed smoke directory must be outside the checkout")
    directory.mkdir(parents=True, exist_ok=True)
    wheels, target = directory / "wheels", directory / "installed"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.pop("VIETDOC_CONTRACTS_DIR", None)
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"

    def run(args):
        result = subprocess.run(args, cwd=directory, env=env, capture_output=True,
                                text=True, timeout=120)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        return result

    run([sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-build-isolation",
         "--no-index", "--wheel-dir", str(wheels), str(root)])
    built = list(wheels.glob("vietdoc-*.whl"))
    if len(built) != 1:
        raise ValueError("expected exactly one AI wheel")
    run([sys.executable, "-m", "pip", "install", "--no-deps", "--no-index",
         "--target", str(target), str(built[0])])
    command = [sys.executable, "-I", "-c", PROBE, str(target), str(root / "tests/contract")]
    missing = subprocess.run(command, cwd=directory, env=env, capture_output=True,
                             text=True, timeout=30)
    if missing.returncode == 0 or "FileNotFoundError: specs/contracts not found" not in missing.stderr:
        raise AssertionError("missing schema configuration did not fail as expected: " + missing.stderr)
    env["VIETDOC_CONTRACTS_DIR"] = str(root / "specs/contracts")
    report = json.loads(run(command).stdout)
    report.update(missing_config_rejected=True,
                  wheel_sha256=hashlib.sha256(built[0].read_bytes()).hexdigest())
    return report
