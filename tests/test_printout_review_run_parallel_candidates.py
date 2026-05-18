import argparse
import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

MODULE_PATH = (
    REPO_ROOT
    / "notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/scripts/run_parallel_candidates.py"
)
SPEC = importlib.util.spec_from_file_location("printout_review_run_parallel_candidates", MODULE_PATH)
assert SPEC and SPEC.loader
run_parallel = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(run_parallel)


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _master_manifest(tmp_path: Path) -> Path:
    run_dir = tmp_path / "printout_review" / "runs" / "parallel-test"
    prompt_path = tmp_path / "prompt.md"
    prompt_path.write_text("variant prompt", encoding="utf-8")
    manifest_path = run_dir / "manifest.json"
    _write_json(
        manifest_path,
        {
            "schema_version": 1,
            "run_name": "parallel-test",
            "variant_prompt_path": str(prompt_path),
            "candidate_output_root": str(tmp_path / "printout_review" / "review"),
            "canonical_output_root": str(tmp_path / "output"),
            "entries": [
                {
                    "source_id": "source-a",
                    "lecture_key": "W01L1",
                    "title": "Source A",
                    "candidate": {"status": "pending"},
                },
                {
                    "source_id": "source-b",
                    "lecture_key": "W01L1",
                    "title": "Source B",
                    "candidate": {"status": "pending"},
                },
            ],
        },
    )
    return manifest_path


def _args(manifest_path: Path, **overrides):
    values = {
        "manifest": str(manifest_path),
        "workers": 2,
        "source_id": [],
        "provider": "gemini",
        "model": "gemini-3.1-pro-preview",
        "force": True,
        "rerender_existing": False,
        "no_pdf": False,
        "include_exam_bridge": False,
        "skip_preflight": True,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _mark_source_complete(state: dict, source_id: str) -> None:
    candidate_output_root = Path(state["candidate_output_root"])
    json_path = run_parallel.printout_engine.artifact_json_path_for_source_id(
        candidate_output_root,
        source_id=source_id,
        provider=state["provider"],
        model=state["model"],
    )
    _write_json(json_path, {"ok": True})
    artifact = {
        "generator": {"provider": state["provider"], "model": state["model"]},
        "source": {"source_id": source_id},
    }
    for stem in run_parallel._expected_stems(include_exam_bridge=False):
        pdf_path = candidate_output_root / run_parallel.printout_engine._review_pdf_filename(artifact, stem)
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(b"%PDF-1.4 fake")

    source_manifest_path = Path(state["entries"][source_id]["manifest_path"])
    manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    manifest["entries"][0]["candidate"]["status"] = "written"
    _write_json(source_manifest_path, manifest)


def test_parallel_state_initializes_per_source_manifests_and_verifies_from_disk(tmp_path):
    manifest_path = _master_manifest(tmp_path)

    state = run_parallel._initialize_state(_args(manifest_path), overwrite=True)

    assert state["status"] == "planned"
    assert sorted(state["source_ids"]) == ["source-a", "source-b"]
    for source_id in state["source_ids"]:
        source_manifest = Path(state["entries"][source_id]["manifest_path"])
        assert source_manifest.exists()
        payload = json.loads(source_manifest.read_text(encoding="utf-8"))
        assert [entry["source_id"] for entry in payload["entries"]] == [source_id]

    _mark_source_complete(state, "source-a")
    verification = run_parallel._verify_state(state)

    assert verification["status"] == "incomplete"
    assert verification["source_count"] == 2
    assert verification["complete_source_count"] == 1
    assert verification["expected_pdf_count"] == 10
    assert verification["present_pdf_count"] == 5
    by_source = {item["source_id"]: item for item in verification["sources"]}
    assert by_source["source-a"]["status"] == "complete"
    assert by_source["source-b"]["status"] == "incomplete"


def test_parallel_resume_preserves_provider_when_not_overridden(tmp_path):
    manifest_path = _master_manifest(tmp_path)
    state = run_parallel._initialize_state(
        _args(manifest_path, provider="openai", model="gpt-5.5"),
        overwrite=True,
    )
    assert state["provider"] == "openai"

    resumed = run_parallel._load_or_initialize_state(
        _args(manifest_path, provider=None, model=None, workers=4),
    )

    assert resumed["provider"] == "openai"
    assert resumed["model"] == "gpt-5.5"
    assert resumed["workers"] == 4


def test_parallel_resume_rejects_semantic_option_changes(tmp_path):
    manifest_path = _master_manifest(tmp_path)
    run_parallel._initialize_state(_args(manifest_path, force=True), overwrite=True)

    try:
        run_parallel._load_or_initialize_state(_args(manifest_path, provider=None, model=None, force=False))
    except SystemExit as exc:
        assert "resume cannot change semantic run options" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("resume accepted a force flag change")


def test_parallel_worker_command_is_scoped_to_one_source_manifest(tmp_path):
    manifest_path = _master_manifest(tmp_path)
    state = run_parallel._initialize_state(_args(manifest_path), overwrite=True)
    entry = state["entries"]["source-a"]

    command = run_parallel._worker_command(state, entry)

    assert str(run_parallel.SCRIPT_DIR / "generate_candidates.py") in command
    assert "--manifest" in command
    assert command[command.index("--manifest") + 1] == entry["manifest_path"]
    assert "--skip-preflight" in command
    assert "--force" in command


def test_terminate_process_group_ignores_permission_race(monkeypatch):
    def raise_permission_error(pgid, sig):
        raise PermissionError("already terminated by another canceller")

    monkeypatch.setattr(run_parallel.os, "killpg", raise_permission_error)

    run_parallel._terminate_process_group(12345)


def test_parallel_cancel_request_prevents_later_sources_from_starting(tmp_path, monkeypatch):
    manifest_path = _master_manifest(tmp_path)
    state = run_parallel._initialize_state(_args(manifest_path, workers=1), overwrite=True)
    started = []

    def fake_run_one_source(pool_state, source_id):
        started.append(source_id)
        run_parallel._request_cancel(pool_state)
        return {"source_id": source_id, "returncode": 130, "cancelled": True}

    monkeypatch.setattr(run_parallel, "_run_one_source", fake_run_one_source)

    exit_code = run_parallel._run_pool(_args(manifest_path, workers=1, skip_preflight=True), state)

    assert exit_code == 130
    assert started == ["source-a"]
    saved = json.loads(run_parallel._state_path_for_manifest(manifest_path).read_text(encoding="utf-8"))
    assert saved["entries"]["source-b"]["status"] == "cancelled"
