from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_module():
    script_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "sync_personlighedspsykologi_readings_to_droplet.py"
    )
    spec = importlib.util.spec_from_file_location("sync_personlighedspsykologi_readings_to_droplet", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_clean_source_filename_strips_short_and_full_annotation():
    mod = _load_module()
    assert (
        mod._clean_source_filename(
            "W11L1 Grundbog kapitel 11 - Postpsykologisk subjektiveringsteori.pdf (short + full)"
        )
        == "W11L1 Grundbog kapitel 11 - Postpsykologisk subjektiveringsteori.pdf"
    )


def test_clean_source_filename_preserves_parentheses_in_real_filename():
    mod = _load_module()
    assert (
        mod._clean_source_filename(
            "W5L1 Freud, S. (1984-1905). Brudstykke af en hysteri-analyse (pp. 9-62, pp. 96-.pdf"
        )
        == "W5L1 Freud, S. (1984-1905). Brudstykke af en hysteri-analyse (pp. 9-62, pp. 96-.pdf"
    )


def test_parse_reading_key_supports_one_logical_reading_with_multiple_pdfs(tmp_path):
    mod = _load_module()
    reading_key = tmp_path / "reading-file-key.md"
    reading_key.write_text(
        "\n".join(
            [
                "**W03L2 Personlighedsfunktion og forstyrrelse**",
                "- Bach & Simonsen (2023) → W3L2 Bach & Simonsen (2023) kapitel 3.pdf; W3L2 Bach & Simonsen (2023) kapitel 5.pdf",
            ]
        ),
        encoding="utf-8",
    )

    entries = mod.parse_reading_key(reading_key)

    assert len(entries) == 2
    assert {entry.source_filename for entry in entries} == {
        "W3L2 Bach & Simonsen (2023) kapitel 3.pdf",
        "W3L2 Bach & Simonsen (2023) kapitel 5.pdf",
    }
    assert entries[0].reading_key == entries[1].reading_key
