"""Real pytest subprocess probes: a green AI runner must mean tests executed."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import pytest

from scripts.ci.gate import CORE_CHECKS, evaluate

ROOT = Path(__file__).resolve().parents[2]
PROBE = """
from pathlib import Path
import sys
from scripts.ci.ai import run_tests
sys.exit(run_tests([Path(sys.argv[1])], minimum_tests=int(sys.argv[2])))
"""


def run_probe(path, pytest_addopts=None, minimum_tests=1):
    env = dict(os.environ)
    env.pop("PYTEST_ADDOPTS", None)
    env.pop("GITHUB_STEP_SUMMARY", None)  # Expected failing probes are not the CI job result.
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    if pytest_addopts is not None:
        env["PYTEST_ADDOPTS"] = pytest_addopts
    return subprocess.run([sys.executable, "-c", PROBE, str(path), str(minimum_tests)], cwd=ROOT,
                          env=env, capture_output=True, text=True, timeout=30)


@pytest.mark.parametrize(("source", "success"), [
    ("def test_pass(): assert 1 + 1 == 2\n", True),
    ("def test_failure(): assert 1 + 1 == 3\n", False),
    ("import pytest\ndef test_skip(): pytest.skip('unexpected')\n", False),
    ("import pytest\n@pytest.mark.xfail\ndef test_xfail(): assert False\n", False),
    ("import pytest\npytest.skip('module skip', allow_module_level=True)\n", False),
    ("# No tests here\n", False),
    (None, False),
])
def test_ai_runner_propagates_real_pytest_result_to_gate(tmp_path, source, success):
    path = tmp_path / "test_probe.py"
    if source is not None:
        path.write_text(source, encoding="utf-8")
    result = run_probe(path)
    assert (result.returncode == 0) is success, result.stdout + result.stderr
    needs = {name: {"result": "success"} for name in CORE_CHECKS}
    needs["release-readiness"] = {"result": "skipped"}
    needs["ai"] = {"result": "success" if result.returncode == 0 else "failure"}
    assert (evaluate("ci", "develop", needs) == []) is success


def test_ai_runner_rejects_empty_module_even_when_other_tests_pass(tmp_path):
    (tmp_path / "test_good.py").write_text("def test_good(): assert True\n", encoding="utf-8")
    (tmp_path / "test_empty.py").write_text("# accidentally removed tests\n", encoding="utf-8")
    result = run_probe(tmp_path)
    assert result.returncode != 0
    assert "test_empty.py" in result.stdout + result.stderr


def test_ai_runner_rejects_inventory_below_floor(tmp_path):
    path = tmp_path / "test_one.py"
    path.write_text("def test_one(): assert True\n", encoding="utf-8")
    result = run_probe(path, minimum_tests=2)
    assert result.returncode != 0
    assert "Test inventory shrank: 1 < 2" in result.stdout + result.stderr


def test_ai_runner_reports_subtests_separately(tmp_path):
    path = tmp_path / "test_probe.py"
    path.write_text("""
import unittest
class Probe(unittest.TestCase):
    def test_subtests(self):
        for number in (1, 2):
            with self.subTest(number=number):
                self.assertGreater(number, 0)
""", encoding="utf-8")
    result = run_probe(path)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout[result.stdout.rfind("\n{") + 1:])
    assert report["collected"] == 1
    assert report["passed"] == 1
    assert report["passed_subtests"] == 2


@pytest.mark.parametrize("options", ["--collect-only", "-k nonexistent_probe"])
def test_ai_runner_requires_execution_without_deselection(tmp_path, options):
    path = tmp_path / "test_probe.py"
    path.write_text("def test_good(): assert True\n", encoding="utf-8")
    result = run_probe(path, pytest_addopts=options)
    assert result.returncode != 0, result.stdout + result.stderr


@pytest.mark.parametrize("missing", [
    "tests/unit/pipeline/test_baseline.py",
    "tests/unit/pipeline/test_baseline_export.py",
    "tests/unit/pipeline/test_preprocess.py",
    "tests/unit/pipeline/test_geometry.py",
    "tests/unit/pipeline/test_evidence.py",
    "tests/unit/pipeline/test_paddle_adapter.py",
    "tests/unit/pipeline/test_ocr_handoff.py",
    "tests/unit/pipeline/test_ocr_preview.py",
    "tests/contract/test_ocr_contracts.py",
])
def test_main_rejects_deleted_mandatory_file_before_running_tests(tmp_path, monkeypatch, capsys, missing):
    from scripts.ci import ai
    for name in ai.REQUIRED_FILES:
        path = tmp_path / name
        if name != missing:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("def test_exists(): pass\n", encoding="utf-8")
    monkeypatch.setattr(ai, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["ai.py"])
    monkeypatch.setattr(ai, "run_tests", lambda *a, **k: pytest.fail("mandatory file was not checked"))
    assert ai.main() == 1
    assert f"Missing mandatory test file: {missing}" in capsys.readouterr().err


def test_installed_compute_contracts_outside_checkout(tmp_path):
    from scripts.ci.ai_installed import verify_installed
    def independent(path):
        path = path.resolve()
        return not path.is_relative_to(ROOT.resolve()) and not any(
            (ancestor / "specs/contracts").is_dir() for ancestor in (path, *path.parents)
        )

    if independent(tmp_path):
        result = verify_installed(ROOT, tmp_path)
    else:
        temp_parent = (Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "Temp"
                       if os.name == "nt" else Path("/tmp"))
        assert independent(temp_parent), "no independent wheel test directory available"
        with tempfile.TemporaryDirectory(prefix="vietdoc-ai-wheel-", dir=temp_parent) as fresh:
            result = verify_installed(ROOT, Path(fresh))
    assert result["missing_config_rejected"] is True
    assert result["configured_fixtures_valid"] == 3
    assert not Path(result["installed_module"]).is_relative_to(ROOT)
