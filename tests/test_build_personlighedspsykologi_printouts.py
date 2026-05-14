import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_personlighedspsykologi_printouts.py"
REVIEW_GENERATE_PATH = (
    REPO_ROOT
    / "notebooklm-podcast-auto"
    / "personlighedspsykologi"
    / "evaluation"
    / "printout_review"
    / "scripts"
    / "generate_candidates.py"
)


def _load_script_module():
    spec = importlib.util.spec_from_file_location("build_personlighedspsykologi_printouts", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_review_generate_module():
    spec = importlib.util.spec_from_file_location("printout_review_generate_candidates", REVIEW_GENERATE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_main_build_uses_canonical_problem_driven_prompt_overlay(tmp_path, monkeypatch):
    module = _load_script_module()
    repo_root = tmp_path / "repo"
    prompt_path = repo_root / module.printouts.PROBLEM_DRIVEN_VARIANT_PROMPT_PATH
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text("variant prompt", encoding="utf-8")
    captured = {}

    def fake_build_printouts(**kwargs):
        captured.update(kwargs)
        return {"status": "ok", "results": []}

    monkeypatch.setattr(module, "REPO_ROOT", repo_root)
    monkeypatch.setattr(module.printouts, "build_printouts", fake_build_printouts)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_personlighedspsykologi_printouts.py",
            "--source-id",
            "source-1",
            "--provider",
            "openai",
            "--model",
            "gpt-5.5",
            "--dry-run",
        ],
    )

    assert module.main() == 0
    assert captured["prompt_version"] == module.printouts.PROBLEM_DRIVEN_PROMPT_VERSION
    assert captured["system_instruction"] == module.printouts.problem_driven_system_instruction()
    assert captured["variant_metadata"] == module.printouts.problem_driven_variant_metadata(
        mode="canonical_main",
        render_completion_markers=False,
        render_exam_bridge=False,
    )

    source = {"source_id": "source-1"}
    source_card = {"source": {"source_id": "source-1"}}
    built_prompt = captured["user_prompt_builder"](
        source=source,
        source_card=source_card,
        lecture_context={},
        course_context={},
        length_budget=None,
    )
    expected_prompt = module.printouts.problem_driven_user_prompt(
        variant_prompt_text="variant prompt",
        source=source,
        source_card=source_card,
        lecture_context={},
        course_context={},
        length_budget=None,
    )
    assert built_prompt == expected_prompt


def test_review_generator_uses_same_problem_driven_prompt_overlay_as_main_engine():
    module = _load_review_generate_module()
    source = {"source_id": "source-1"}
    source_card = {"source": {"source_id": "source-1"}}

    assert module._variant_system_instruction() == module.printout_engine.problem_driven_system_instruction()
    assert module._variant_user_prompt(
        variant_key=module.DEFAULT_VARIANT_KEY,
        variant_prompt_text="variant prompt",
        source=source,
        source_card=source_card,
        lecture_context={},
        course_context={},
    ) == module.printout_engine.problem_driven_user_prompt(
        variant_prompt_text="variant prompt",
        source=source,
        source_card=source_card,
        lecture_context={},
        course_context={},
    )
