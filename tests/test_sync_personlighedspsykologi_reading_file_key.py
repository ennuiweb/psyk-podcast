from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_script_module(script_name: str, module_name: str):
    script_path = Path(__file__).resolve().parents[1] / "scripts" / script_name
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_export_dry_run_reports_drift_without_mutating_target(monkeypatch, tmp_path, capsys):
    mod = _load_script_module(
        "sync_personlighedspsykologi_reading_file_key.py",
        "sync_personlighedspsykologi_reading_file_key_test_dry_run",
    )
    canonical = tmp_path / "reading-file-key.md"
    target = tmp_path / "onedrive-reading-file-key.md"
    canonical.write_text("**W01L1 Test**\n- Reading A -> File A.pdf\n", encoding="utf-8")
    target.write_text("outdated\n", encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(mod.__file__),
            "--canonical-path",
            str(canonical),
            "--target",
            str(target),
        ],
    )

    assert mod.main() == 0
    assert target.read_text(encoding="utf-8") == "outdated\n"

    captured = capsys.readouterr().out
    assert "MODE=export" in captured
    assert "TARGET1_STATUS=out_of_sync" in captured
    assert "DRY_RUN_ONLY: no changes applied." in captured


def test_export_fail_on_drift_returns_non_zero(monkeypatch, tmp_path, capsys):
    mod = _load_script_module(
        "sync_personlighedspsykologi_reading_file_key.py",
        "sync_personlighedspsykologi_reading_file_key_test_fail_on_drift",
    )
    canonical = tmp_path / "reading-file-key.md"
    target = tmp_path / "onedrive-reading-file-key.md"
    canonical.write_text("**W01L1 Test**\n- Reading A -> File A.pdf\n", encoding="utf-8")
    target.write_text("outdated\n", encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(mod.__file__),
            "--canonical-path",
            str(canonical),
            "--target",
            str(target),
            "--fail-on-drift",
        ],
    )

    assert mod.main() == 1
    assert "TARGET1_STATUS=out_of_sync" in capsys.readouterr().out


def test_apply_exports_canonical_to_all_targets(monkeypatch, tmp_path, capsys):
    mod = _load_script_module(
        "sync_personlighedspsykologi_reading_file_key.py",
        "sync_personlighedspsykologi_reading_file_key_test_apply_export",
    )
    canonical = tmp_path / "reading-file-key.md"
    primary_target = tmp_path / "primary-reading-file-key.md"
    secondary_target = tmp_path / "secondary-reading-file-key.md"
    canonical_text = (
        "**W11L1 Test**\n"
        "- Grundbog kapitel 11 - Postpsykologisk subjektiveringsteori → "
        "Grundbog kapitel 11 - Postpsykologisk subjektiveringsteori.pdf\n"
    )
    canonical.write_text(canonical_text, encoding="utf-8")
    primary_target.write_text("old primary\n", encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(mod.__file__),
            "--canonical-path",
            str(canonical),
            "--target",
            str(primary_target),
            "--secondary-target",
            str(secondary_target),
            "--apply",
        ],
    )

    assert mod.main() == 0

    normalized_text = (
        "**W11L1 Test**\n"
        "- Grundbog kapitel 11 - Postpsykologisk subjektiveringsteori → "
        "Grundbog kapitel 11 - Postpsykologisk subjektiveringsteori.pdf (short + full)\n"
    )
    assert primary_target.read_text(encoding="utf-8") == normalized_text
    assert secondary_target.read_text(encoding="utf-8") == normalized_text
    assert canonical.read_text(encoding="utf-8") == canonical_text

    captured = capsys.readouterr().out
    assert "TARGET1_ACTION=export_from_canonical" in captured
    assert "TARGET2_ACTION=export_from_canonical" in captured


def test_import_mode_requires_explicit_apply_to_update_canonical(monkeypatch, tmp_path, capsys):
    mod = _load_script_module(
        "sync_personlighedspsykologi_reading_file_key.py",
        "sync_personlighedspsykologi_reading_file_key_test_import",
    )
    canonical = tmp_path / "reading-file-key.md"
    target = tmp_path / "onedrive-reading-file-key.md"
    canonical.write_text("repo canonical\n", encoding="utf-8")
    target.write_text("mirror canonical\n", encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(mod.__file__),
            "--mode",
            "import",
            "--canonical-path",
            str(canonical),
            "--target",
            str(target),
        ],
    )

    assert mod.main() == 0
    assert canonical.read_text(encoding="utf-8") == "repo canonical\n"
    assert "CANONICAL_STATUS=out_of_sync" in capsys.readouterr().out

    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(mod.__file__),
            "--mode",
            "import",
            "--canonical-path",
            str(canonical),
            "--target",
            str(target),
            "--apply",
        ],
    )

    assert mod.main() == 0
    assert canonical.read_text(encoding="utf-8") == "mirror canonical\n"
    assert "CANONICAL_ACTION=import_from_primary_target" in capsys.readouterr().out


def test_normalize_exercise_titles_uses_repo_owned_default_path():
    mod = _load_script_module(
        "normalize_personlighedspsykologi_exercise_titles.py",
        "normalize_personlighedspsykologi_exercise_titles_test_default_path",
    )

    assert mod.DEFAULT_KEY_PATH == "shows/personlighedspsykologi-en/docs/reading-file-key.md"
    expected = (
        Path(__file__).resolve().parents[1]
        / "shows"
        / "personlighedspsykologi-en"
        / "docs"
        / "reading-file-key.md"
    ).resolve()
    assert mod._resolve_key_path(mod.DEFAULT_KEY_PATH) == expected
