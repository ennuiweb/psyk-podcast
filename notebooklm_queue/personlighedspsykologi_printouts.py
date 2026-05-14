"""Schema-v3 printable reading printout generation for Personlighedspsykologi."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import importlib.util
import sys
import tempfile
import time
from copy import deepcopy
from collections.abc import Callable
from pathlib import Path
from typing import Any

from notebooklm_queue.gemini_preprocessing import (
    DEFAULT_GEMINI_PREPROCESSING_MODEL,
    GeminiPreprocessingBackend,
    GeminiPreprocessingGenerationError,
    generate_json,
    generation_config_metadata,
    make_gemini_backend,
)
from notebooklm_queue.source_intelligence_schemas import utc_now_iso

try:
    from notebooklm_queue import personlighedspsykologi_recursive as recursive
except ImportError:
    _RECURSIVE_PATH = Path(__file__).resolve().with_name("personlighedspsykologi_recursive.py")
    _RECURSIVE_SPEC = importlib.util.spec_from_file_location("personlighedspsykologi_recursive", _RECURSIVE_PATH)
    assert _RECURSIVE_SPEC and _RECURSIVE_SPEC.loader
    recursive = importlib.util.module_from_spec(_RECURSIVE_SPEC)
    _RECURSIVE_SPEC.loader.exec_module(recursive)

SUBJECT_SLUG = recursive.SUBJECT_SLUG
DEFAULT_SOURCE_CATALOG = recursive.DEFAULT_SOURCE_CATALOG
DEFAULT_SOURCE_CARD_DIR = recursive.DEFAULT_SOURCE_CARD_DIR
DEFAULT_REVISED_LECTURE_SUBSTRATE_DIR = recursive.DEFAULT_REVISED_LECTURE_SUBSTRATE_DIR
DEFAULT_COURSE_SYNTHESIS_PATH = recursive.DEFAULT_COURSE_SYNTHESIS_PATH
DEFAULT_SUBJECT_ROOT = recursive.DEFAULT_SUBJECT_ROOT
DEFAULT_OUTPUT_ROOT = Path("notebooklm-podcast-auto/personlighedspsykologi/output")
PROMPT_VERSION = "personlighedspsykologi-reading-printouts-v3"
PROBLEM_DRIVEN_PROMPT_VERSION = "personlighedspsykologi-reading-printouts-problem-driven-v1"
PROBLEM_DRIVEN_VARIANT_KEY = "problem_driven_v1"
PROBLEM_DRIVEN_VARIANT_PROMPT_PATH = Path(
    "notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/prompts/problem-driven-v1.md"
)
PROBLEM_DRIVEN_DESIGN_DOC = "shows/personlighedspsykologi-en/docs/problem-driven-printouts.md"
PROBLEM_DRIVEN_WORKSPACE = "notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/"
SCHEMA_VERSION = 3
LEGACY_SCHEMA_VERSION = 2
CANONICAL_PRINTOUT_DIRNAME = "printouts"
CANONICAL_PRINTOUT_JSON_DIRNAME = "printout-json"
LEGACY_PRINTOUT_DIRNAME = "scaffolding"
CANONICAL_PRINTOUT_JSON_NAME = "reading-printouts.json"
LEGACY_PRINTOUT_JSON_NAME = "reading-scaffolds.json"
INTERNAL_REVIEW_ARTIFACT_DIRNAME = ".scaffolding"
REVIEW_OUTPUT_DIRNAME = "review"
PDF_STAGING_DIRNAME = "staging"
OUTPUT_LAYOUT_CANONICAL = "canonical"
OUTPUT_LAYOUT_REVIEW = "review"
RENDER_COMPLETION_MARKERS_KEY = "render_completion_markers"
RENDER_EXAM_BRIDGE_KEY = "render_exam_bridge"
V3_FIXED_TITLES = {
    "cover": "Compendium",
    "reading_guide": "Reading Guide",
    "abridged_reader": "Abridged Version",
    "active_reading": "Active Reading",
    "consolidation_sheet": "Consolidation Sheet",
    "exam_bridge": "Exam Bridge",
}
V3_RENDER_STEMS = (
    "00-cover",
    "01-reading-guide",
    "02-active-reading",
    "03-abridged-version",
    "04-consolidation-sheet",
    "05-exam-bridge",
)
V3_LEGACY_RENDER_STEMS = (
    "00-reading-guide",
    "01-abridged-reader",
    "02-active-reading",
    "03-consolidation-sheet",
    "04-exam-bridge",
)
V2_RENDER_STEMS = (
    "01-abridged-guide",
    "02-unit-test-suite",
    "03-cloze-scaffold",
)
READING_TITLE_OVERRIDES = {
    "w01l1-lewis-1999-295c67e3": "Issues in the Study of Personality Development",
    "w07l2-evans-1975-8e8a9d79": "Carl Rogers: The Man and His Ideas",
    "w07l2-giorgi-2005-55ca98f7": "Remaining Challenges for Humanistic Psychology",
    "w07l2-maslow-1968-7ea53e34": "Deficiency Motivation and Growth Motivation",
    "w08l1-lamiell-2021-be79d36e": "William Stern and Personalistic Thinking: Making Acquaintance",
    "w08l1-laux-et-al-2010-cfff840c": "Personalistic Concepts in Action: The Case of Adolf Hitler",
    "w08l2-holzkamp-1982-845aafd2": "Daglig livsførelse som subjektvidenskabeligt grundkoncept",
    "w08l2-tolman-2009-455915e0": "Holzkamp's Critical Psychology as a Science from the Standpoint of the Human Subject",
    "w09l1-dreier-1999-35da58b5": "Personal Trajectories of Participation across Contexts of Social Practice",
    "w09l1-holzkamp-2013-c3068d8a": "What Could a Psychology from the Standpoint of the Subject Be?",
    "w09l1-m-rch-and-hansen-2015-b1dbfc5f": "Fra rocker til akademiker",
    "w11l2-bruner-1999-7930abd8": "Entry into Meaning",
    "w11l2-mcadams-and-pals-2006-b9675688": "A New Big Five: Fundamental Principles for an Integrative Science of Personality",
    "w11l2-raggatt-2002-d15129af": "A Plurality of Selves? An Illustration of Polypsychism in a Recovered Addict",
    "w12l1-elias-2000-f9176ae8": "Sociogenetic and Psychogenetic Investigations",
}
PDF_RENDER_ENGINES = (
    "xelatex",
    "lualatex",
    "pdflatex",
)
TASK_VERB_PREFIXES = (
    "Skriv",
    "Vælg",
    "Forklar",
    "Afgør",
    "Tegn",
    "Brug",
    "Find",
    "Beslut",
    "Redegør",
    "Diskutér",
    "Diskuter",
    "Analyser",
)
COMPLETION_MARKER_TEXT = "[ ]"
TRANSIENT_GENERATION_RETRY_DELAYS_SECONDS = (5, 15, 30)
TRANSIENT_GENERATION_ERROR_PATTERNS = (
    "connection reset by peer",
    "connection reset",
    "broken pipe",
    "timed out",
    "timeout",
    "connection aborted",
    "connection refused",
    "temporarily unavailable",
    "service unavailable",
    "bad gateway",
    "gateway timeout",
    "internal server error",
    "remote end closed connection",
    "ssl",
    "transport",
    "connection error",
    "network is unreachable",
    "server disconnected",
    "unavailable",
    "502",
    "503",
    "504",
)

SPACING_RHYTHM_CM = 0.28
SPACING_CONTRACT_CM = {
    "guide_paragraph_gap": SPACING_RHYTHM_CM,
    "active_step_gap": SPACING_RHYTHM_CM,
    "response_line_gap_compact": 0.30,
    "response_line_gap_standard": 0.36,
    "response_line_gap_extended": 0.42,
    "completion_block_gap": SPACING_RHYTHM_CM,
    "completion_item_gap": 0.16,
    "diagram_inline_space_ceiling": 1.60,
    "diagram_dedicated_page_floor": 7.60,
}
DIAGRAM_SPACE_PROFILES_CM = {
    "grid": (5.20, 4.80, 4.00),
    "network": (4.80, 4.30, 3.60),
    "default": (4.80, 4.20, 3.40),
}
RESPONSE_LINE_MULTIPLIER_NUMERATOR = 3
RESPONSE_LINE_MULTIPLIER_DENOMINATOR = 2
PDF_BODY_LINE_SPREAD = "1.07"
PDF_CONSOLIDATION_FILL_BODY_LINE_SPREAD = "2.14"

JsonGenerator = Callable[..., dict[str, Any]]
UserPromptBuilder = Callable[..., str]


class PrintoutError(RuntimeError):
    """Raised when a printable printout cannot be generated or rendered."""


class GenerationFailure(PrintoutError):
    """Generation failed after any provider retry handling, with sanitized stats."""

    def __init__(self, message: str, *, generation_stats: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.generation_stats = dict(generation_stats or {})


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def _spacing_cm(key: str) -> float:
    return float(SPACING_CONTRACT_CM[key])


def _vspace_cm(cm: float) -> str:
    return f"\\vspace*{{{cm:.2f}cm}}"


def _vspace_key(key: str) -> str:
    return _vspace_cm(_spacing_cm(key))


def _append_spacing_gap(lines: list[str], key: str) -> None:
    lines.extend(["", _vspace_key(key), ""])


def _latex_escape_inline(text: Any) -> str:
    value = str(text or "")
    replacements = {
        "\\": r"\textbackslash{}",
        "{": r"\{",
        "}": r"\}",
        "$": r"\$",
        "&": r"\&",
        "%": r"\%",
        "#": r"\#",
        "_": r"\_",
        "^": r"\^{}",
        "~": r"\~{}",
    }
    return "".join(replacements.get(char, char) for char in value)


def _format_margin_lecture_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    match = re.fullmatch(r"w0*(\d+)\s*[-_ ]?\s*l0*(\d+)", text)
    if match:
        week_number = int(match.group(1))
        lecture_number = int(match.group(2))
        return f"forelæsning {lecture_number}, uge {week_number}"
    return text


def _metadata_comment_value(markdown_text: str, key: str) -> str:
    pattern = rf"<!--\s*printout-{re.escape(key)}:\s*(.+?)\s*-->"
    match = re.search(pattern, markdown_text, flags=re.IGNORECASE)
    return str(match.group(1) if match else "").strip()


def _pdf_margin_metadata(markdown_text: str) -> dict[str, str]:
    title_match = re.search(r"^#\s+(.+)$", markdown_text, flags=re.MULTILINE)
    source_match = re.search(r"^\*\*Kilde:\*\*\s*(.+)$", markdown_text, flags=re.MULTILINE)
    lecture_match = re.search(r"^\*\*Forelæsning:\*\*\s*(.+)$", markdown_text, flags=re.MULTILINE)
    title = _metadata_comment_value(markdown_text, "title") or str(title_match.group(1) if title_match else "").strip()
    source_title = _metadata_comment_value(markdown_text, "source") or str(source_match.group(1) if source_match else "").strip()
    lecture_key = _metadata_comment_value(markdown_text, "lecture") or str(lecture_match.group(1) if lecture_match else "").strip()
    lecture_key_margin = _format_margin_lecture_key(lecture_key)
    meta_text = " | ".join(
        item.lower()
        for item in [lecture_key_margin, source_title, title]
        if str(item).strip()
    )
    return {
        "title": title,
        "source_title": source_title,
        "lecture_key": lecture_key,
        "lecture_key_margin": lecture_key_margin,
        "meta_text": meta_text,
    }


def _pdf_wrapped_markdown(markdown_text: str, *, total_pages: int | None = None) -> str:
    metadata = _pdf_margin_metadata(markdown_text)
    meta_text = _latex_escape_inline(metadata.get("meta_text") or "")
    total_pages_value = str(total_pages) if total_pages and total_pages > 0 else "?"
    blocks = [
        r"\usepackage{fancyhdr}",
        "\n".join(
            [
                r"\makeatletter",
                r"\setlength{\headheight}{16pt}",
                r"\setlength{\headsep}{10pt}",
                r"\setlength{\footskip}{18pt}",
                rf"\AtBeginDocument{{\linespread{{{PDF_BODY_LINE_SPREAD}}}\selectfont}}",
                r"\newlength{\printoutneedspacelen}",
                r"\newlength{\printoutremainingpage}",
                r"\newcommand{\printoutneedspace}[1]{%",
                r"  \par%",
                r"  \begingroup%",
                r"  \setlength{\printoutneedspacelen}{#1}%",
                r"  \setlength{\printoutremainingpage}{\pagegoal}%",
                r"  \addtolength{\printoutremainingpage}{-\pagetotal}%",
                r"  \ifdim \printoutneedspacelen>\printoutremainingpage \vfil\break \fi%",
                r"  \endgroup%",
                r"}",
                r"\let\printoutoldsection\section",
                r"\renewcommand{\section}{\printoutneedspace{6\baselineskip}\@ifstar{\printoutoldsection*}{\printoutoldsection}}",
                r"\let\printoutoldsubsection\subsection",
                r"\renewcommand{\subsection}{\printoutneedspace{5\baselineskip}\@ifstar{\printoutoldsubsection*}{\printoutoldsubsection}}",
                r"\let\printoutoldsubsubsection\subsubsection",
                r"\renewcommand{\subsubsection}{\printoutneedspace{4\baselineskip}\@ifstar{\printoutoldsubsubsection*}{\printoutoldsubsubsection}}",
                r"\let\printoutoldparagraph\paragraph",
                r"\renewcommand{\paragraph}{\printoutneedspace{3\baselineskip}\@ifstar{\printoutoldparagraph*}{\printoutoldparagraph}}",
                r"\newcommand{\printoutmarginfont}{\ttfamily\fontsize{7.2pt}{8.4pt}\selectfont}",
                rf"\newcommand{{\printoutmarginmeta}}{{\printoutmarginfont {meta_text}}}",
                rf"\newcommand{{\printoutmarginpage}}{{\printoutmarginfont side \thepage/{total_pages_value}}}",
                r"\fancypagestyle{printoutstyle}{%",
                r"  \fancyhf{}%",
                r"  \renewcommand{\headrulewidth}{0.4pt}%",
                r"  \renewcommand{\footrulewidth}{0.4pt}%",
                r"  \fancyhead[L]{\printoutmarginpage}%",
                r"  \fancyhead[C]{\printoutmarginmeta}%",
                r"  \fancyhead[R]{\printoutmarginpage}%",
                r"  \fancyfoot[L]{\printoutmarginpage}%",
                r"  \fancyfoot[C]{\printoutmarginmeta}%",
                r"  \fancyfoot[R]{\printoutmarginpage}%",
                r"}",
                r"\fancypagestyle{plain}{%",
                r"  \fancyhf{}%",
                r"  \renewcommand{\headrulewidth}{0.4pt}%",
                r"  \renewcommand{\footrulewidth}{0.4pt}%",
                r"  \fancyhead[L]{\printoutmarginpage}%",
                r"  \fancyhead[C]{\printoutmarginmeta}%",
                r"  \fancyhead[R]{\printoutmarginpage}%",
                r"  \fancyfoot[L]{\printoutmarginpage}%",
                r"  \fancyfoot[C]{\printoutmarginmeta}%",
                r"  \fancyfoot[R]{\printoutmarginpage}%",
                r"}",
                r"\pagestyle{printoutstyle}",
                r"\makeatother",
            ]
        ),
    ]
    front_matter = ["---", "header-includes:"]
    for block in blocks:
        front_matter.append("  - |")
        for line in str(block).splitlines():
            front_matter.append(f"    {line}")
    front_matter.extend(["---", ""])
    return "\n".join(front_matter) + markdown_text.lstrip()


def _pdf_page_count(pdf_path: Path) -> int:
    if shutil.which("pdfinfo") is None:
        raise PrintoutError("pdfinfo is required to compute total page counts for PDF margins")
    result = subprocess.run(
        ["pdfinfo", str(pdf_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    match = re.search(r"^Pages:\s+(\d+)\s*$", result.stdout, flags=re.MULTILINE)
    if not match:
        raise PrintoutError(f"could not determine page count for {pdf_path}")
    return int(match.group(1))


def source_card_path(source_card_dir: Path, source_id: str) -> Path:
    return source_card_dir / f"{source_id}.json"


def _source_path_parts(source: dict[str, Any]) -> tuple[str, str]:
    lecture_key = str(source.get("lecture_key") or "UNKNOWN").strip().upper() or "UNKNOWN"
    source_id = str(source.get("source_id") or "source").strip()
    return lecture_key, source_id


def canonical_baseline_output_dir_for_source(output_root: Path, source: dict[str, Any]) -> Path:
    lecture_key, source_id = _source_path_parts(source)
    return output_root / lecture_key / CANONICAL_PRINTOUT_DIRNAME / source_id


def canonical_baseline_legacy_output_dir_for_source(output_root: Path, source: dict[str, Any]) -> Path:
    lecture_key, source_id = _source_path_parts(source)
    return output_root / lecture_key / LEGACY_PRINTOUT_DIRNAME / source_id


def _normalize_output_layout(output_layout: str | None) -> str:
    value = str(output_layout or OUTPUT_LAYOUT_CANONICAL).strip().lower()
    if value not in {OUTPUT_LAYOUT_CANONICAL, OUTPUT_LAYOUT_REVIEW}:
        raise PrintoutError(f"unknown printout output layout: {output_layout!r}")
    return value


def printout_source_root(
    output_root: Path,
    source: dict[str, Any],
    *,
    output_layout: str = OUTPUT_LAYOUT_CANONICAL,
) -> Path:
    if _normalize_output_layout(output_layout) == OUTPUT_LAYOUT_CANONICAL:
        return output_root
    return output_root


def _parse_test_dir_index(name: str) -> int | None:
    match = re.fullmatch(r"(\d{3,})", str(name or "").strip())
    if not match:
        return None
    return int(match.group(1))


def _existing_test_dirs(source_root: Path) -> list[Path]:
    if not source_root.exists():
        return []
    dirs: list[tuple[int, Path]] = []
    for child in source_root.iterdir():
        if not child.is_dir():
            continue
        index = _parse_test_dir_index(child.name)
        if index is None:
            continue
        dirs.append((index, child))
    return [path for _, path in sorted(dirs, key=lambda item: item[0])]


def latest_test_dir_for_source_root(source_root: Path) -> Path | None:
    test_dirs = _existing_test_dirs(source_root)
    if test_dirs:
        return test_dirs[-1]
    flat_json = source_root / CANONICAL_PRINTOUT_JSON_NAME
    return source_root if flat_json.exists() else None


def output_dir_for_source(
    output_root: Path,
    source: dict[str, Any],
    *,
    output_layout: str = OUTPUT_LAYOUT_CANONICAL,
) -> Path:
    return printout_source_root(output_root, source, output_layout=output_layout)


def legacy_printout_dir_for_source(output_root: Path, source: dict[str, Any]) -> Path:
    return canonical_baseline_output_dir_for_source(output_root, source)


def legacy_output_dir_for_source(output_root: Path, source: dict[str, Any]) -> Path:
    return canonical_baseline_legacy_output_dir_for_source(output_root, source)


def _artifact_provider_model_slug(provider: str, model: str) -> str:
    return f"{_filename_slug(provider)}-{_filename_slug(model)}"


def artifact_dir_for_source_id(
    output_root: Path,
    *,
    source_id: str,
    provider: str | None = None,
    model: str | None = None,
) -> Path:
    if provider and model:
        return (
            output_root
            / INTERNAL_REVIEW_ARTIFACT_DIRNAME
            / "artifacts"
            / _artifact_provider_model_slug(provider, model)
            / _filename_slug(source_id)
        )
    return output_root / INTERNAL_REVIEW_ARTIFACT_DIRNAME / source_id


def artifact_json_path_for_source_id(
    output_root: Path,
    *,
    source_id: str,
    provider: str | None = None,
    model: str | None = None,
) -> Path:
    return artifact_dir_for_source_id(
        output_root,
        source_id=source_id,
        provider=provider,
        model=model,
    ) / LEGACY_PRINTOUT_JSON_NAME


def artifact_dir_for_output_dir(output_root: Path, source: dict[str, Any], output_dir: Path) -> Path:
    del output_dir
    _, source_id = _source_path_parts(source)
    return output_root / INTERNAL_REVIEW_ARTIFACT_DIRNAME / source_id


def artifact_json_path_for_output_dir(
    output_root: Path,
    source: dict[str, Any],
    output_dir: Path,
    *,
    provider: str | None = None,
    model: str | None = None,
    output_layout: str = OUTPUT_LAYOUT_CANONICAL,
) -> Path:
    _, source_id = _source_path_parts(source)
    if _normalize_output_layout(output_layout) == OUTPUT_LAYOUT_CANONICAL:
        del provider, model
        return output_root / CANONICAL_PRINTOUT_JSON_DIRNAME / _filename_slug(source_id) / CANONICAL_PRINTOUT_JSON_NAME
    return artifact_json_path_for_source_id(
        output_root,
        source_id=source_id,
        provider=provider,
        model=model,
    )


def _legacy_json_path_in_output_dir(output_dir: Path) -> Path:
    return output_dir / CANONICAL_PRINTOUT_JSON_NAME


def _find_existing_artifact_json(
    output_root: Path,
    source: dict[str, Any],
    output_dir: Path,
    *,
    provider: str | None = None,
    model: str | None = None,
    output_layout: str = OUTPUT_LAYOUT_CANONICAL,
) -> Path | None:
    _, source_id = _source_path_parts(source)
    preferred = artifact_json_path_for_output_dir(
        output_root,
        source,
        output_dir,
        provider=provider,
        model=model,
        output_layout=output_layout,
    )
    if preferred.exists():
        return preferred
    old_nested_canonical = canonical_baseline_output_dir_for_source(output_root, source) / CANONICAL_PRINTOUT_JSON_NAME
    if old_nested_canonical.exists():
        return old_nested_canonical
    legacy_preferred = artifact_json_path_for_source_id(output_root, source_id=source_id)
    if legacy_preferred.exists():
        return legacy_preferred
    old_canonical = _legacy_json_path_in_output_dir(output_dir)
    if old_canonical.exists():
        return old_canonical
    legacy_root = legacy_output_dir_for_source(output_root, source)
    legacy_direct = legacy_root / LEGACY_PRINTOUT_JSON_NAME
    if legacy_direct.exists():
        return legacy_direct
    legacy_numbered_dirs = _existing_test_dirs(legacy_root)
    if legacy_numbered_dirs:
        candidate = legacy_numbered_dirs[-1] / LEGACY_PRINTOUT_JSON_NAME
        if candidate.exists():
            return candidate
    source_root = legacy_printout_dir_for_source(output_root, source)
    numbered_dirs = _existing_test_dirs(source_root)
    if numbered_dirs:
        candidate = numbered_dirs[-1] / CANONICAL_PRINTOUT_JSON_NAME
        if candidate.exists():
            return candidate
    if output_root.name == REVIEW_OUTPUT_DIRNAME:
        legacy_run_roots = sorted(
            (output_root.parent / "runs").glob(
                f"*/candidate_output/{INTERNAL_REVIEW_ARTIFACT_DIRNAME}/{source_id}/{LEGACY_PRINTOUT_JSON_NAME}"
            ),
            key=lambda path: path.stat().st_mtime,
        )
        if legacy_run_roots:
            return legacy_run_roots[-1]
    return None


def _copy_printout_tree(
    *,
    source_dir: Path,
    target_dir: Path,
    legacy_json_name: bool = False,
    skip_json_files: bool = False,
) -> None:
    if not source_dir.exists():
        return
    if source_dir.resolve() == target_dir.resolve():
        return
    target_dir.mkdir(parents=True, exist_ok=True)
    for child in source_dir.iterdir():
        if not child.is_file():
            continue
        if skip_json_files and child.suffix.lower() == ".json":
            continue
        target_name = child.name
        if legacy_json_name and child.name == CANONICAL_PRINTOUT_JSON_NAME:
            target_name = LEGACY_PRINTOUT_JSON_NAME
        elif not legacy_json_name and child.name == LEGACY_PRINTOUT_JSON_NAME:
            target_name = CANONICAL_PRINTOUT_JSON_NAME
        target_path = target_dir / target_name
        if child.suffix.lower() in {".json", ".md"}:
            target_path.write_text(child.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            target_path.write_bytes(child.read_bytes())


def _promote_legacy_printouts_if_present(
    *,
    canonical_out_dir: Path,
    legacy_printout_dir: Path,
    legacy_scaffolding_dir: Path,
) -> None:
    source_id = legacy_printout_dir.name
    if canonical_out_dir.name != source_id:
        return
    lecture_key = legacy_printout_dir.parent.parent.name if legacy_printout_dir.parent.name == CANONICAL_PRINTOUT_DIRNAME else "UNKNOWN"
    canonical_json_path = (
        canonical_out_dir
        / CANONICAL_PRINTOUT_JSON_DIRNAME
        / _filename_slug(source_id)
        / CANONICAL_PRINTOUT_JSON_NAME
    )
    source_pdf_prefix = f"{_filename_slug(lecture_key)}--{_filename_slug(source_id)}--"
    if canonical_json_path.exists() or any(canonical_out_dir.glob(f"{source_pdf_prefix}*.pdf")):
        return
    for legacy_dir in (legacy_printout_dir, legacy_scaffolding_dir):
        if legacy_dir.exists() and any(legacy_dir.glob("*.pdf")):
            _copy_printout_tree(
                source_dir=legacy_dir,
                target_dir=canonical_out_dir,
                legacy_json_name=False,
                skip_json_files=True,
            )
            return


def _prune_empty_dirs(path: Path, *, stop_at: Path) -> None:
    stop = stop_at.resolve()
    current = path
    while True:
        try:
            resolved = current.resolve()
        except FileNotFoundError:
            current = current.parent
            continue
        if resolved == stop:
            return
        if not current.exists() or not current.is_dir():
            current = current.parent
            continue
        if any(current.iterdir()):
            return
        current.rmdir()
        current = current.parent


def _cleanup_legacy_review_dirs(*, output_root: Path, legacy_dirs: list[Path]) -> None:
    for legacy_dir in legacy_dirs:
        if legacy_dir.exists():
            shutil.rmtree(legacy_dir)
            _prune_empty_dirs(legacy_dir.parent, stop_at=output_root)


def select_sources(
    *,
    source_catalog_path: Path,
    lecture_keys: list[str] | None = None,
    source_ids: list[str] | None = None,
    source_families: set[str] | None = None,
) -> list[dict[str, Any]]:
    catalog = read_json(source_catalog_path)
    if not isinstance(catalog, dict):
        raise PrintoutError(f"invalid source catalog: {source_catalog_path}")
    normalized_lectures = set(recursive.normalize_lecture_keys(",".join(lecture_keys or [])))
    normalized_source_ids = {item.strip() for item in source_ids or [] if item.strip()}
    selected: list[dict[str, Any]] = []
    for source in catalog.get("sources", []):
        if not isinstance(source, dict):
            continue
        source_id = str(source.get("source_id") or "").strip()
        source_family = str(source.get("source_family") or "").strip()
        lecture_values = set(recursive.normalize_lecture_keys(str(source.get("lecture_key") or "")))
        for value in source.get("lecture_keys", []) or []:
            lecture_values.update(recursive.normalize_lecture_keys(str(value or "")))
        if normalized_source_ids and source_id not in normalized_source_ids:
            continue
        if normalized_lectures and not lecture_values.intersection(normalized_lectures):
            continue
        if source_families is not None and source_family not in source_families:
            continue
        if not source.get("source_exists", False):
            continue
        selected.append(source)
    return sorted(
        selected,
        key=lambda item: (
            str(item.get("lecture_key") or ""),
            int(item.get("sequence_index") or 0),
            str(item.get("source_id") or ""),
        ),
    )


def _compact_source_card(source_card: dict[str, Any]) -> dict[str, Any]:
    analysis = source_card.get("analysis") if isinstance(source_card.get("analysis"), dict) else {}
    return {
        "source": source_card.get("source", {}),
        "analysis": {
            "theory_role": analysis.get("theory_role", ""),
            "source_role": analysis.get("source_role", ""),
            "relation_to_lecture": analysis.get("relation_to_lecture", ""),
            "central_claims": analysis.get("central_claims", [])[:6],
            "key_concepts": analysis.get("key_concepts", [])[:8],
            "distinctions": analysis.get("distinctions", [])[:6],
            "likely_misunderstandings": analysis.get("likely_misunderstandings", [])[:5],
            "quote_targets": analysis.get("quote_targets", [])[:4],
            "grounding_notes": analysis.get("grounding_notes", [])[:4],
        },
    }


def _load_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists() or not path.is_file():
        return None
    payload = read_json(path)
    return payload if isinstance(payload, dict) else None


def _compact_lecture_context(revised_substrate_dir: Path, lecture_key: str) -> dict[str, Any] | None:
    payload = _load_optional_json(revised_substrate_dir / f"{lecture_key}.json")
    if payload is None:
        return None
    analysis = payload.get("analysis") if isinstance(payload.get("analysis"), dict) else {}
    return {
        "lecture_key": lecture_key,
        "what_matters_more": analysis.get("what_matters_more", [])[:5],
        "de_emphasize": analysis.get("de_emphasize", [])[:4],
        "strongest_sideways_connections": analysis.get("strongest_sideways_connections", [])[:5],
        "top_down_course_relevance": analysis.get("top_down_course_relevance", ""),
        "carry_forward": analysis.get("carry_forward", [])[:5],
    }


def _compact_course_context(course_synthesis_path: Path) -> dict[str, Any] | None:
    payload = _load_optional_json(course_synthesis_path)
    if payload is None:
        return None
    analysis = payload.get("analysis") if isinstance(payload.get("analysis"), dict) else {}
    return {
        "scope": payload.get("scope", {}),
        "course_arc": analysis.get("course_arc", ""),
        "top_down_priorities": analysis.get("top_down_priorities", [])[:8],
        "sideways_relations": analysis.get("sideways_relations", [])[:8],
        "weak_spots": analysis.get("weak_spots", [])[:5],
    }


def _budget_bounds(minimum: int, maximum: int) -> dict[str, int]:
    return {"min": minimum, "max": maximum}


def _budget_max(budget: dict[str, Any], *keys: str) -> int:
    value: Any = budget
    for key in keys:
        value = value.get(key) if isinstance(value, dict) else None
    if isinstance(value, dict):
        return int(value.get("max") or 0)
    return 0


def _budget_min(budget: dict[str, Any], *keys: str) -> int:
    value: Any = budget
    for key in keys:
        value = value.get(key) if isinstance(value, dict) else None
    if isinstance(value, dict):
        return int(value.get("min") or 0)
    return 0


def _budget_range_text(bounds: dict[str, int]) -> str:
    minimum = int(bounds.get("min") or 0)
    maximum = int(bounds.get("max") or 0)
    if minimum == maximum:
        return str(minimum)
    return f"{minimum}-{maximum}"


def _coerce_positive_int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _extract_page_count(source: dict[str, Any] | None) -> int | None:
    if not isinstance(source, dict):
        return None
    direct = _coerce_positive_int(source.get("page_count"))
    if direct:
        return direct
    file_info = source.get("file_info") if isinstance(source.get("file_info"), dict) else {}
    return _coerce_positive_int(file_info.get("page_count"))


def _length_band_tier(value: Any) -> int:
    text = str(value or "").strip().lower()
    if text in {"short", "brief", "kort"}:
        return 0
    if text in {"medium", "middels", "mellem"}:
        return 1
    if text in {"long", "extended", "lang", "book"}:
        return 2
    return 0


def _page_count_tier(page_count: int | None) -> int:
    if page_count is None:
        return 0
    if page_count <= 8:
        return 0
    if page_count <= 22:
        return 1
    return 2


def _complexity_tier(source_card: dict[str, Any] | None) -> int:
    if not isinstance(source_card, dict):
        return 0
    analysis = source_card.get("analysis") if isinstance(source_card.get("analysis"), dict) else {}
    score = (
        len(_coerce_list(analysis.get("central_claims")))
        + len(_coerce_list(analysis.get("key_concepts")))
        + len(_coerce_list(analysis.get("distinctions")))
        + len(_coerce_list(analysis.get("likely_misunderstandings")))
        + len(_coerce_list(analysis.get("grounding_notes")))
    )
    if score <= 12:
        return 0
    if score <= 22:
        return 1
    return 2


def build_printout_length_budget(
    *,
    source: dict[str, Any] | None = None,
    source_card: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_payload = source if isinstance(source, dict) else {}
    if not source_payload and isinstance(source_card, dict):
        source_payload = source_card.get("source") if isinstance(source_card.get("source"), dict) else {}
    length_band = str(
        source_payload.get("length_band")
        or (source_card.get("source", {}) if isinstance(source_card, dict) else {}).get("length_band")
        or ""
    ).strip()
    page_count = _extract_page_count(source_payload) or _extract_page_count(
        source_card.get("source") if isinstance(source_card, dict) else {}
    )
    band_tier = _length_band_tier(length_band)
    page_tier = _page_count_tier(page_count)
    complexity = _complexity_tier(source_card)
    tier = max(band_tier, page_tier)
    if complexity == 2 and tier < 2:
        tier += 1
    tier = max(0, min(2, tier))
    profile = ("short", "medium", "long")[tier]
    if tier == 0:
        reading_guide = {
            "teaser_paragraphs": _budget_bounds(3, 4),
            "opening_passages": _budget_bounds(2, 3),
            "subproblems": _budget_bounds(3, 4),
            "reading_route": _budget_bounds(3, 4),
            "key_quote_targets": _budget_bounds(3, 3),
            "do_not_get_stuck_on": _budget_bounds(2, 3),
        }
        abridged_sections = _budget_bounds(3, 4)
        active_steps = _budget_bounds(4, 5)
        consolidation = {
            "fill_in_sentences": _budget_bounds(5, 6),
            "diagram_tasks": _budget_bounds(1, 1),
        }
        exam_bridge = {
            "use_this_text_for": _budget_bounds(3, 4),
            "course_connections": _budget_bounds(2, 3),
            "comparison_targets": _budget_bounds(2, 3),
            "exam_moves": _budget_bounds(3, 4),
            "misunderstanding_traps": _budget_bounds(2, 3),
            "mini_exam_answer_plan_slots": _budget_bounds(3, 4),
        }
    elif tier == 1:
        reading_guide = {
            "teaser_paragraphs": _budget_bounds(4, 5),
            "opening_passages": _budget_bounds(2, 4),
            "subproblems": _budget_bounds(4, 5),
            "reading_route": _budget_bounds(4, 5),
            "key_quote_targets": _budget_bounds(3, 4),
            "do_not_get_stuck_on": _budget_bounds(2, 4),
        }
        abridged_sections = _budget_bounds(4, 6)
        active_steps = _budget_bounds(5, 6)
        consolidation = {
            "fill_in_sentences": _budget_bounds(6, 7),
            "diagram_tasks": _budget_bounds(1, 2),
        }
        exam_bridge = {
            "use_this_text_for": _budget_bounds(4, 5),
            "course_connections": _budget_bounds(3, 4),
            "comparison_targets": _budget_bounds(3, 4),
            "exam_moves": _budget_bounds(4, 5),
            "misunderstanding_traps": _budget_bounds(3, 4),
            "mini_exam_answer_plan_slots": _budget_bounds(4, 5),
        }
    else:
        reading_guide = {
            "teaser_paragraphs": _budget_bounds(5, 6),
            "opening_passages": _budget_bounds(3, 4),
            "subproblems": _budget_bounds(5, 6),
            "reading_route": _budget_bounds(5, 7),
            "key_quote_targets": _budget_bounds(4, 4),
            "do_not_get_stuck_on": _budget_bounds(3, 5),
        }
        abridged_sections = _budget_bounds(5, 8)
        active_steps = _budget_bounds(6, 8)
        consolidation = {
            "fill_in_sentences": _budget_bounds(7, 8),
            "diagram_tasks": _budget_bounds(2, 3),
        }
        exam_bridge = {
            "use_this_text_for": _budget_bounds(5, 6),
            "course_connections": _budget_bounds(3, 5),
            "comparison_targets": _budget_bounds(3, 5),
            "exam_moves": _budget_bounds(5, 6),
            "misunderstanding_traps": _budget_bounds(3, 5),
            "mini_exam_answer_plan_slots": _budget_bounds(4, 5),
        }
    return {
        "profile": profile,
        "signals": {
            "length_band": length_band or "",
            "page_count": page_count,
            "complexity_tier": complexity,
        },
        "reading_guide": reading_guide,
        "abridged_reader": {"sections": abridged_sections},
        "active_reading": {"solve_steps": active_steps},
        "consolidation_sheet": consolidation,
        "exam_bridge": exam_bridge,
    }


def _string_schema() -> dict[str, str]:
    return {"type": "string"}


def _string_list_schema(*, min_items: int = 0, max_items: int | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "array", "items": _string_schema()}
    if min_items:
        schema["minItems"] = min_items
    # Gemini rejects maxItems in response schemas; upper bounds are enforced locally.
    return schema


def _object_list_schema(
    *,
    properties: dict[str, Any],
    required: list[str],
    min_items: int = 0,
    max_items: int | None = None,
) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "array",
        "items": {"type": "object", "properties": properties, "required": required},
    }
    if min_items:
        schema["minItems"] = min_items
    # Gemini rejects maxItems in response schemas; upper bounds are enforced locally.
    return schema


def scaffold_response_schema() -> dict[str, Any]:
    quote_anchor = {
        "phrase": _string_schema(),
        "why_it_matters": _string_schema(),
        "source_location": _string_schema(),
    }
    subproblem = {
        "number": _string_schema(),
        "question": _string_schema(),
        "why_it_matters": _string_schema(),
        "answer_form": _string_schema(),
    }
    quote_target = {
        "target": _string_schema(),
        "why": _string_schema(),
        "where_to_look": _string_schema(),
    }
    source_passage = {
        "source_location": _string_schema(),
        "passage": _string_schema(),
        "why_it_matters": _string_schema(),
    }
    opening_passage = {
        "number": _string_schema(),
        "source_location": _string_schema(),
        "excerpt": _string_schema(),
        "open_question": _string_schema(),
    }
    route_item = {
        "number": _string_schema(),
        "source_location": _string_schema(),
        "task": _string_schema(),
        "why_it_matters": _string_schema(),
        "stop_signal": _string_schema(),
    }
    abridged_section = {
        "number": _string_schema(),
        "source_location": _string_schema(),
        "heading": _string_schema(),
        "solves_subproblem": _string_schema(),
        "local_problem": _string_schema(),
        "explanation_paragraphs": _string_list_schema(min_items=2, max_items=5),
        "key_points": _string_list_schema(min_items=1, max_items=5),
        "quote_anchors": _object_list_schema(
            properties=quote_anchor,
            required=["phrase", "why_it_matters", "source_location"],
            min_items=0,
            max_items=3,
        ),
        "source_passages": _object_list_schema(
            properties=source_passage,
            required=["source_location", "passage", "why_it_matters"],
            min_items=0,
            max_items=1,
        ),
        "no_quote_anchor_needed": _string_schema(),
    }
    solve_step = {
        "number": _string_schema(),
        "subproblem_ref": _string_schema(),
        "prompt": _string_schema(),
        "task_type": _string_schema(),
        "abridged_reader_location": _string_schema(),
        "answer_shape": _string_schema(),
        "blank_lines": {"type": "integer"},
        "done_signal": _string_schema(),
    }
    cloze_sentence = {
        "number": _string_schema(),
        "sentence": _string_schema(),
        "where_to_look": _string_schema(),
        "answer_shape": _string_schema(),
    }
    diagram_task = {
        "number": _string_schema(),
        "task": _string_schema(),
        "required_elements": _string_list_schema(min_items=2, max_items=6),
        "blank_space_hint": _string_schema(),
    }
    course_connection = {
        "course_theme": _string_schema(),
        "connection": _string_schema(),
    }
    comparison_target = {
        "compare_with": _string_schema(),
        "how_to_compare": _string_schema(),
    }
    exam_move = {
        "prompt_type": _string_schema(),
        "use_in_answer": _string_schema(),
        "caution": _string_schema(),
    }
    misunderstanding_trap = {
        "trap": _string_schema(),
        "better_reading": _string_schema(),
    }
    return {
        "type": "object",
        "properties": {
            "metadata": {
                "type": "object",
                "properties": {
                    "language": _string_schema(),
                    "source_id": _string_schema(),
                    "lecture_key": _string_schema(),
                    "source_title": _string_schema(),
                },
                "required": ["language", "source_id", "lecture_key", "source_title"],
            },
            "reading_guide": {
                "type": "object",
                "properties": {
                    "title": _string_schema(),
                    "how_to_use": _string_schema(),
                    "teaser_paragraphs": _string_list_schema(min_items=3, max_items=6),
                    "opening_passages": _object_list_schema(
                        properties=opening_passage,
                        required=["number", "source_location", "excerpt", "open_question"],
                        min_items=2,
                        max_items=4,
                    ),
                    "main_problem": _string_schema(),
                    "subproblems": _object_list_schema(
                        properties=subproblem,
                        required=["number", "question", "why_it_matters", "answer_form"],
                        min_items=3,
                        max_items=6,
                    ),
                    "why_this_text_matters": _string_schema(),
                    "overview": _string_list_schema(min_items=3, max_items=3),
                    "reading_route": _object_list_schema(
                        properties=route_item,
                        required=["number", "source_location", "task", "why_it_matters", "stop_signal"],
                        min_items=3,
                        max_items=7,
                    ),
                    "key_quote_targets": _object_list_schema(
                        properties=quote_target,
                        required=["target", "why", "where_to_look"],
                        min_items=3,
                        max_items=4,
                    ),
                    "do_not_get_stuck_on": _string_list_schema(min_items=2, max_items=5),
                },
                "required": [
                    "title",
                    "how_to_use",
                    "teaser_paragraphs",
                    "main_problem",
                    "subproblems",
                    "why_this_text_matters",
                    "overview",
                    "reading_route",
                    "key_quote_targets",
                    "do_not_get_stuck_on",
                ],
            },
            "abridged_reader": {
                "type": "object",
                "properties": {
                    "title": _string_schema(),
                    "how_to_use": _string_schema(),
                    "coverage_note": _string_schema(),
                    "sections": _object_list_schema(
                        properties=abridged_section,
                        required=[
                            "number",
                            "source_location",
                            "heading",
                            "solves_subproblem",
                            "local_problem",
                            "explanation_paragraphs",
                            "key_points",
                            "quote_anchors",
                            "source_passages",
                            "no_quote_anchor_needed",
                        ],
                        min_items=3,
                        max_items=9,
                    ),
                },
                "required": ["title", "how_to_use", "coverage_note", "sections"],
            },
            "active_reading": {
                "type": "object",
                "properties": {
                    "title": _string_schema(),
                    "instructions": _string_schema(),
                    "solve_steps": _object_list_schema(
                        properties=solve_step,
                        required=[
                            "number",
                            "subproblem_ref",
                            "prompt",
                            "task_type",
                            "abridged_reader_location",
                            "answer_shape",
                            "blank_lines",
                            "done_signal",
                        ],
                        min_items=6,
                        max_items=10,
                    ),
                },
                "required": ["title", "instructions", "solve_steps"],
            },
            "consolidation_sheet": {
                "type": "object",
                "properties": {
                    "title": _string_schema(),
                    "instructions": _string_schema(),
                    "overview": _string_list_schema(min_items=3, max_items=3),
                    "fill_in_sentences": _object_list_schema(
                        properties=cloze_sentence,
                        required=["number", "sentence", "where_to_look", "answer_shape"],
                        min_items=5,
                        max_items=8,
                    ),
                    "diagram_tasks": _object_list_schema(
                        properties=diagram_task,
                        required=["number", "task", "required_elements", "blank_space_hint"],
                        min_items=1,
                        max_items=3,
                    ),
                },
                "required": ["title", "instructions", "overview", "fill_in_sentences", "diagram_tasks"],
            },
            "exam_bridge": {
                "type": "object",
                "properties": {
                    "title": _string_schema(),
                    "instructions": _string_schema(),
                    "use_this_text_for": _string_list_schema(min_items=3, max_items=6),
                    "course_connections": _object_list_schema(
                        properties=course_connection,
                        required=["course_theme", "connection"],
                        min_items=2,
                        max_items=5,
                    ),
                    "comparison_targets": _object_list_schema(
                        properties=comparison_target,
                        required=["compare_with", "how_to_compare"],
                        min_items=2,
                        max_items=5,
                    ),
                    "exam_moves": _object_list_schema(
                        properties=exam_move,
                        required=["prompt_type", "use_in_answer", "caution"],
                        min_items=3,
                        max_items=6,
                    ),
                    "misunderstanding_traps": _object_list_schema(
                        properties=misunderstanding_trap,
                        required=["trap", "better_reading"],
                        min_items=2,
                        max_items=5,
                    ),
                    "mini_exam_prompt_question": _string_schema(),
                    "mini_exam_answer_plan_slots": _string_list_schema(min_items=3, max_items=5),
                },
                "required": [
                    "title",
                    "instructions",
                    "use_this_text_for",
                    "course_connections",
                    "comparison_targets",
                    "exam_moves",
                    "misunderstanding_traps",
                    "mini_exam_prompt_question",
                    "mini_exam_answer_plan_slots",
                ],
            },
        },
        "required": [
            "metadata",
            "reading_guide",
            "abridged_reader",
            "active_reading",
            "consolidation_sheet",
            "exam_bridge",
        ],
    }


def scaffold_prompt_contract(length_budget: dict[str, Any] | None = None) -> dict[str, Any]:
    """Human-readable JSON contract used when Gemini schema mode is too restrictive."""
    budget = length_budget or build_printout_length_budget()
    guide_budget = budget["reading_guide"]
    reader_budget = budget["abridged_reader"]
    active_budget = budget["active_reading"]
    consolidation_budget = budget["consolidation_sheet"]
    exam_budget = budget["exam_bridge"]
    return {
        "top_level_required_keys": [
            "metadata",
            "reading_guide",
            "abridged_reader",
            "active_reading",
            "consolidation_sheet",
            "exam_bridge",
        ],
        "metadata": {
            "required_keys": ["language", "source_id", "lecture_key", "source_title"],
            "language": "da",
        },
        "reading_guide": {
            "required_keys": [
                "title",
                "how_to_use",
                "teaser_paragraphs",
                "main_problem",
                "subproblems",
                "why_this_text_matters",
                "overview",
                "reading_route",
                "key_quote_targets",
                "do_not_get_stuck_on",
            ],
            "cardinality": {
                "teaser_paragraphs": f"{_budget_range_text(guide_budget['teaser_paragraphs'])} short teaser paragraphs totaling roughly half to one page",
                "subproblems": f"{_budget_range_text(guide_budget['subproblems'])} objects",
                "overview": "exactly 3 strings",
                "reading_route": f"{_budget_range_text(guide_budget['reading_route'])} objects in source order",
                "key_quote_targets": f"{_budget_range_text(guide_budget['key_quote_targets'])} objects",
                "do_not_get_stuck_on": f"{_budget_range_text(guide_budget['do_not_get_stuck_on'])} strings",
            },
            "optional_keys": ["opening_passages"],
            "opening_passage_keys": ["number", "source_location", "excerpt", "open_question"],
            "subproblem_keys": ["number", "question", "why_it_matters", "answer_form"],
            "reading_route_item_keys": ["number", "source_location", "task", "why_it_matters", "stop_signal"],
            "key_quote_target_keys": ["target", "why", "where_to_look"],
            "quote_target_limit": "target must be max 12 words and max 140 characters",
        },
        "abridged_reader": {
            "required_keys": ["title", "how_to_use", "coverage_note", "sections"],
            "cardinality": {"sections": f"{_budget_range_text(reader_budget['sections'])} objects in source order"},
            "section_required_keys": [
                "number",
                "source_location",
                "heading",
                "solves_subproblem",
                "local_problem",
                "explanation_paragraphs",
                "key_points",
                "quote_anchors",
                "source_passages",
                "no_quote_anchor_needed",
            ],
            "section_cardinality": {
                "explanation_paragraphs": "2-5 strings; each paragraph max 95 words",
                "key_points": "1-5 strings",
                "quote_anchors": "0-3 internal search-anchor objects; each phrase must be max 12 words and max 140 characters",
                "source_passages": "0-1 visible quote objects; prefer complete sentence-level excerpts, usually 20-70 words; mark omitted beginnings or endings with (...)",
            },
            "quote_anchor_keys": ["phrase", "why_it_matters", "source_location"],
            "source_passage_keys": ["source_location", "passage", "why_it_matters"],
        },
        "active_reading": {
            "required_keys": ["title", "instructions", "solve_steps"],
            "cardinality": {
                "solve_steps": f"{_budget_range_text(active_budget['solve_steps'])} objects solved with abridged_reader open",
            },
            "note": "The final active_reading sheet is engine-derived from reading_guide and abridged_reader. Model-provided solve_steps are treated as optional hints only.",
            "solve_step_keys": [
                "number",
                "subproblem_ref",
                "prompt",
                "task_type",
                "abridged_reader_location",
                "answer_shape",
                "blank_lines",
                "done_signal",
            ],
        },
        "consolidation_sheet": {
            "required_keys": ["title", "instructions", "overview", "fill_in_sentences", "diagram_tasks"],
            "cardinality": {
                "overview": "exactly 3 strings, no blanks",
                "fill_in_sentences": f"{_budget_range_text(consolidation_budget['fill_in_sentences'])} objects, each sentence has exactly one __________ blank",
                "diagram_tasks": f"{_budget_range_text(consolidation_budget['diagram_tasks'])} objects, all answerable from abridged_reader alone",
            },
            "fill_in_sentence_keys": ["number", "sentence", "where_to_look", "answer_shape"],
            "fill_in_sentence_note": "where_to_look is treated as a hint and normalized by the engine to abridged_reader sections when needed.",
            "diagram_task_keys": ["number", "task", "required_elements", "blank_space_hint"],
        },
        "exam_bridge": {
            "required_keys": [
                "title",
                "instructions",
                "use_this_text_for",
                "course_connections",
                "comparison_targets",
                "exam_moves",
                "misunderstanding_traps",
                "mini_exam_prompt_question",
                "mini_exam_answer_plan_slots",
            ],
            "cardinality": {
                "use_this_text_for": f"{_budget_range_text(exam_budget['use_this_text_for'])} strings",
                "course_connections": f"{_budget_range_text(exam_budget['course_connections'])} objects with course_theme and connection",
                "comparison_targets": f"{_budget_range_text(exam_budget['comparison_targets'])} objects with compare_with and how_to_compare",
                "exam_moves": f"{_budget_range_text(exam_budget['exam_moves'])} objects with prompt_type, use_in_answer, and caution",
                "misunderstanding_traps": f"{_budget_range_text(exam_budget['misunderstanding_traps'])} objects with trap and better_reading",
                "mini_exam_answer_plan_slots": f"{_budget_range_text(exam_budget['mini_exam_answer_plan_slots'])} strings",
            },
        },
        "global_quality_rules": [
            "All required keys must be present even when a list is short.",
            "Use Danish for student-facing text.",
            "Document titles are fixed canonical English headings that match the artifact type; do not invent stylistic titles.",
            "Do not reveal answers in active_reading or consolidation_sheet.",
            "active_reading and consolidation_sheet must be solvable after reading abridged_reader alone.",
            "reading_guide should render as coherent teaser prose, not as a worksheet, checklist, or outline.",
            "active_reading is an open-book guided-solve sheet; consolidation_sheet is the later recall sheet.",
            "abridged_reader_location and where_to_look fields must point to abridged_reader sections, not source pages or the original PDF.",
            "answer_shape fields describe answer format only, never semantic hints.",
            "done_signal and stop_signal must not contain parenthetical answer hints.",
            "active_reading should use fewer, larger solve steps rather than a long fact-quiz.",
            "consolidation_sheet must not depend on source figures, page numbers, or opening the original PDF.",
            "exam_bridge should read like oral-exam cues, not like a long advice handout.",
            "Use quote_anchors only as internal search anchors; visible quoted wording inside abridged_reader belongs in source_passages, and should carry enough sentence context to stand alone.",
        ],
    }


def printout_generation_config_metadata() -> dict[str, Any]:
    metadata = generation_config_metadata()
    metadata["response_json_schema"] = None
    metadata["json_contract"] = "prompt_contract_v3_with_local_validation"
    return metadata


def printout_system_instruction() -> str:
    return "\n".join(
        [
            "You generate printable Danish reading scaffolds for Personlighedspsykologi.",
            "Return only valid JSON that matches the output_contract exactly.",
            "Use the attached source file as authority. Use supplied source-card and course context only to prioritize what matters.",
            "The student has ADD and needs offline, short, dopamine-friendly tasks while reading.",
            "The abridged reader is a legitimate minimum viable reading path, not a failure mode.",
            "The abridged reader must be self-contained enough that the student can do active_reading and consolidation_sheet without opening the original source.",
            "If exact wording matters, place one sentence-level original passage directly inside the abridged reader section instead of sending the student back to the PDF.",
            "The output must be a coherent printout kit, not one overloaded everything sheet.",
            "Do not invent creative document titles; use the canonical English artifact titles from the contract.",
            "Make every task operational: it should tell the student what to do, where to look, and when to stop.",
            "Do not reveal answers in active-reading or consolidation tasks.",
            "reading_guide is an appetizer, not an overview sheet: render it as a short coherent teaser text that sets up unresolved problems and makes the learner want to read on.",
            "The rendered reading guide must not look like a worksheet: no standalone fill-out questions, no answer lines, no excerpt-by-excerpt list rhythm.",
            "Keep metatext and workflow language minimal across all printouts; avoid labels like how-to-use, role descriptions, stop signals, and explicit helper scaffolding in the rendered feel.",
            "Never put the answer inside parentheses in answer_shape, locations, done_signal, or stop_signal.",
            "answer_shape must describe only the answer format, e.g. '1 ord', '2 ord', 'et navn', or 'en kort sætning'. Do not add semantic hints.",
            "A done_signal should say when to stop, for example 'når du har skrevet gruppen', not what the group is.",
            "Do not make broad essay prompts, vague blanks, or questions that can be answered without reading the source.",
            "Respect copyright: use quote_anchors only as short search phrases. Visible quoted wording belongs in source_passages; prefer complete sentence-level excerpts and mark omitted beginnings or endings with (...).",
            "Quote anchors and quote targets must be max 12 words and max 140 characters.",
            "Abridged-reader prose should mostly be rewritten explanation, with occasional sentence-level source passages only when exact wording improves the explanation.",
            "Do not put worksheet blanks, mini-quizzes, or checkboxes inside abridged_reader.",
            "active_reading is a guided-solve sheet with abridged_reader open; consolidation_sheet is the memory-first recall sheet after that.",
            "Their location hints must point back into abridged_reader sections.",
            "Prefer concrete Danish wording and avoid generic study-skills language.",
            "Use a serious, practical university-student tone. Avoid hype, motivational language, and childish metaphors.",
        ]
    )


def printout_user_prompt(
    *,
    source: dict[str, Any],
    source_card: dict[str, Any],
    lecture_context: dict[str, Any] | None,
    course_context: dict[str, Any] | None,
    length_budget: dict[str, Any] | None = None,
) -> str:
    budget = length_budget or build_printout_length_budget(source=source, source_card=source_card)
    payload = {
        "source_metadata": source,
        "source_card": _compact_source_card(source_card),
        "lecture_context": lecture_context,
        "course_context": course_context,
        "length_budget": budget,
        "output_contract": scaffold_prompt_contract(budget),
        "required_outputs": {
            "reading_guide": [
                "A one-page teaser printout in Danish.",
                f"Write {_budget_range_text(budget['reading_guide']['teaser_paragraphs'])} coherent teaser paragraphs that read like a continuous text, not a list, outline, or worksheet.",
                "Weave in 2-4 short original phrases or sentence fragments from the text where they sharpen the tension, but do not render the sheet as excerpt-plus-question blocks.",
                "Set up unresolved problems that the learner should carry into the reading, but do it inside the prose rather than as standalone fill-out questions.",
                f"List {_budget_range_text(budget['reading_guide']['subproblems'])} subproblems that break the main problem into concrete answerable parts.",
                "Keep the explicit framing light. Avoid administrative-feeling labels and do not let the sheet read like an overview outline.",
                "Explain why this text matters for the lecture/course in the underlying data, but do not make the rendered feel depend on long setup text.",
                "Include a chronological reading route with concrete stop signals.",
                "Include exactly 3-4 short quote targets or short phrases the student should look for.",
                "Include 2-5 things the student should not get stuck on.",
            ],
            "abridged_reader": [
                "An ADHD-friendly shortened reading path, in Danish, that can serve as the student's minimum viable reading.",
                "Preserve the source's argument movement in source order.",
                "Each section should name the local problem it solves and which reading-guide subproblem it advances.",
                "Use short paragraphs, section headings, page/source anchors, and bullets where helpful.",
                "Mostly rewrite and explain; include at most one visible source_passage in a section when exact wording matters. quote_anchors are search metadata, not standalone visible citations.",
                "Every section must include source_location, explanation_paragraphs, key_points, quote_anchors or no_quote_anchor_needed, source_passages, solves_subproblem, and local_problem.",
                "Do not include blanks, checkboxes, mini-tests, or other fill-out tasks inside abridged_reader.",
                "The reader must be self-contained enough that the student can do active_reading, consolidation_sheet, and exam_bridge without opening the full source.",
            ],
            "active_reading": [
                "Do not spend generation effort on final solve-step formatting.",
                "The engine derives the final active_reading sheet deterministically from reading_guide and abridged_reader.",
                "If you include active_reading content at all, treat it as optional hints only and keep it aligned with abridged_reader subproblems.",
                "The final sheet should feel like open-book guided problem-solving rather than recall from memory.",
            ],
            "consolidation_sheet": [
                "Include instructions that explicitly tell the student to do the sheet from memory first and only check the abridged reader afterward.",
                "Three-sentence overview of what the text is about; do not put blanks in this overview.",
                f"{_budget_range_text(budget['consolidation_sheet']['fill_in_sentences'])} fill-in-the-blank sentences where one key term, distinction, result, or connection is removed.",
                "Each blank must be narrow enough that the intended answer is findable in abridged_reader.",
                "Each fill-in sentence may include where_to_look as a hint, but the engine will normalize references back to abridged_reader sections.",
                f"{_budget_range_text(budget['consolidation_sheet']['diagram_tasks'])} blank diagram tasks; describe what to draw but do not draw it.",
                "Each diagram task must be completable from abridged_reader alone and must list required_elements.",
                "Do not refer to original figures, source pages, or the original PDF inside the tasks.",
                "Keep the work narrower than active_reading: this is memory-first retrieval and repair, not guided problem-solving.",
                "Leave all answer fields blank and do not explain answers.",
            ],
            "exam_bridge": [
                "A transfer worksheet, in Danish, that makes the reading usable for exam answers.",
                "Include where this source is useful, course connections, comparison targets, exam moves, misunderstanding traps, and a mini exam prompt.",
                "Use concrete course language and avoid generic exam-advice filler.",
                "Keep it cue-based and oral-friendly: shorter prompts, shorter cautions, less essay-like explanation.",
                "Do not include a full model answer.",
            ],
        },
    }
    return (
        "Generate printable printout outputs for the attached source file.\n"
        "Use Danish for student-facing text.\n"
        "Here is the source/context payload:\n\n"
        f"{json.dumps(payload, indent=2, ensure_ascii=False)}"
    )


def problem_driven_system_instruction() -> str:
    return "\n".join(
        [
            printout_system_instruction(),
            "This run is an experimental prompt overlay.",
            "Keep the schema-v3 shape and validation contract unchanged.",
            "Let the user-prompt variant instructions change the pedagogical feel, not the artifact structure.",
        ]
    )


def problem_driven_user_prompt(
    *,
    variant_prompt_text: str,
    source: dict[str, Any],
    source_card: dict[str, Any],
    lecture_context: dict[str, Any] | None,
    course_context: dict[str, Any] | None,
    length_budget: dict[str, Any] | None = None,
    variant_key: str = PROBLEM_DRIVEN_VARIANT_KEY,
) -> str:
    base_prompt = printout_user_prompt(
        source=source,
        source_card=source_card,
        lecture_context=lecture_context,
        course_context=course_context,
        length_budget=length_budget,
    )
    return "\n\n".join(
        [
            "This is an experimental printout-review run.",
            f"Variant key: {variant_key}",
            "Apply the following variant instructions while keeping the same JSON contract and required keys.",
            variant_prompt_text.strip(),
            base_prompt,
        ]
    )


def problem_driven_user_prompt_builder(
    *,
    variant_prompt_text: str,
    variant_key: str = PROBLEM_DRIVEN_VARIANT_KEY,
) -> UserPromptBuilder:
    def builder(
        *,
        source: dict[str, Any],
        source_card: dict[str, Any],
        lecture_context: dict[str, Any] | None,
        course_context: dict[str, Any] | None,
        length_budget: dict[str, Any] | None = None,
    ) -> str:
        return problem_driven_user_prompt(
            variant_prompt_text=variant_prompt_text,
            variant_key=variant_key,
            source=source,
            source_card=source_card,
            lecture_context=lecture_context,
            course_context=course_context,
            length_budget=length_budget,
        )

    return builder


def read_problem_driven_variant_prompt(repo_root: Path) -> str:
    return (repo_root / PROBLEM_DRIVEN_VARIANT_PROMPT_PATH).read_text(encoding="utf-8")


def problem_driven_variant_metadata(
    *,
    mode: str,
    render_completion_markers: bool,
    render_exam_bridge: bool,
) -> dict[str, Any]:
    return {
        "mode": mode,
        "variant_key": PROBLEM_DRIVEN_VARIANT_KEY,
        "render_completion_markers": bool(render_completion_markers),
        "render_exam_bridge": bool(render_exam_bridge),
        "variant_prompt_path": str(PROBLEM_DRIVEN_VARIANT_PROMPT_PATH),
        "design_doc": PROBLEM_DRIVEN_DESIGN_DOC,
        "workspace": PROBLEM_DRIVEN_WORKSPACE,
    }


def _coerce_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _looks_like_answer_leak(text: str, *, forbid_parentheses: bool = False) -> bool:
    lowered = text.lower()
    if forbid_parentheses and ("(" in text or ")" in text):
        return True
    return (
        "svaret er" in lowered
        or "answer is" in lowered
        or "fx:" in lowered
        or "f.eks.:" in lowered
    )


def _blank_count(text: str) -> int:
    return len(re.findall(r"_{3,}", text))


def _require_text(value: Any, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise PrintoutError(f"scaffold field must not be empty: {field_name}")
    return text


def _reject_broad_prompt(text: str, field_name: str) -> None:
    lowered = text.lower()
    broad_patterns = (
        r"^\s*(diskuter|reflekter|perspektiver|vurder|sammenlign)\b",
        r"^\s*analyser\s+hvordan\b",
        r"\bhvad\s+mener\s+du\b",
        r"\btag\s+stilling\b",
        r"\bovervej\b",
    )
    if any(re.search(pattern, lowered) for pattern in broad_patterns):
        raise PrintoutError(f"{field_name} is too broad for a reading micro-task")


def _require_safe_task_hint(value: Any, field_name: str, *, forbid_parentheses: bool = False) -> str:
    text = _require_text(value, field_name)
    if _looks_like_answer_leak(text, forbid_parentheses=forbid_parentheses):
        raise PrintoutError(f"{field_name} must not reveal the answer")
    return text


def _require_answer_shape(value: Any, field_name: str) -> str:
    text = _require_safe_task_hint(value, field_name)
    if len(text) > 80:
        raise PrintoutError(f"{field_name} must describe answer format only")
    lowered = text.lower()
    semantic_hint_patterns = (
        r"\bder\b",
        r"\bsom\b",
        r"\bom\b",
        r"\bbeskriver\b",
        r"\bforklarer\b",
        r"\bhentet\s+fra\b",
        r"\bhandler\s+om\b",
        r"\binden\s+for\b",
    )
    if any(re.search(pattern, lowered) for pattern in semantic_hint_patterns):
        raise PrintoutError(f"{field_name} must describe answer format only")
    if re.search(r"\bfor\b", lowered):
        raise PrintoutError(f"{field_name} must describe answer format only")
    return text


def _normalize_answer_shape(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return text
    text = re.sub(r"\([^)]*\)", "", text).strip()
    text = re.sub(r"\([^)]*$", "", text).strip()
    text = re.sub(r"\s+(der|som|om)\b.*$", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"\s+inden\s+for\b.*$", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"\s+hentet\s+fra\b.*$", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"\s+handler\s+om\b.*$", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"\s+for\b.*$", "", text, flags=re.IGNORECASE).strip()
    text = text.rstrip(" .;:")
    return text if text else str(value or "").strip()


def _normalize_quote_anchor(value: Any, *, max_words: int = 12, max_chars: int = 140) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text:
        return text
    words = text.split()
    if len(words) > max_words:
        text = " ".join(words[:max_words])
    if len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0].strip() or text[:max_chars].strip()
    return text.strip(" .,;:")


def _normalize_question_text(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text or text.endswith("?"):
        return text
    return text.rstrip(" .;:!") + "?"


def _normalize_stop_signal(value: Any, *, fallback: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"\[[^\]]*\]", "", text)
    text = re.sub(r"\s+", " ", text).strip(" .;:")
    return text or fallback


def _normalize_source_passage_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _normalize_teaser_paragraph_text(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    text = re.sub(r"^[-*]\s+", "", text)
    return text


def _legacy_teaser_paragraphs(
    opening_passages: list[dict[str, Any]],
    *,
    main_problem: str,
    overview: list[Any],
) -> list[str]:
    fragments: list[tuple[str, str]] = []
    for item in opening_passages[:6]:
        excerpt = _normalize_source_passage_text(item.get("excerpt"))
        question = _normalize_question_text(item.get("open_question"))
        if excerpt or question:
            fragments.append((excerpt, question))
    teaser_paragraphs: list[str] = []
    if fragments:
        first_excerpt, first_question = fragments[0]
        second_excerpt, second_question = fragments[1] if len(fragments) > 1 else ("", "")
        if first_excerpt:
            paragraph = f'"{first_excerpt}"'
            if first_question:
                paragraph += f" Allerede her bliver det uklart, {first_question.rstrip('?').lower()}."
            if second_excerpt:
                paragraph += f' Når teksten samtidig spørger "{second_excerpt}"'
                if second_question:
                    paragraph += f", skærpes problemet yderligere: {second_question.rstrip('?').lower()}."
                else:
                    paragraph += "."
            teaser_paragraphs.append(paragraph.strip())
        remaining = fragments[2:] if len(fragments) > 2 else []
        if remaining:
            parts: list[str] = []
            for excerpt, question in remaining:
                if excerpt:
                    sentence = f'Senere bliver spændingen endnu tydeligere i formuleringen "{excerpt}"'
                    if question:
                        sentence += f", fordi den tvinger læseren til at afgøre, {question.rstrip('?').lower()}."
                    else:
                        sentence += "."
                    parts.append(sentence)
            if parts:
                teaser_paragraphs.append(" ".join(parts).strip())
    if teaser_paragraphs:
        return teaser_paragraphs[:6]
    fallback = str(main_problem or "").strip()
    overview_paragraphs = [str(item).strip() for item in overview if str(item).strip()]
    if fallback:
        return ([fallback] + overview_paragraphs)[:6]
    return overview_paragraphs[:6]


def _question_stem(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip()).rstrip("?").strip()


def _answer_shape_is_short(answer_shape: str) -> bool:
    lowered = answer_shape.casefold()
    if any(
        term in lowered
        for term in ("sætning", "sætninger", "linjer", "afsnit", "paragraf", "forklaring", "kontrast", "skel")
    ):
        return False
    return any(
        term in lowered
        for term in ("ord", "navn", "tal", "ja/nej", "ja eller nej", "begreb", "nøgleord")
    )


def _answer_shape_prefers_compact_paragraph(answer_shape: str) -> bool:
    lowered = answer_shape.casefold()
    if any(
        term in lowered
        for term in (
            "1-2 sæt",
            "1–2 sæt",
            "kort kontrast",
            "kort forklaring",
            "kort skriftlig forklaring",
            "kort begrebsforklaring",
            "begrebsforklaring",
            "kort svar",
            "kort begrundelse",
            "kort sammenligning",
            "kort beskrivelse",
            "kontrast mellem",
            "oversigt",
            "akse",
            "akser",
            "betingelse",
            "betingelser",
        )
    ):
        return True
    return bool(re.search(r"\b(to|tre|fire|fem)\b", lowered))


def _looks_like_decision_question(question: str) -> bool:
    lowered = question.casefold().strip()
    return lowered.startswith(
        (
            "er ",
            "kan ",
            "skal ",
            "bør ",
            "mener ",
            "påvirker ",
            "beskytter ",
            "repræsenterer ",
        )
    ) or "ja/nej" in lowered


def _looks_like_term_question(question: str) -> bool:
    lowered = question.casefold().strip()
    if lowered.startswith("hvilke "):
        return any(
            token in lowered
            for token in ("begreb", "begreber", "ord", "navn", "navne", "punkt", "punkter", "tema", "temaer")
        )
    return lowered.startswith(
        (
            "hvilket ",
            "hvilken ",
            "hvad kaldes",
            "hvad hedder",
            "hvor mange",
            "hvem ",
        )
    )


def _subproblem_answer_form_map(guide: dict[str, Any]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for index, item in enumerate(_coerce_list(guide.get("subproblems")), start=1):
        if not isinstance(item, dict):
            continue
        key = _canonical_subproblem_ref(item.get("number"), fallback=index).casefold()
        answer_form = _normalize_answer_shape(item.get("answer_form"))
        if answer_form:
            mapping[key] = answer_form
    return mapping


def _subproblem_question_map(guide: dict[str, Any]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for index, item in enumerate(_coerce_list(guide.get("subproblems")), start=1):
        if not isinstance(item, dict):
            continue
        key = _canonical_subproblem_ref(item.get("number"), fallback=index).casefold()
        question = _normalize_question_text(item.get("question"))
        if question:
            mapping[key] = question
    return mapping


def _canonical_subproblem_ref(value: Any, *, fallback: int) -> str:
    text = str(value or "").strip()
    if not text:
        return f"Delproblem {fallback}"
    if re.fullmatch(r"\d+", text):
        return f"Delproblem {text}"
    lowered = text.casefold()
    if lowered.startswith("delproblem"):
        suffix = text.split(" ", 1)[1].strip() if " " in text else str(fallback)
        return f"Delproblem {suffix}"
    return text


def _section_location_label(section: dict[str, Any]) -> str:
    number = str(section.get("number") or "").strip()
    return f"Abridged reader sektion {number or '1'}"


def _term_prompt_for_question(question: str) -> str:
    lowered = question.casefold()
    if "lejr" in lowered:
        return f"Skriv lejrnavnet, som sektionen peger på: {question}"
    if "punkt" in lowered:
        return f"Skriv orienteringspunktet, som sektionen peger på: {question}"
    if lowered.startswith(("hvad er ", "hvad er det ", "hvad betyder ", "hvilket begreb", "hvilken term")):
        return f"Skriv begrebet, som besvarer spørgsmålet: {question}"
    if "begreb" in lowered:
        return f"Skriv begrebet, som besvarer spørgsmålet: {question}"
    if "begivenhed" in lowered:
        return f"Skriv den konkrete begivenhed, som sektionen fremhæver: {question}"
    if "tidsramme" in lowered:
        return f"Skriv den tidsramme, som sektionen ender med: {question}"
    if lowered.startswith("hvem "):
        return f"Skriv navnet, som besvarer spørgsmålet: {question}"
    return f"Skriv det korte svar på spørgsmålet: {question}"


def _decision_prompt_for_question(question: str) -> str:
    lowered = question.casefold()
    if " eller " in lowered:
        return f"Vælg side i spændingen og begrund kort: {question}"
    return f"Afgør spørgsmålet ud fra sektionen og begrund kort: {question}"


def _paragraph_prompt_for_question(question: str) -> str:
    lowered = question.casefold()
    if lowered.startswith(("hvordan ", "hvorfor ", "hvor er ", "på hvilken måde ")):
        return f"Forklar kort, hvordan sektionen besvarer dette: {question}"
    return f"Skriv et kort, sammenhængende svar på dette: {question}"


def _looks_like_question_stem(text: str) -> bool:
    lowered = text.casefold().strip()
    return lowered.startswith(
        (
            "hvordan ",
            "hvorfor ",
            "hvad ",
            "hvilken ",
            "hvilket ",
            "hvilke ",
            "kan ",
            "skal ",
            "bør ",
            "er ",
            "på hvilken måde ",
        )
    )


def _synthesis_prompt_for_main_problem(main_problem: str) -> str:
    stem = _question_stem(main_problem).rstrip(".").strip()
    if not stem:
        return "Brug dine delsvar til at samle tekstens hovedbevægelse kort."
    if str(main_problem or "").strip().endswith("?") or _looks_like_question_stem(stem):
        return f"Brug dine delsvar til at besvare hovedproblemet kort: {stem}?"
    if stem.casefold().startswith("at "):
        infinitive = stem[3:].strip()
        if infinitive:
            return (
                "Brug dine delsvar til at forklare tekstens hovedbevægelse kort: "
                f"Hvordan hjælper teksten med at {infinitive}?"
            )
    return f"Brug dine delsvar til at samle tekstens hovedbevægelse kort: {stem}."


def _paragraph_blank_lines(answer_shape: str, *, is_synthesis: bool = False) -> int:
    if is_synthesis:
        return 4
    if _answer_shape_prefers_compact_paragraph(answer_shape):
        return 2
    return 3


def _scaled_response_line_count(blank_lines: int) -> int:
    return max(
        1,
        (blank_lines * RESPONSE_LINE_MULTIPLIER_NUMERATOR + RESPONSE_LINE_MULTIPLIER_DENOMINATOR - 1)
        // RESPONSE_LINE_MULTIPLIER_DENOMINATOR,
    )


def _active_step_needspace_baselines(task_type: str, blank_lines: int) -> int:
    rendered_blank_lines = _scaled_response_line_count(blank_lines)
    if task_type == "term":
        return rendered_blank_lines + 4
    if task_type == "decision":
        return rendered_blank_lines + 4
    return rendered_blank_lines + 5


def _rebalance_active_solve_steps(guide: dict[str, Any], reader: dict[str, Any]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    answer_forms = _subproblem_answer_form_map(guide)
    subproblem_questions = _subproblem_question_map(guide)
    sections = [item for item in _coerce_list(reader.get("sections")) if isinstance(item, dict)]
    for index, section in enumerate(sections, start=1):
        ref = _canonical_subproblem_ref(section.get("solves_subproblem"), fallback=index)
        question = _normalize_question_text(section.get("local_problem") or f"Hvad løser sektion {index}")
        guide_question = subproblem_questions.get(ref.casefold(), "")
        if question.casefold().startswith("at ") and guide_question:
            question = guide_question
        answer_shape = answer_forms.get(ref.casefold(), "")
        short_answer_hint = bool(answer_shape and _answer_shape_is_short(answer_shape))
        compact_paragraph_hint = bool(answer_shape and _answer_shape_prefers_compact_paragraph(answer_shape))
        if _looks_like_decision_question(question):
            task_type = "decision"
            answer_shape = "Ja/Nej + 1 sætning"
            prompt = _decision_prompt_for_question(question)
            blank_lines = 2
            done_signal = "Stop når du har valgt og skrevet en kort begrundelse"
        elif _looks_like_term_question(question) or short_answer_hint:
            task_type = "term"
            answer_shape = answer_shape or "1-3 ord"
            prompt = _term_prompt_for_question(question)
            blank_lines = 1
            done_signal = "Stop når du har skrevet det centrale begreb"
        else:
            task_type = "short_paragraph"
            answer_shape = answer_shape or ("1-2 sætninger" if compact_paragraph_hint else "2-4 sætninger")
            prompt = _paragraph_prompt_for_question(question)
            blank_lines = _paragraph_blank_lines(answer_shape)
            done_signal = "Stop når du har skrevet et kort, sammenhængende svar"
        steps.append(
            {
                "number": str(len(steps) + 1),
                "subproblem_ref": ref,
                "prompt": prompt,
                "task_type": task_type,
                "abridged_reader_location": _section_location_label(section),
                "answer_shape": answer_shape,
                "blank_lines": blank_lines,
                "done_signal": done_signal,
            }
        )
    main_problem = _question_stem(guide.get("main_problem"))
    if main_problem:
        end_number = str(len(sections))
        steps.append(
            {
                "number": str(len(steps) + 1),
                "subproblem_ref": "Hovedproblem",
                "prompt": _synthesis_prompt_for_main_problem(str(guide.get("main_problem") or "")),
                "task_type": "short_paragraph",
                "abridged_reader_location": (
                    f"Abridged reader sektion 1-{end_number}" if end_number and end_number != "1" else "Abridged reader sektion 1"
                ),
                "answer_shape": "4-5 sætninger",
                "blank_lines": _paragraph_blank_lines("4-5 sætninger", is_synthesis=True),
                "done_signal": "Stop når du har skrevet et samlet svar med tekstens vigtigste bevægelser",
            }
        )
    return steps[:8]


def _active_solve_steps_need_rebalance(steps: list[dict[str, Any]]) -> bool:
    if not steps:
        return True
    paragraph_steps = 0
    for item in steps:
        prompt = _normalize_open_prompt(item.get("prompt"))
        answer_shape = _normalize_answer_shape(item.get("answer_shape"))
        task_type = _normalize_task_type(item.get("task_type"), prompt=prompt, answer_shape=answer_shape)
        if task_type == "short_paragraph":
            paragraph_steps += 1
        location = str(item.get("abridged_reader_location") or "").strip()
        if not prompt or not answer_shape or not location:
            return True
        if _looks_like_source_page_reference(location):
            return True
        if task_type not in {"term", "decision", "short_paragraph"}:
            return True
        try:
            _reject_broad_prompt(prompt, "active-reading solve step")
        except PrintoutError:
            return True
    return paragraph_steps < 1


def _derive_active_reading_payload(guide: dict[str, Any], reader: dict[str, Any], *, max_steps: int) -> dict[str, Any]:
    solve_steps = _rebalance_active_solve_steps(guide, reader)[:max_steps]
    return {
        "title": V3_FIXED_TITLES["active_reading"],
        "instructions": (
            "Hold abridged reader åben. Løs delproblemerne et trin ad gangen, og skriv kun det, der er nødvendigt for at få svaret på plads."
        ),
        "solve_steps": solve_steps,
    }


def _rewrite_diagram_task_for_abridged_only(task: Any, required_elements: list[str]) -> str:
    text = re.sub(r"\s+", " ", str(task or "").strip())
    if not _looks_like_source_page_reference(text) and not re.search(r"\bfigur\b", text, flags=re.IGNORECASE):
        return text
    if required_elements:
        return "Genskab modellen fra hukommelsen og placer elementerne i korrekt forhold."
    return "Genskab tekstens model fra hukommelsen."


def _looks_like_source_page_reference(text: str) -> bool:
    lowered = text.casefold()
    if re.search(r"\b(?:s|side|sid[e]?r|p|pp|page|pages)\.?\s*\d", lowered):
        return True
    return any(term in lowered for term in ("originalteksten", "originalen", "pdf", "kildeteksten"))


def _require_abridged_reference(value: Any, field_name: str) -> str:
    text = _require_text(value, field_name)
    lowered = text.casefold()
    if _looks_like_source_page_reference(text):
        raise PrintoutError(f"{field_name} must point to abridged_reader, not the original source")
    if not any(hint in lowered for hint in ("abridged", "læsespor", "sektion", "del")):
        raise PrintoutError(f"{field_name} must point to abridged_reader sections")
    return text


def _looks_like_abridged_reference(value: Any) -> bool:
    text = str(value or "").strip()
    if not text or _looks_like_source_page_reference(text):
        return False
    lowered = text.casefold()
    return any(hint in lowered for hint in ("abridged", "læsespor", "sektion", "del"))


def _normalize_open_prompt(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _infer_task_type(*, prompt: Any, answer_shape: Any) -> str:
    prompt_text = str(prompt or "").casefold()
    answer_text = str(answer_shape or "").casefold()
    if any(term in prompt_text for term in ("vælg", "afgør", "beslut", "tag stilling", "enten", "ja eller nej")):
        return "decision"
    if any(term in answer_text for term in ("sætning", "sætninger", "linjer", "afsnit", "paragraf")):
        return "short_paragraph"
    if any(term in prompt_text for term in ("skriv", "forklar", "vis med", "brug 3", "brug tre")):
        return "short_paragraph"
    return "term"


def _normalize_task_type(value: Any, *, prompt: Any, answer_shape: Any) -> str:
    text = re.sub(r"\s+", "_", str(value or "").strip().casefold().replace("-", "_"))
    if not text:
        return _infer_task_type(prompt=prompt, answer_shape=answer_shape)
    aliases = {
        "kort_svar": "term",
        "ord": "term",
        "term": "term",
        "begreb": "term",
        "decision": "decision",
        "valg": "decision",
        "kort_beslutning": "decision",
        "short_paragraph": "short_paragraph",
        "paragraph": "short_paragraph",
        "paragraf": "short_paragraph",
        "kort_paragraf": "short_paragraph",
    }
    normalized = aliases.get(text, text)
    if normalized not in {"term", "decision", "short_paragraph"}:
        return _infer_task_type(prompt=prompt, answer_shape=answer_shape)
    return normalized


def _require_task_type(value: Any, field_name: str) -> str:
    text = _require_text(value, field_name).casefold().replace("-", "_").replace(" ", "_")
    if text not in {"term", "decision", "short_paragraph"}:
        raise PrintoutError(f"{field_name} must be one of: term, decision, short_paragraph")
    return text


def _normalize_blank_lines(value: Any, *, task_type: str, answer_shape: Any) -> int:
    default = 4 if task_type == "short_paragraph" else 1
    if isinstance(value, bool):
        return default
    try:
        blank_lines = int(value)
    except (TypeError, ValueError):
        text = str(answer_shape or "").casefold()
        if task_type == "short_paragraph" and re.search(r"\b([3-6])\s*-\s*([3-6])\b", text):
            blank_lines = 4
        else:
            blank_lines = default
    minimum, maximum = (2, 6) if task_type == "short_paragraph" else (1, 2)
    return max(minimum, min(maximum, blank_lines))


def _require_blank_lines(value: Any, field_name: str, *, task_type: str) -> int:
    if isinstance(value, bool):
        raise PrintoutError(f"{field_name} must be an integer")
    try:
        blank_lines = int(value)
    except (TypeError, ValueError) as exc:
        raise PrintoutError(f"{field_name} must be an integer") from exc
    minimum, maximum = (2, 6) if task_type == "short_paragraph" else (1, 2)
    if not minimum <= blank_lines <= maximum:
        raise PrintoutError(f"{field_name} must be {minimum}-{maximum} for task_type={task_type}")
    return blank_lines


def _split_required_element_text(value: str) -> list[str]:
    text = re.sub(r"\s+", " ", value.strip())
    if not text:
        return []
    text = re.sub(r"^[\s:.-]*(fx|f\.eks\.|elementer|begreber)\s*[:.-]\s*", "", text, flags=re.IGNORECASE)
    parts = re.split(r"\s*(?:,|;|/|→|->|\bog\b|\bsamt\b|\bvs\.?\b|\bversus\b)\s*", text, flags=re.IGNORECASE)
    return [part.strip(" .:;()[]") for part in parts if part.strip(" .:;()[]")]


def _clean_required_element_text(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if text.count("(") > text.count(")"):
        text = text.replace("(", ": ")
    if text.count(")") > text.count("("):
        text = text.replace(")", "")
    text = text.replace(" :", ":")
    text = re.sub(r":\s*:", ":", text)
    return text.strip(" .:;[]")


def _short_required_element_fragment(text: str) -> bool:
    return 1 <= _word_count(text) <= 3 and len(text) <= 36


def _should_merge_required_element_fragment(previous: str, current: str) -> bool:
    previous_lower = previous.casefold().strip()
    current_lower = current.casefold().strip()
    if previous_lower in {"pile", "pile,", "pile:"} and current_lower.startswith("der "):
        return True
    if current_lower.startswith("pile"):
        return False
    if previous_lower.endswith((" med", " uden", " og", " der viser")):
        return True
    if ":" not in previous or not _short_required_element_fragment(current):
        return False
    merge_prefixes = (
        "2 rækker",
        "3 kolonner",
        "akser",
        "de tre",
        "de fire",
        "deres",
        "det midterste",
        "det nederste",
        "det øverste",
        "en boks",
        "en fordelingskurve",
        "en markering",
        "en x-akse",
        "en y-akse",
        "navnet",
        "række ",
        "to elementer",
        "to kolonner",
    )
    return previous_lower.startswith(merge_prefixes)


def _split_embedded_required_elements(items: list[str]) -> list[str]:
    split_items: list[str] = []
    for item in items:
        match = re.search(r",\s+(Pile(?:\s+der\b.*)?)$", item)
        if match:
            prefix = item[: match.start()].strip(" ,")
            suffix = match.group(1).strip()
            if prefix:
                split_items.append(prefix)
            if suffix:
                split_items.append(suffix)
            continue
        split_items.append(item)
    return split_items


def _repair_required_element_fragments(items: list[str]) -> list[str]:
    repaired: list[str] = []
    for item in items:
        text = _clean_required_element_text(item)
        if not text:
            continue
        if repaired and _should_merge_required_element_fragment(repaired[-1], text):
            separator = " " if repaired[-1].casefold().strip() == "pile" else ", "
            repaired[-1] = f"{repaired[-1]}{separator}{text}".strip()
            continue
        repaired.append(text)
    return _split_embedded_required_elements(repaired)


def _extract_required_elements_from_task(task: Any) -> list[str]:
    text = re.sub(r"\s+", " ", str(task or "").strip())
    if not text:
        return []
    quoted = re.findall(r"['\"“”‘’]([^'\"“”‘’]{2,60})['\"“”‘’]", text)
    elements: list[str] = []
    for item in quoted:
        elements.extend(_split_required_element_text(item))
    if elements:
        return elements
    match = re.search(r"\bmellem\s+(.+?)(?:\.|$)", text, flags=re.IGNORECASE)
    if match:
        elements.extend(_split_required_element_text(match.group(1)))
    match = re.search(r"\b(?:forholdet|relationen)\s+(.+?)(?:\.|$)", text, flags=re.IGNORECASE)
    if match:
        elements.extend(_split_required_element_text(match.group(1)))
    return elements


def _normalize_required_elements(value: Any, *, task: Any) -> list[str]:
    elements: list[str] = []
    if isinstance(value, list):
        raw_items: list[str] = []
        for item in value:
            if isinstance(item, dict):
                text = str(item.get("term") or item.get("name") or item.get("label") or "").strip()
            else:
                text = str(item or "").strip()
            if text:
                raw_items.append(text)
        if len(raw_items) == 1:
            elements.extend(_split_required_element_text(raw_items[0]) or [_clean_required_element_text(raw_items[0])])
        else:
            elements.extend(_repair_required_element_fragments(raw_items))
    elif isinstance(value, str):
        elements.extend(_split_required_element_text(value))
    if len(elements) < 2:
        elements.extend(_extract_required_elements_from_task(task))
    unique: list[str] = []
    seen: set[str] = set()
    for element in elements:
        cleaned = re.sub(r"\s+", " ", str(element or "").strip(" .:;()[]"))
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(cleaned)
    return unique[:6]


def _ensure_minimum_required_elements(task: Any, elements: list[str]) -> list[str]:
    if len(elements) >= 2:
        return elements
    task_text = re.sub(r"\s+", " ", str(task or "").strip()).casefold()
    fallbacks: list[str]
    if "matrix" in task_text or "2x3" in task_text or "2 × 3" in task_text:
        fallbacks = ["akser", "felter"]
    elif "model" in task_text:
        fallbacks = ["centrale elementer", "relationer"]
    elif "diagram" in task_text or "tegn" in task_text:
        fallbacks = ["elementer", "relationer"]
    else:
        fallbacks = ["noder", "relationer"]
    merged = list(elements)
    for item in fallbacks:
        if len(merged) >= 2:
            break
        if item.casefold() not in {existing.casefold() for existing in merged}:
            merged.append(item)
    return merged[:6]


def _normalize_exam_moves(value: Any) -> list[dict[str, str]]:
    moves = [dict(item) for item in _coerce_list(value) if isinstance(item, dict)]
    defaults = [
        {
            "prompt_type": "definer",
            "use_in_answer": "Brug teksten til at definere dens centrale begreb eller position præcist.",
            "caution": "Hold definitionen knyttet til teksten, ikke til en løs hverdagsforståelse.",
        },
        {
            "prompt_type": "sammenlign",
            "use_in_answer": "Brug teksten som kontrast til en anden tilgang fra kurset.",
            "caution": "Undgå karikatur; sammenlign på antagelser, metode eller menneskesyn.",
        },
        {
            "prompt_type": "diskuter",
            "use_in_answer": "Brug teksten til at nuancere styrker, begrænsninger eller anvendelse.",
            "caution": "Skriv ikke et generelt essay; bind diskussionen til tekstens konkrete pointe.",
        },
    ]
    existing = {str(item.get("prompt_type") or "").strip().casefold() for item in moves}
    for default in defaults:
        if len(moves) >= 3:
            break
        if default["prompt_type"].casefold() not in existing:
            moves.append(default)
            existing.add(default["prompt_type"].casefold())
    return moves[:6]


def normalize_v2_scaffold_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(payload)
    tests = normalized.get("unit_test_suite") if isinstance(normalized.get("unit_test_suite"), dict) else {}
    for item in _coerce_list(tests.get("questions")):
        if isinstance(item, dict) and "answer_shape" in item:
            item["answer_shape"] = _normalize_answer_shape(item.get("answer_shape"))
    cloze = normalized.get("cloze_scaffold") if isinstance(normalized.get("cloze_scaffold"), dict) else {}
    for item in _coerce_list(cloze.get("fill_in_sentences")):
        if isinstance(item, dict) and "answer_shape" in item:
            item["answer_shape"] = _normalize_answer_shape(item.get("answer_shape"))
    return normalized


def normalize_scaffold_payload(
    payload: dict[str, Any],
    *,
    legacy_compat: bool = False,
    length_budget: dict[str, Any] | None = None,
) -> dict[str, Any]:
    budget = length_budget or build_printout_length_budget()
    normalized = deepcopy(payload)
    guide = normalized.get("reading_guide") if isinstance(normalized.get("reading_guide"), dict) else {}
    if isinstance(guide, dict):
        guide["title"] = V3_FIXED_TITLES["reading_guide"]
        if legacy_compat and ("main_problem" not in guide or not str(guide.get("main_problem") or "").strip()):
            fallback_problem = str(guide.get("why_this_text_matters") or "").strip()
            if not fallback_problem:
                fallback_problem = str((_coerce_list(guide.get("overview")) or [""])[0]).strip()
            guide["main_problem"] = fallback_problem
        subproblems = [dict(item) for item in _coerce_list(guide.get("subproblems")) if isinstance(item, dict)]
        if legacy_compat and not subproblems:
            for index, item in enumerate(_coerce_list(guide.get("reading_route")), start=1):
                if not isinstance(item, dict):
                    continue
                subproblems.append(
                    {
                        "number": str(item.get("number") or index),
                        "question": _normalize_question_text(item.get("task")),
                        "why_it_matters": str(item.get("why_it_matters") or "").strip()
                        or "Det hjælper dig med at løse hovedproblemet.",
                        "answer_form": "en kort sætning",
                    }
                )
                if len(subproblems) >= _budget_max(budget, "reading_guide", "subproblems"):
                    break
        guide["subproblems"] = subproblems[: _budget_max(budget, "reading_guide", "subproblems")]
        opening_passages = [
            dict(item) for item in _coerce_list(guide.get("opening_passages")) if isinstance(item, dict)
        ]
        quote_targets = [dict(item) for item in _coerce_list(guide.get("key_quote_targets")) if isinstance(item, dict)]
        if legacy_compat and not opening_passages:
            for index, item in enumerate(quote_targets, start=1):
                question = ""
                if index <= len(subproblems) and isinstance(subproblems[index - 1], dict):
                    question = str(subproblems[index - 1].get("question") or "").strip()
                opening_passages.append(
                    {
                        "number": str(index),
                        "source_location": str(item.get("where_to_look") or "").strip() or f"Side {index}",
                        "excerpt": str(item.get("target") or "").strip(),
                        "open_question": _normalize_question_text(question or f"Hvad bliver det afgørende spørgsmål i {str(item.get('target') or 'denne passage').strip()}"),
                    }
                )
                if len(opening_passages) >= _budget_max(budget, "reading_guide", "opening_passages"):
                    break
        minimum_opening_passages = _budget_min(budget, "reading_guide", "opening_passages")
        if 0 < len(opening_passages) < minimum_opening_passages:
            seen_locations = {
                (
                    str(item.get("source_location") or "").strip().casefold(),
                    str(item.get("excerpt") or "").strip().casefold(),
                )
                for item in opening_passages
                if isinstance(item, dict)
            }
            next_number = len(opening_passages) + 1
            for item in quote_targets:
                if len(opening_passages) >= minimum_opening_passages:
                    break
                location = str(item.get("where_to_look") or "").strip() or f"Side {next_number}"
                excerpt = str(item.get("target") or "").strip()
                key = (location.casefold(), excerpt.casefold())
                if not excerpt or key in seen_locations:
                    continue
                question = ""
                if next_number <= len(subproblems) and isinstance(subproblems[next_number - 1], dict):
                    question = str(subproblems[next_number - 1].get("question") or "").strip()
                opening_passages.append(
                    {
                        "number": str(next_number),
                        "source_location": location,
                        "excerpt": excerpt,
                        "open_question": _normalize_question_text(
                            question or f"Hvad bliver det afgørende spørgsmål i {excerpt}?"
                        ),
                    }
                )
                seen_locations.add(key)
                next_number += 1
        if 0 < len(opening_passages) < minimum_opening_passages:
            opening_passages = []
        guide["opening_passages"] = opening_passages[: _budget_max(budget, "reading_guide", "opening_passages")]
        teaser_paragraphs = [str(item).strip() for item in _coerce_list(guide.get("teaser_paragraphs")) if str(item).strip()]
        if legacy_compat and not teaser_paragraphs:
            teaser_paragraphs = _legacy_teaser_paragraphs(
                opening_passages,
                main_problem=str(guide.get("main_problem") or "").strip(),
                overview=_coerce_list(guide.get("overview")),
            )
        guide["teaser_paragraphs"] = teaser_paragraphs[: _budget_max(budget, "reading_guide", "teaser_paragraphs")]
    for item in _coerce_list(guide.get("subproblems")):
        if isinstance(item, dict):
            if "question" in item:
                item["question"] = _normalize_question_text(item.get("question"))
            if "answer_form" in item:
                item["answer_form"] = _normalize_answer_shape(item.get("answer_form"))
    guide["teaser_paragraphs"] = [
        _normalize_teaser_paragraph_text(item) for item in _coerce_list(guide.get("teaser_paragraphs")) if str(item).strip()
    ][: _budget_max(budget, "reading_guide", "teaser_paragraphs")]
    for item in _coerce_list(guide.get("opening_passages")):
        if isinstance(item, dict):
            if "excerpt" in item:
                item["excerpt"] = _normalize_source_passage_text(item.get("excerpt"))
            if "open_question" in item:
                item["open_question"] = _normalize_question_text(item.get("open_question"))
    for item in _coerce_list(guide.get("key_quote_targets")):
        if isinstance(item, dict) and "target" in item:
            item["target"] = _normalize_quote_anchor(item.get("target"))
    for item in _coerce_list(guide.get("reading_route")):
        if isinstance(item, dict) and "stop_signal" in item:
            item["stop_signal"] = _normalize_stop_signal(
                item.get("stop_signal"),
                fallback="Stop når du har skrevet en kort note",
            )
    guide["reading_route"] = [
        dict(item) for item in _coerce_list(guide.get("reading_route")) if isinstance(item, dict)
    ][: _budget_max(budget, "reading_guide", "reading_route")]
    guide["key_quote_targets"] = [
        dict(item) for item in _coerce_list(guide.get("key_quote_targets")) if isinstance(item, dict)
    ][: _budget_max(budget, "reading_guide", "key_quote_targets")]
    guide["do_not_get_stuck_on"] = [
        str(item).strip() for item in _coerce_list(guide.get("do_not_get_stuck_on")) if str(item).strip()
    ][: _budget_max(budget, "reading_guide", "do_not_get_stuck_on")]
    reader = normalized.get("abridged_reader") if isinstance(normalized.get("abridged_reader"), dict) else {}
    if isinstance(reader, dict):
        reader["title"] = V3_FIXED_TITLES["abridged_reader"]
        reader["sections"] = [
            dict(item) for item in _coerce_list(reader.get("sections")) if isinstance(item, dict)
        ][: _budget_max(budget, "abridged_reader", "sections")]
    subproblem_refs = [
        f"Delproblem {str(item.get('number') or index).strip()}"
        for index, item in enumerate(_coerce_list(guide.get("subproblems")), start=1)
        if isinstance(item, dict)
    ]
    for section_index, section in enumerate(_coerce_list(reader.get("sections")), start=1):
        if not isinstance(section, dict):
            continue
        if legacy_compat and ("solves_subproblem" not in section or not str(section.get("solves_subproblem") or "").strip()):
            fallback_number = str(section.get("number") or section_index).strip() or str(section_index)
            fallback_ref = subproblem_refs[min(len(subproblem_refs), section_index) - 1] if subproblem_refs else f"Delproblem {fallback_number}"
            section["solves_subproblem"] = fallback_ref
        section["solves_subproblem"] = _canonical_subproblem_ref(
            section.get("solves_subproblem"),
            fallback=section_index,
        )
        if legacy_compat and ("local_problem" not in section or not str(section.get("local_problem") or "").strip()):
            section["local_problem"] = _normalize_question_text(
                section.get("mini_check_question") or f"Hvad løser {str(section.get('heading') or 'denne del').strip()}?"
            )
        for anchor in _coerce_list(section.get("quote_anchors")):
            if isinstance(anchor, dict) and "phrase" in anchor:
                anchor["phrase"] = _normalize_quote_anchor(anchor.get("phrase"))
        for passage in _coerce_list(section.get("source_passages")):
            if isinstance(passage, dict) and "passage" in passage:
                passage["passage"] = _normalize_source_passage_text(passage.get("passage"))
        quote_anchors = [item for item in _coerce_list(section.get("quote_anchors")) if isinstance(item, dict)]
        no_quote_needed = str(section.get("no_quote_anchor_needed") or "").strip()
        if not quote_anchors and not no_quote_needed:
            section["no_quote_anchor_needed"] = "Sektionen bæres af forklaringen frem for en kort citerbar formulering."
        if "mini_check_answer_shape" in section:
            section["mini_check_answer_shape"] = _normalize_answer_shape(section.get("mini_check_answer_shape"))
        if "mini_check_question" in section:
            section["mini_check_question"] = _normalize_question_text(section.get("mini_check_question"))
        if "mini_check_done_signal" in section:
            section["mini_check_done_signal"] = _normalize_stop_signal(
                section.get("mini_check_done_signal"),
                fallback="Stop når du har skrevet et kort svar",
            )
        if "local_problem" in section:
            section["local_problem"] = _normalize_question_text(section.get("local_problem"))
    active = _derive_active_reading_payload(
        guide,
        reader,
        max_steps=_budget_max(budget, "active_reading", "solve_steps"),
    )
    normalized["active_reading"] = active
    consolidation = (
        normalized.get("consolidation_sheet")
        if isinstance(normalized.get("consolidation_sheet"), dict)
        else {}
    )
    if isinstance(consolidation, dict):
        consolidation["title"] = V3_FIXED_TITLES["consolidation_sheet"]
    if legacy_compat and isinstance(consolidation, dict) and (
        "instructions" not in consolidation or not str(consolidation.get("instructions") or "").strip()
    ):
        consolidation["instructions"] = (
            "Lav arket uden at kigge først. Brug derefter abridged reader til at tjekke eller reparere dine svar."
        )
    for fill_index, item in enumerate(_coerce_list(consolidation.get("fill_in_sentences")), start=1):
        if isinstance(item, dict) and "answer_shape" in item:
            item["answer_shape"] = _normalize_answer_shape(item.get("answer_shape"))
        if isinstance(item, dict):
            location = str(item.get("where_to_look") or "").strip()
            if not _looks_like_abridged_reference(location):
                fallback_section = min(fill_index, max(1, len(_coerce_list(reader.get("sections")))))
                item["where_to_look"] = f"Abridged reader sektion {fallback_section}."
    consolidation["fill_in_sentences"] = [
        dict(item) for item in _coerce_list(consolidation.get("fill_in_sentences")) if isinstance(item, dict)
    ][: _budget_max(budget, "consolidation_sheet", "fill_in_sentences")]
    for item in _coerce_list(consolidation.get("diagram_tasks")):
        if isinstance(item, dict):
            normalized_required_elements = _normalize_required_elements(
                item.get("required_elements"),
                task=item.get("task"),
            )
            item["task"] = _rewrite_diagram_task_for_abridged_only(
                item.get("task"),
                normalized_required_elements,
            )
            item["required_elements"] = _ensure_minimum_required_elements(
                item.get("task"),
                normalized_required_elements,
            )
    consolidation["diagram_tasks"] = [
        dict(item) for item in _coerce_list(consolidation.get("diagram_tasks")) if isinstance(item, dict)
    ][: _budget_max(budget, "consolidation_sheet", "diagram_tasks")]
    exam_bridge = normalized.get("exam_bridge") if isinstance(normalized.get("exam_bridge"), dict) else {}
    if isinstance(exam_bridge, dict):
        exam_bridge["title"] = V3_FIXED_TITLES["exam_bridge"]
        exam_bridge["exam_moves"] = _normalize_exam_moves(exam_bridge.get("exam_moves"))
        if legacy_compat:
            exam_bridge["use_this_text_for"] = [re.sub(r"\s+", " ", str(item or "").strip()) for item in _coerce_list(exam_bridge.get("use_this_text_for")) if str(item or "").strip()][: _budget_max(budget, "exam_bridge", "use_this_text_for")]
            exam_bridge["course_connections"] = [dict(item) for item in _coerce_list(exam_bridge.get("course_connections")) if isinstance(item, dict)][: _budget_max(budget, "exam_bridge", "course_connections")]
            exam_bridge["comparison_targets"] = [dict(item) for item in _coerce_list(exam_bridge.get("comparison_targets")) if isinstance(item, dict)][: _budget_max(budget, "exam_bridge", "comparison_targets")]
            exam_bridge["misunderstanding_traps"] = [dict(item) for item in _coerce_list(exam_bridge.get("misunderstanding_traps")) if isinstance(item, dict)][: _budget_max(budget, "exam_bridge", "misunderstanding_traps")]
        exam_bridge["use_this_text_for"] = [
            re.sub(r"\s+", " ", str(item or "").strip())
            for item in _coerce_list(exam_bridge.get("use_this_text_for"))
            if str(item or "").strip()
        ][: _budget_max(budget, "exam_bridge", "use_this_text_for")]
        exam_bridge["course_connections"] = [
            dict(item) for item in _coerce_list(exam_bridge.get("course_connections")) if isinstance(item, dict)
        ][: _budget_max(budget, "exam_bridge", "course_connections")]
        exam_bridge["comparison_targets"] = [
            dict(item) for item in _coerce_list(exam_bridge.get("comparison_targets")) if isinstance(item, dict)
        ][: _budget_max(budget, "exam_bridge", "comparison_targets")]
        exam_bridge["exam_moves"] = [
            dict(item) for item in _coerce_list(exam_bridge.get("exam_moves")) if isinstance(item, dict)
        ][: _budget_max(budget, "exam_bridge", "exam_moves")]
        exam_bridge["misunderstanding_traps"] = [
            dict(item)
            for item in _coerce_list(exam_bridge.get("misunderstanding_traps"))
            if isinstance(item, dict)
        ][: _budget_max(budget, "exam_bridge", "misunderstanding_traps")]
        exam_bridge["mini_exam_answer_plan_slots"] = [
            str(item).strip()
            for item in _coerce_list(exam_bridge.get("mini_exam_answer_plan_slots"))
            if str(item).strip()
        ][: _budget_max(budget, "exam_bridge", "mini_exam_answer_plan_slots")]
    return normalized


def _number_label(item: dict[str, Any], fallback: int) -> str:
    value = str(item.get("number") or "").strip().rstrip(".")
    return value or str(fallback)


def _append_response_space(
    lines: list[str],
    *,
    answer_shape: str,
    blank_lines: int,
    indent: str = "",
    final_block: bool = False,
) -> None:
    del indent
    if blank_lines <= 0:
        return
    blank_lines = _scaled_response_line_count(blank_lines)
    compact_answer = _answer_shape_is_short(answer_shape) or _answer_shape_prefers_compact_paragraph(answer_shape)
    if final_block:
        line_gap_key = "response_line_gap_extended"
    elif blank_lines <= 1 or compact_answer:
        line_gap_key = "response_line_gap_compact"
    else:
        line_gap_key = "response_line_gap_standard"
    lines.append("")
    for index in range(blank_lines):
        lines.append(r"\noindent\rule{\linewidth}{0.4pt}")
        if index < blank_lines - 1:
            _append_spacing_gap(lines, line_gap_key)


def _append_fill_to_page_response_area(lines: list[str], *, minimum_cm: float = 0.0) -> None:
    if minimum_cm > 0:
        lines.append(_vspace_cm(minimum_cm))
        lines.append("")
    lines.append("\\vspace*{\\fill}")


def _append_fill_page_ruled_space(lines: list[str], *, line_count: int = 6) -> None:
    if line_count <= 0:
        return
    lines.append("")
    line_count = _scaled_response_line_count(line_count)
    for index in range(line_count):
        lines.append(r"\noindent\rule{\linewidth}{0.4pt}")
        if index < line_count - 1:
            _append_spacing_gap(lines, "response_line_gap_standard")


def _lengthen_consolidation_blanks(text: str) -> str:
    return re.sub(r"_{5,}", lambda match: "_" * max(len(match.group(0)) * 3, 30), text)


def _consolidation_blank_rule(blank: str, *, trailing_text: str = "", width_ratio: float | None = None) -> str:
    if width_ratio is None:
        width_ratio = min(0.78, max(0.34, len(blank) / 60))
    return rf"\noindent\underline{{\hspace{{{width_ratio:.2f}\linewidth}}}}{trailing_text}"


def _render_consolidation_fill_in_sentence(number: str, sentence: str) -> list[str]:
    match = re.search(r"_{5,}", sentence)
    if not match:
        return [f"{_md_bold(number + '.')} {sentence}", ""]

    prefix = sentence[: match.start()].rstrip()
    blank = _lengthen_consolidation_blanks(match.group(0))
    suffix = sentence[match.end() :].lstrip()
    trailing_punctuation = ""
    if suffix[:1] in ",.;:!?":
        trailing_punctuation = suffix[:1]
        suffix = suffix[1:].lstrip()
    should_stack_blank = bool(
        prefix
        and suffix
        and (len(sentence) >= 82 or len(prefix) >= 34 or len(suffix) >= 24)
    )
    if not should_stack_blank:
        expanded_sentence = sentence[: match.start()] + blank + sentence[match.end() :]
        return [f"{_md_bold(number + '.')} {expanded_sentence}", ""]

    if trailing_punctuation:
        trailing_text = f"{trailing_punctuation} {suffix}".rstrip()
        return [
            f"{_md_bold(number + '.')} {prefix}",
            "",
            _consolidation_blank_rule(blank, trailing_text=trailing_text, width_ratio=0.32),
            "",
        ]

    lines = [f"{_md_bold(number + '.')} {prefix}", "", _consolidation_blank_rule(blank)]
    if suffix:
        lines.extend(["", suffix])
    lines.append("")
    return lines


def _fixed_v3_title(section_key: str) -> str:
    return V3_FIXED_TITLES[section_key]


def _md_bold(text: Any) -> str:
    return f"**{str(text or '').strip()}**"


def _md_italic(text: Any) -> str:
    return f"*{str(text or '').strip()}*"


def _md_mono(text: Any) -> str:
    return f"`{str(text or '').strip()}`"


def _normalized_source_location(text: Any) -> str:
    value = str(text or "").strip()
    if not value:
        return ""
    value = re.sub(r"^\s*side\s+", "s. ", value, flags=re.IGNORECASE)
    value = re.sub(r"^\s*s\.\s*", "s. ", value, flags=re.IGNORECASE)
    value = re.sub(r"\bBoks\b", "boks", value, flags=re.IGNORECASE)
    value = re.sub(r"\bSpalte\b", "spalte", value, flags=re.IGNORECASE)
    value = re.sub(r"\bAfsnit\b", "afsnit", value, flags=re.IGNORECASE)
    return value


def _quote_anchor_fragment(text: Any) -> str:
    phrase = re.sub(r"\s+", " ", str(text or "").strip()).strip(" .,;:")
    if not phrase:
        return ""
    return f"“(...) {phrase} (...)”"


def _source_passage_quote_text(text: Any) -> str:
    passage = re.sub(r"\s+", " ", str(text or "").strip()).strip()
    if not passage:
        return ""
    passage = passage.strip("\"'“”‘’")
    starts_mid_sentence = bool(re.match(r"^[a-zæøå]", passage))
    ends_mid_sentence = not bool(re.search(r"[.!?]([\"'”’)\]]*)$", passage))
    if starts_mid_sentence and not passage.startswith("(...)"):
        passage = f"(...) {passage}"
    if ends_mid_sentence and not passage.endswith("(...)"):
        passage = passage.rstrip(" .") + " (...)"
    return f"“{passage}”"


def _render_source_passage_block(text: Any, location: Any) -> str:
    quote_text = _source_passage_quote_text(text)
    normalized_location = _normalized_source_location(location)
    if not quote_text and normalized_location:
        return _md_mono(normalized_location)
    if not quote_text:
        return ""
    lines = [f"> {_md_italic(quote_text)}"]
    if normalized_location:
        lines.extend([">", f"> {_md_mono(normalized_location)}"])
    return "\n".join(lines)


def _style_reading_guide_paragraph(paragraph: str, index: int) -> str:
    del index
    text = str(paragraph or "").strip()
    if not text:
        return ""
    return text


def _style_task_prompt(prompt: str) -> str:
    text = str(prompt or "").strip()
    for prefix in TASK_VERB_PREFIXES:
        if text.startswith(f"{prefix} "):
            return f"{_md_bold(prefix)} {text[len(prefix) + 1:]}"
    return text


def _task_type_label(task_type: str) -> str:
    return {
        "term": "Find term",
        "decision": "Træf valg",
        "short_paragraph": "Skriv kort afsnit",
    }.get(task_type, "Løs opgave")


def _completion_markers_enabled(artifact: dict[str, Any]) -> bool:
    variant = artifact.get("variant") if isinstance(artifact.get("variant"), dict) else {}
    return bool(variant.get(RENDER_COMPLETION_MARKERS_KEY, False))


def _is_seeded_review_artifact(artifact: dict[str, Any]) -> bool:
    generator = artifact.get("generator") if isinstance(artifact.get("generator"), dict) else {}
    variant = artifact.get("variant") if isinstance(artifact.get("variant"), dict) else {}
    provider = str(generator.get("provider") or "").strip().casefold()
    if provider == "seeded-from-baseline":
        return True
    return bool(variant.get("seeded_from_baseline", False))


def _validate_review_variant_metadata(variant_metadata: dict[str, Any] | None) -> None:
    if not variant_metadata:
        return
    if bool(variant_metadata.get("seeded_from_baseline", False)):
        raise PrintoutError(
            "seeded_from_baseline is forbidden in review candidates; generate all candidates fresh from source"
        )


def _default_variant_mode_for_output_layout(output_layout: str) -> str:
    if _normalize_output_layout(output_layout) == OUTPUT_LAYOUT_REVIEW:
        return "evaluation_sandbox"
    return "canonical_main"


def _exam_bridge_render_enabled(artifact: dict[str, Any]) -> bool:
    variant = artifact.get("variant") if isinstance(artifact.get("variant"), dict) else {}
    return bool(variant.get(RENDER_EXAM_BRIDGE_KEY, False))


def _check_prefix(artifact: dict[str, Any]) -> str:
    del artifact
    return ""


def _append_completion_footer(lines: list[str], artifact: dict[str, Any], labels: list[str]) -> None:
    del lines, artifact, labels


def validate_v2_scaffold_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise PrintoutError("scaffold payload must be a JSON object")
    for key in ("metadata", "abridged_guide", "unit_test_suite", "cloze_scaffold"):
        if not isinstance(payload.get(key), dict):
            raise PrintoutError(f"scaffold payload missing object: {key}")
    guide = payload["abridged_guide"]
    tests = payload["unit_test_suite"]
    cloze = payload["cloze_scaffold"]
    guide_overview = _coerce_list(guide.get("overview"))
    structure_map = _coerce_list(guide.get("structure_map"))
    quote_targets = _coerce_list(guide.get("key_quote_targets"))
    questions = _coerce_list(tests.get("questions"))
    fill_ins = _coerce_list(cloze.get("fill_in_sentences"))
    diagrams = _coerce_list(cloze.get("diagram_tasks"))
    overview = _coerce_list(cloze.get("overview"))
    if len(guide_overview) != 3:
        raise PrintoutError("abridged guide must include a three-sentence overview")
    _require_text(guide.get("title"), "abridged_guide.title")
    _require_text(guide.get("how_to_use"), "abridged_guide.how_to_use")
    _require_text(guide.get("why_this_text_matters"), "abridged_guide.why_this_text_matters")
    _require_text(tests.get("title"), "unit_test_suite.title")
    _require_text(tests.get("instructions"), "unit_test_suite.instructions")
    _require_text(cloze.get("title"), "cloze_scaffold.title")
    if not 3 <= len(structure_map) <= 7:
        raise PrintoutError("abridged guide must include 3-7 structure-map items")
    if not 3 <= len(quote_targets) <= 4:
        raise PrintoutError("abridged guide must include 3-4 quote targets")
    if not 2 <= len(_coerce_list(guide.get("do_not_get_stuck_on"))) <= 5:
        raise PrintoutError("abridged guide must include 2-5 do-not-get-stuck-on items")
    if not 15 <= len(questions) <= 20:
        raise PrintoutError("unit-test suite must include 15-20 questions")
    if len(overview) != 3:
        raise PrintoutError("cloze scaffold must include a three-sentence overview")
    if not 5 <= len(fill_ins) <= 8:
        raise PrintoutError("cloze scaffold must include 5-8 fill-in sentences")
    if not 1 <= len(diagrams) <= 3:
        raise PrintoutError("cloze scaffold must include 1-3 diagram tasks")
    for item in guide_overview + overview:
        if "____" in str(item):
            raise PrintoutError("overview sentences must not contain blanks")
    for index, item in enumerate(structure_map, start=1):
        if not isinstance(item, dict):
            raise PrintoutError("each structure-map item must be an object")
        _require_text(item.get("number"), f"abridged_guide.structure_map[{index}].number")
        _require_text(item.get("section_hint"), f"abridged_guide.structure_map[{index}].section_hint")
        _require_text(item.get("what_to_get"), f"abridged_guide.structure_map[{index}].what_to_get")
        _require_text(item.get("why_it_matters"), f"abridged_guide.structure_map[{index}].why_it_matters")
        _require_safe_task_hint(item.get("stop_after"), f"abridged_guide.structure_map[{index}].stop_after")
    for index, item in enumerate(quote_targets, start=1):
        if not isinstance(item, dict):
            raise PrintoutError("each quote target must be an object")
        target = _require_text(item.get("target"), f"abridged_guide.key_quote_targets[{index}].target")
        if len(target) > 140:
            raise PrintoutError("quote targets must be short search phrases, not reproduced passages")
        _require_text(item.get("why"), f"abridged_guide.key_quote_targets[{index}].why")
        _require_text(item.get("where_to_look"), f"abridged_guide.key_quote_targets[{index}].where_to_look")
    for index, item in enumerate(questions, start=1):
        if not isinstance(item, dict):
            raise PrintoutError("each unit-test question must be an object")
        _require_text(item.get("number"), f"unit_test_suite.questions[{index}].number")
        question = _require_text(item.get("question"), f"unit_test_suite.questions[{index}].question")
        if not question.endswith("?"):
            raise PrintoutError("each unit-test question must be phrased as a question")
        if len(question) > 220:
            raise PrintoutError("unit-test questions must stay short and concrete")
        _reject_broad_prompt(question, "unit-test question")
        _require_safe_task_hint(item.get("where_to_look"), f"unit_test_suite.questions[{index}].where_to_look")
        _require_answer_shape(item.get("answer_shape"), f"unit_test_suite.questions[{index}].answer_shape")
        _require_safe_task_hint(
            item.get("done_signal"),
            f"unit_test_suite.questions[{index}].done_signal",
            forbid_parentheses=True,
        )
    for index, item in enumerate(fill_ins, start=1):
        if not isinstance(item, dict):
            raise PrintoutError("each cloze sentence must be an object")
        _require_text(item.get("number"), f"cloze_scaffold.fill_in_sentences[{index}].number")
        sentence = str(item.get("sentence") if isinstance(item, dict) else item)
        if _blank_count(sentence) != 1:
            raise PrintoutError("each cloze sentence must contain exactly one blank marker")
        if len(sentence) > 220:
            raise PrintoutError("cloze sentences must stay short enough for print use")
        _reject_broad_prompt(sentence, "cloze sentence")
        _require_safe_task_hint(item.get("where_to_look"), f"cloze_scaffold.fill_in_sentences[{index}].where_to_look")
        _require_answer_shape(item.get("answer_shape"), f"cloze_scaffold.fill_in_sentences[{index}].answer_shape")
    for index, item in enumerate(diagrams, start=1):
        if not isinstance(item, dict):
            raise PrintoutError("each diagram task must be an object")
        _require_text(item.get("number"), f"cloze_scaffold.diagram_tasks[{index}].number")
        _reject_broad_prompt(_require_text(item.get("task"), f"cloze_scaffold.diagram_tasks[{index}].task"), "diagram task")
        _require_text(item.get("blank_space_hint"), f"cloze_scaffold.diagram_tasks[{index}].blank_space_hint")
        elements = _coerce_list(item.get("required_elements")) if isinstance(item, dict) else []
        if len(elements) < 2:
            raise PrintoutError("each diagram task must include at least two required elements")
        for element in elements:
            _require_text(element, f"cloze_scaffold.diagram_tasks[{index}].required_elements[]")
    return payload


def _require_object(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PrintoutError(f"scaffold payload missing object: {field_name}")
    return value


def _require_count(items: list[Any], field_name: str, minimum: int, maximum: int) -> None:
    if not minimum <= len(items) <= maximum:
        raise PrintoutError(f"{field_name} must include {minimum}-{maximum} items")


def _word_count(text: str) -> int:
    return len([part for part in re.split(r"\s+", text.strip()) if part])


def _require_short_quote_anchor(value: Any, field_name: str) -> str:
    text = _require_text(value, field_name)
    if len(text) > 180 or _word_count(text) > 18:
        raise PrintoutError(f"{field_name} must be a short quote anchor, not a reproduced passage")
    return text


def _require_short_source_passage(value: Any, field_name: str) -> str:
    text = _require_text(value, field_name)
    if len(text) > 900 or _word_count(text) > 120:
        raise PrintoutError(f"{field_name} must stay short enough to function as one paragraph-level excerpt")
    return text


def _validate_v3_reading_guide(guide: dict[str, Any], *, length_budget: dict[str, Any]) -> None:
    _require_text(guide.get("title"), "reading_guide.title")
    _require_text(guide.get("how_to_use"), "reading_guide.how_to_use")
    main_problem = _require_text(guide.get("main_problem"), "reading_guide.main_problem")
    _require_text(guide.get("why_this_text_matters"), "reading_guide.why_this_text_matters")
    if len(main_problem) > 220:
        raise PrintoutError("reading guide main_problem must stay short enough for a mission brief")
    teaser_paragraphs = _coerce_list(guide.get("teaser_paragraphs"))
    opening_passages = _coerce_list(guide.get("opening_passages"))
    subproblems = _coerce_list(guide.get("subproblems"))
    overview = _coerce_list(guide.get("overview"))
    route = _coerce_list(guide.get("reading_route"))
    quote_targets = _coerce_list(guide.get("key_quote_targets"))
    stuck_items = _coerce_list(guide.get("do_not_get_stuck_on"))
    if len(overview) != 3:
        raise PrintoutError("reading guide must include a three-sentence overview")
    _require_count(
        teaser_paragraphs,
        "reading_guide.teaser_paragraphs",
        _budget_min(length_budget, "reading_guide", "teaser_paragraphs"),
        _budget_max(length_budget, "reading_guide", "teaser_paragraphs"),
    )
    _require_count(
        subproblems,
        "reading_guide.subproblems",
        _budget_min(length_budget, "reading_guide", "subproblems"),
        _budget_max(length_budget, "reading_guide", "subproblems"),
    )
    _require_count(
        route,
        "reading_guide.reading_route",
        _budget_min(length_budget, "reading_guide", "reading_route"),
        _budget_max(length_budget, "reading_guide", "reading_route"),
    )
    _require_count(
        quote_targets,
        "reading_guide.key_quote_targets",
        _budget_min(length_budget, "reading_guide", "key_quote_targets"),
        _budget_max(length_budget, "reading_guide", "key_quote_targets"),
    )
    _require_count(
        stuck_items,
        "reading_guide.do_not_get_stuck_on",
        _budget_min(length_budget, "reading_guide", "do_not_get_stuck_on"),
        _budget_max(length_budget, "reading_guide", "do_not_get_stuck_on"),
    )
    total_teaser_words = 0
    total_questions = 0
    for index, paragraph in enumerate(teaser_paragraphs, start=1):
        text = _require_text(paragraph, f"reading_guide.teaser_paragraphs[{index}]")
        if "____" in text:
            raise PrintoutError("reading guide teaser paragraphs must not contain blanks")
        if re.match(r"^\s*(?:[-*]|\d+\.)\s+", text):
            raise PrintoutError("reading guide teaser paragraphs must be prose, not list items")
        total_teaser_words += _word_count(text)
        total_questions += text.count("?")
    if total_teaser_words < 110:
        raise PrintoutError("reading guide teaser paragraphs must be substantial enough to feel like a half-page appetizer")
    if total_questions > 3:
        raise PrintoutError("reading guide teaser paragraphs must not read like a fill-out question list")
    for item in overview:
        if "____" in str(item):
            raise PrintoutError("reading guide overview must not contain blanks")
    if opening_passages:
        _require_count(
            opening_passages,
            "reading_guide.opening_passages",
            _budget_min(length_budget, "reading_guide", "opening_passages"),
            _budget_max(length_budget, "reading_guide", "opening_passages"),
        )
        for index, item in enumerate(opening_passages, start=1):
            if not isinstance(item, dict):
                raise PrintoutError("each reading-guide opening passage must be an object")
            _require_text(item.get("number"), f"reading_guide.opening_passages[{index}].number")
            _require_text(item.get("source_location"), f"reading_guide.opening_passages[{index}].source_location")
            _require_short_source_passage(item.get("excerpt"), f"reading_guide.opening_passages[{index}].excerpt")
            question = _require_text(item.get("open_question"), f"reading_guide.opening_passages[{index}].open_question")
            if not question.endswith("?"):
                raise PrintoutError("reading-guide opening questions must be phrased as questions")
            _reject_broad_prompt(question, "reading-guide opening question")
    for index, item in enumerate(subproblems, start=1):
        if not isinstance(item, dict):
            raise PrintoutError("each reading-guide subproblem must be an object")
        _require_text(item.get("number"), f"reading_guide.subproblems[{index}].number")
        question = _require_text(item.get("question"), f"reading_guide.subproblems[{index}].question")
        if not question.endswith("?"):
            raise PrintoutError("reading-guide subproblems must be phrased as questions")
        _reject_broad_prompt(question, "reading-guide subproblem")
        _require_text(item.get("why_it_matters"), f"reading_guide.subproblems[{index}].why_it_matters")
        _require_answer_shape(item.get("answer_form"), f"reading_guide.subproblems[{index}].answer_form")
    for index, item in enumerate(route, start=1):
        if not isinstance(item, dict):
            raise PrintoutError("each reading-route item must be an object")
        _require_text(item.get("number"), f"reading_guide.reading_route[{index}].number")
        _require_text(item.get("source_location"), f"reading_guide.reading_route[{index}].source_location")
        _require_text(item.get("task"), f"reading_guide.reading_route[{index}].task")
        _require_text(item.get("why_it_matters"), f"reading_guide.reading_route[{index}].why_it_matters")
        _require_safe_task_hint(item.get("stop_signal"), f"reading_guide.reading_route[{index}].stop_signal")
    for index, item in enumerate(quote_targets, start=1):
        if not isinstance(item, dict):
            raise PrintoutError("each reading-guide quote target must be an object")
        _require_short_quote_anchor(item.get("target"), f"reading_guide.key_quote_targets[{index}].target")
        _require_text(item.get("why"), f"reading_guide.key_quote_targets[{index}].why")
        _require_text(item.get("where_to_look"), f"reading_guide.key_quote_targets[{index}].where_to_look")


def _validate_v3_abridged_reader(reader: dict[str, Any], *, length_budget: dict[str, Any]) -> None:
    _require_text(reader.get("title"), "abridged_reader.title")
    _require_text(reader.get("how_to_use"), "abridged_reader.how_to_use")
    _require_text(reader.get("coverage_note"), "abridged_reader.coverage_note")
    sections = _coerce_list(reader.get("sections"))
    _require_count(
        sections,
        "abridged_reader.sections",
        _budget_min(length_budget, "abridged_reader", "sections"),
        _budget_max(length_budget, "abridged_reader", "sections"),
    )
    for index, item in enumerate(sections, start=1):
        if not isinstance(item, dict):
            raise PrintoutError("each abridged-reader section must be an object")
        _require_text(item.get("number"), f"abridged_reader.sections[{index}].number")
        _require_text(item.get("source_location"), f"abridged_reader.sections[{index}].source_location")
        _require_text(item.get("heading"), f"abridged_reader.sections[{index}].heading")
        _require_text(item.get("solves_subproblem"), f"abridged_reader.sections[{index}].solves_subproblem")
        local_problem = _require_text(item.get("local_problem"), f"abridged_reader.sections[{index}].local_problem")
        if not local_problem.endswith("?"):
            raise PrintoutError("abridged-reader local_problem must be phrased as a question")
        paragraphs = _coerce_list(item.get("explanation_paragraphs"))
        key_points = _coerce_list(item.get("key_points"))
        quote_anchors = _coerce_list(item.get("quote_anchors"))
        source_passages = _coerce_list(item.get("source_passages"))
        _require_count(paragraphs, f"abridged_reader.sections[{index}].explanation_paragraphs", 2, 5)
        _require_count(key_points, f"abridged_reader.sections[{index}].key_points", 1, 5)
        if len(quote_anchors) > 3:
            raise PrintoutError("each abridged-reader section may include at most 3 quote anchors")
        if len(source_passages) > 1:
            raise PrintoutError("each abridged-reader section may include at most 1 short source passage")
        if not quote_anchors:
            _require_text(
                item.get("no_quote_anchor_needed"),
                f"abridged_reader.sections[{index}].no_quote_anchor_needed",
            )
        for paragraph in paragraphs:
            text = _require_text(paragraph, f"abridged_reader.sections[{index}].explanation_paragraphs[]")
            if _word_count(text) > 95:
                raise PrintoutError("abridged-reader paragraphs must stay short")
        for anchor_index, anchor in enumerate(quote_anchors, start=1):
            if not isinstance(anchor, dict):
                raise PrintoutError("each quote anchor must be an object")
            _require_short_quote_anchor(
                anchor.get("phrase"),
                f"abridged_reader.sections[{index}].quote_anchors[{anchor_index}].phrase",
            )
            _require_text(
                anchor.get("why_it_matters"),
                f"abridged_reader.sections[{index}].quote_anchors[{anchor_index}].why_it_matters",
            )
            _require_text(
                anchor.get("source_location"),
                f"abridged_reader.sections[{index}].quote_anchors[{anchor_index}].source_location",
            )
        for passage_index, passage in enumerate(source_passages, start=1):
            if not isinstance(passage, dict):
                raise PrintoutError("each abridged-reader source passage must be an object")
            _require_text(
                passage.get("source_location"),
                f"abridged_reader.sections[{index}].source_passages[{passage_index}].source_location",
            )
            _require_short_source_passage(
                passage.get("passage"),
                f"abridged_reader.sections[{index}].source_passages[{passage_index}].passage",
            )
            _require_text(
                passage.get("why_it_matters"),
                f"abridged_reader.sections[{index}].source_passages[{passage_index}].why_it_matters",
            )
def _validate_v3_active_reading(active: dict[str, Any], *, length_budget: dict[str, Any]) -> None:
    _require_text(active.get("title"), "active_reading.title")
    _require_text(active.get("instructions"), "active_reading.instructions")
    solve_steps = _coerce_list(active.get("solve_steps"))
    _require_count(
        solve_steps,
        "active_reading.solve_steps",
        _budget_min(length_budget, "active_reading", "solve_steps"),
        _budget_max(length_budget, "active_reading", "solve_steps"),
    )
    paragraph_steps = 0
    for index, item in enumerate(solve_steps, start=1):
        if not isinstance(item, dict):
            raise PrintoutError("each active-reading solve step must be an object")
        _require_text(item.get("number"), f"active_reading.solve_steps[{index}].number")
        _require_text(item.get("subproblem_ref"), f"active_reading.solve_steps[{index}].subproblem_ref")
        prompt = _require_text(item.get("prompt"), f"active_reading.solve_steps[{index}].prompt")
        _reject_broad_prompt(prompt, "active-reading solve step")
        task_type = _require_task_type(item.get("task_type"), f"active_reading.solve_steps[{index}].task_type")
        _require_abridged_reference(
            item.get("abridged_reader_location"),
            f"active_reading.solve_steps[{index}].abridged_reader_location",
        )
        _require_answer_shape(item.get("answer_shape"), f"active_reading.solve_steps[{index}].answer_shape")
        _require_blank_lines(
            item.get("blank_lines"),
            f"active_reading.solve_steps[{index}].blank_lines",
            task_type=task_type,
        )
        _require_safe_task_hint(
            item.get("done_signal"),
            f"active_reading.solve_steps[{index}].done_signal",
            forbid_parentheses=True,
        )
        if task_type == "short_paragraph":
            paragraph_steps += 1
    if paragraph_steps < 1:
        raise PrintoutError("active_reading must include at least one short_paragraph solve step")


def _validate_v3_consolidation(consolidation: dict[str, Any], *, length_budget: dict[str, Any]) -> None:
    _require_text(consolidation.get("title"), "consolidation_sheet.title")
    _require_text(consolidation.get("instructions"), "consolidation_sheet.instructions")
    overview = _coerce_list(consolidation.get("overview"))
    fill_ins = _coerce_list(consolidation.get("fill_in_sentences"))
    diagrams = _coerce_list(consolidation.get("diagram_tasks"))
    if len(overview) != 3:
        raise PrintoutError("consolidation sheet must include a three-sentence overview")
    _require_count(
        fill_ins,
        "consolidation_sheet.fill_in_sentences",
        _budget_min(length_budget, "consolidation_sheet", "fill_in_sentences"),
        _budget_max(length_budget, "consolidation_sheet", "fill_in_sentences"),
    )
    _require_count(
        diagrams,
        "consolidation_sheet.diagram_tasks",
        _budget_min(length_budget, "consolidation_sheet", "diagram_tasks"),
        _budget_max(length_budget, "consolidation_sheet", "diagram_tasks"),
    )
    for item in overview:
        if "____" in str(item):
            raise PrintoutError("consolidation overview must not contain blanks")
    for index, item in enumerate(fill_ins, start=1):
        if not isinstance(item, dict):
            raise PrintoutError("each consolidation fill-in sentence must be an object")
        _require_text(item.get("number"), f"consolidation_sheet.fill_in_sentences[{index}].number")
        sentence = str(item.get("sentence") or "")
        if _blank_count(sentence) != 1:
            raise PrintoutError("each consolidation fill-in sentence must contain exactly one blank marker")
        if len(sentence) > 240:
            raise PrintoutError("consolidation fill-in sentences must stay short enough for print use")
        if _looks_like_source_page_reference(sentence) or re.search(r"\bfigur\b", sentence, flags=re.IGNORECASE):
            raise PrintoutError("consolidation fill-in sentences must not depend on original figures or source pages")
        _reject_broad_prompt(sentence, "consolidation fill-in sentence")
        _require_abridged_reference(
            item.get("where_to_look"),
            f"consolidation_sheet.fill_in_sentences[{index}].where_to_look",
        )
        _require_answer_shape(item.get("answer_shape"), f"consolidation_sheet.fill_in_sentences[{index}].answer_shape")
    for index, item in enumerate(diagrams, start=1):
        if not isinstance(item, dict):
            raise PrintoutError("each consolidation diagram task must be an object")
        _require_text(item.get("number"), f"consolidation_sheet.diagram_tasks[{index}].number")
        task_text = _require_text(item.get("task"), f"consolidation_sheet.diagram_tasks[{index}].task")
        if _looks_like_source_page_reference(task_text) or re.search(r"\bfigur\b", task_text, flags=re.IGNORECASE):
            raise PrintoutError("consolidation diagram tasks must not depend on source figures or original pages")
        _reject_broad_prompt(
            task_text,
            "consolidation diagram task",
        )
        _require_text(item.get("blank_space_hint"), f"consolidation_sheet.diagram_tasks[{index}].blank_space_hint")
        elements = _coerce_list(item.get("required_elements"))
        if len(elements) < 2:
            raise PrintoutError("each consolidation diagram task must include at least two required elements")
        for element in elements:
            _require_text(element, f"consolidation_sheet.diagram_tasks[{index}].required_elements[]")


def _validate_v3_exam_bridge(exam_bridge: dict[str, Any], *, length_budget: dict[str, Any]) -> None:
    _require_text(exam_bridge.get("title"), "exam_bridge.title")
    _require_text(exam_bridge.get("instructions"), "exam_bridge.instructions")
    _require_count(
        _coerce_list(exam_bridge.get("use_this_text_for")),
        "exam_bridge.use_this_text_for",
        _budget_min(length_budget, "exam_bridge", "use_this_text_for"),
        _budget_max(length_budget, "exam_bridge", "use_this_text_for"),
    )
    _require_count(
        _coerce_list(exam_bridge.get("course_connections")),
        "exam_bridge.course_connections",
        _budget_min(length_budget, "exam_bridge", "course_connections"),
        _budget_max(length_budget, "exam_bridge", "course_connections"),
    )
    _require_count(
        _coerce_list(exam_bridge.get("comparison_targets")),
        "exam_bridge.comparison_targets",
        _budget_min(length_budget, "exam_bridge", "comparison_targets"),
        _budget_max(length_budget, "exam_bridge", "comparison_targets"),
    )
    _require_count(
        _coerce_list(exam_bridge.get("exam_moves")),
        "exam_bridge.exam_moves",
        _budget_min(length_budget, "exam_bridge", "exam_moves"),
        _budget_max(length_budget, "exam_bridge", "exam_moves"),
    )
    _require_count(
        _coerce_list(exam_bridge.get("misunderstanding_traps")),
        "exam_bridge.misunderstanding_traps",
        _budget_min(length_budget, "exam_bridge", "misunderstanding_traps"),
        _budget_max(length_budget, "exam_bridge", "misunderstanding_traps"),
    )
    for index, item in enumerate(_coerce_list(exam_bridge.get("course_connections")), start=1):
        if not isinstance(item, dict):
            raise PrintoutError("each exam bridge course connection must be an object")
        _require_text(item.get("course_theme"), f"exam_bridge.course_connections[{index}].course_theme")
        _require_text(item.get("connection"), f"exam_bridge.course_connections[{index}].connection")
    for index, item in enumerate(_coerce_list(exam_bridge.get("comparison_targets")), start=1):
        if not isinstance(item, dict):
            raise PrintoutError("each exam bridge comparison target must be an object")
        _require_text(item.get("compare_with"), f"exam_bridge.comparison_targets[{index}].compare_with")
        _require_text(item.get("how_to_compare"), f"exam_bridge.comparison_targets[{index}].how_to_compare")
    for index, item in enumerate(_coerce_list(exam_bridge.get("exam_moves")), start=1):
        if not isinstance(item, dict):
            raise PrintoutError("each exam bridge move must be an object")
        _require_text(item.get("prompt_type"), f"exam_bridge.exam_moves[{index}].prompt_type")
        _require_text(item.get("use_in_answer"), f"exam_bridge.exam_moves[{index}].use_in_answer")
        _require_text(item.get("caution"), f"exam_bridge.exam_moves[{index}].caution")
    for index, item in enumerate(_coerce_list(exam_bridge.get("misunderstanding_traps")), start=1):
        if not isinstance(item, dict):
            raise PrintoutError("each exam bridge misunderstanding trap must be an object")
        _require_text(item.get("trap"), f"exam_bridge.misunderstanding_traps[{index}].trap")
        _require_text(item.get("better_reading"), f"exam_bridge.misunderstanding_traps[{index}].better_reading")
    _require_text(exam_bridge.get("mini_exam_prompt_question"), "exam_bridge.mini_exam_prompt_question")
    _require_count(
        _coerce_list(exam_bridge.get("mini_exam_answer_plan_slots")),
        "exam_bridge.mini_exam_answer_plan_slots",
        _budget_min(length_budget, "exam_bridge", "mini_exam_answer_plan_slots"),
        _budget_max(length_budget, "exam_bridge", "mini_exam_answer_plan_slots"),
    )


def validate_printout_payload(
    payload: dict[str, Any],
    *,
    length_budget: dict[str, Any] | None = None,
    validate_exam_bridge: bool = True,
) -> dict[str, Any]:
    budget = length_budget or build_printout_length_budget()
    if not isinstance(payload, dict):
        raise PrintoutError("scaffold payload must be a JSON object")
    for key in (
        "metadata",
        "reading_guide",
        "abridged_reader",
        "active_reading",
        "consolidation_sheet",
        "exam_bridge",
    ):
        if not isinstance(payload.get(key), dict):
            raise PrintoutError(f"scaffold payload missing object: {key}")
    _validate_v3_reading_guide(payload["reading_guide"], length_budget=budget)
    _validate_v3_abridged_reader(payload["abridged_reader"], length_budget=budget)
    _validate_v3_active_reading(payload["active_reading"], length_budget=budget)
    _validate_v3_consolidation(payload["consolidation_sheet"], length_budget=budget)
    if validate_exam_bridge:
        _validate_v3_exam_bridge(payload["exam_bridge"], length_budget=budget)
    return payload


def _is_retryable_generation_error(exc: Exception) -> bool:
    if not isinstance(exc, GeminiPreprocessingGenerationError):
        return False
    text = str(exc or "").strip().casefold()
    if not text:
        return False
    if any(token in text for token in ("response was not valid json", "response json must be an object", "did not contain a json object", "returned an empty response")):
        return False
    return any(token in text for token in TRANSIENT_GENERATION_ERROR_PATTERNS)


def call_json_generator(
    *,
    backend: GeminiPreprocessingBackend | None,
    json_generator: JsonGenerator | None,
    model: str,
    system_instruction: str,
    user_prompt: str,
    source_paths: list[Path],
    max_output_tokens: int,
    response_json_schema: dict[str, Any] | None,
    generation_stats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if json_generator is not None:
        if generation_stats is not None:
            generation_stats["attempt_count"] = 1
            generation_stats.setdefault("transient_error_count", 0)
            generation_stats.setdefault("last_transient_error", "")
        return json_generator(
            system_instruction=system_instruction,
            user_prompt=user_prompt,
            source_paths=source_paths,
            max_output_tokens=max_output_tokens,
            response_json_schema=response_json_schema,
        )
    active_backend = backend or make_gemini_backend(model=model)
    last_exc: Exception | None = None
    if generation_stats is not None:
        generation_stats["attempt_count"] = 0
        generation_stats["transient_error_count"] = 0
        generation_stats["last_transient_error"] = ""
    for attempt, delay_seconds in enumerate((0, *TRANSIENT_GENERATION_RETRY_DELAYS_SECONDS), start=1):
        if generation_stats is not None:
            generation_stats["attempt_count"] = attempt
        if delay_seconds:
            print(
                f"[printout_engine] retrying transient Gemini generation failure in {delay_seconds}s (attempt {attempt})",
                file=sys.stderr,
                flush=True,
            )
            time.sleep(delay_seconds)
        try:
            return generate_json(
                backend=active_backend,
                system_instruction=system_instruction,
                user_prompt=user_prompt,
                source_paths=source_paths,
                max_output_tokens=max_output_tokens,
                response_json_schema=response_json_schema,
            )
        except Exception as exc:
            last_exc = exc
            if not _is_retryable_generation_error(exc) or attempt >= len(TRANSIENT_GENERATION_RETRY_DELAYS_SECONDS) + 1:
                raise
            if generation_stats is not None:
                generation_stats["transient_error_count"] = int(generation_stats.get("transient_error_count") or 0) + 1
                generation_stats["last_transient_error"] = str(exc)
            print(
                f"[printout_engine] transient Gemini generation failure on attempt {attempt}: {exc}",
                file=sys.stderr,
                flush=True,
            )
            continue
    if last_exc is not None:
        raise last_exc
    raise PrintoutError("call_json_generator exited without a result")


def _sanitized_generation_error(exc: Exception) -> str:
    text = re.sub(r"\s+", " ", str(exc or "").strip())
    text = re.sub(r"AIza[0-9A-Za-z_-]{20,}", "[redacted-google-api-key]", text)
    text = re.sub(r"sk-[0-9A-Za-z_-]{20,}", "[redacted-openai-api-key]", text)
    return text[:500]


def build_printout_for_source(
    *,
    repo_root: Path,
    subject_root: Path,
    source: dict[str, Any],
    source_card_dir: Path,
    revised_lecture_substrate_dir: Path,
    course_synthesis_path: Path,
    output_root: Path,
    model: str = DEFAULT_GEMINI_PREPROCESSING_MODEL,
    backend: GeminiPreprocessingBackend | None = None,
    json_generator: JsonGenerator | None = None,
    render_pdf: bool = True,
    force: bool = False,
    rerender_existing: bool = False,
    prompt_version: str = PROMPT_VERSION,
    system_instruction: str | None = None,
    user_prompt_builder: UserPromptBuilder | None = None,
    variant_metadata: dict[str, Any] | None = None,
    generation_provider: str = "gemini",
    generation_config_metadata_override: dict[str, Any] | None = None,
    output_layout: str = OUTPUT_LAYOUT_CANONICAL,
) -> dict[str, Any]:
    _validate_review_variant_metadata(variant_metadata)
    output_layout = _normalize_output_layout(output_layout)
    source_id = str(source.get("source_id") or "").strip()
    if not source_id:
        raise PrintoutError("source is missing source_id")
    source_paths = recursive.source_file_paths(subject_root, source)
    if not source_paths:
        raise PrintoutError(f"source has no subject_relative_path: {source_id}")
    missing_paths = [path for path in source_paths if not path.exists() or not path.is_file()]
    if missing_paths:
        raise PrintoutError(f"source file not found: {missing_paths[0]}")
    card_path = source_card_path(source_card_dir, source_id)
    if not card_path.exists():
        raise PrintoutError(f"source card not found: {card_path}")
    source_root = printout_source_root(output_root, source, output_layout=output_layout)
    out_dir = source_root
    legacy_printout_dir = legacy_printout_dir_for_source(output_root, source)
    legacy_scaffolding_dir = legacy_output_dir_for_source(output_root, source)
    _promote_legacy_printouts_if_present(
        canonical_out_dir=out_dir,
        legacy_printout_dir=legacy_printout_dir,
        legacy_scaffolding_dir=legacy_scaffolding_dir,
    )
    json_path = artifact_json_path_for_output_dir(
        output_root,
        source,
        out_dir,
        provider=generation_provider,
        model=model,
        output_layout=output_layout,
    )
    existing_json_path = _find_existing_artifact_json(
        output_root,
        source,
        out_dir,
        provider=generation_provider,
        model=model,
        output_layout=output_layout,
    )
    if rerender_existing and not force and existing_json_path is None:
        raise PrintoutError(f"existing printout JSON not found for rerender: {json_path}")
    if existing_json_path is not None and not force:
        candidate_existing_artifact = read_json(existing_json_path)
        if _is_seeded_review_artifact(candidate_existing_artifact):
            raise PrintoutError(
                f"existing review candidate is seeded and invalid for reuse: {source_id}. "
                "Generate a fresh from-scratch candidate with --force."
            )
        if not _artifact_generator_matches(candidate_existing_artifact, provider=generation_provider, model=model):
            existing_json_path = None
    if rerender_existing and not force and existing_json_path is None:
        raise PrintoutError(f"matching existing printout JSON not found for rerender: {json_path}")
    if existing_json_path is not None and not force:
        existing_artifact = read_json(existing_json_path)
        existing_schema_version = _artifact_schema_version(existing_artifact)
        if output_layout == OUTPUT_LAYOUT_CANONICAL and existing_schema_version < SCHEMA_VERSION:
            if rerender_existing:
                raise PrintoutError(
                    f"existing printout is legacy schema v{existing_schema_version} and cannot be "
                    f"rerendered into canonical schema v{SCHEMA_VERSION} without generation: {existing_json_path}"
                )
            existing_json_path = None
        else:
            expected_pdf_stems = _expected_pdf_stems_for_artifact(existing_artifact)
            existing_pdf_paths = _existing_pdf_paths_for_artifact(out_dir, existing_artifact, stems=expected_pdf_stems)
            has_expected_pdfs = len(existing_pdf_paths) == len(expected_pdf_stems)
            should_auto_rerender_legacy = (
                existing_json_path.resolve() != json_path.resolve()
                and (output_layout == OUTPUT_LAYOUT_CANONICAL or not has_expected_pdfs)
            )
            should_auto_rerender_incomplete = render_pdf and not has_expected_pdfs
            if _is_seeded_review_artifact(existing_artifact):
                raise PrintoutError(
                    f"existing review candidate is seeded and invalid for reuse: {source_id}. "
                    "Generate a fresh from-scratch candidate with --force."
                )
            if rerender_existing or should_auto_rerender_legacy or should_auto_rerender_incomplete:
                artifact = existing_artifact
                artifact_source = artifact.get("source") if isinstance(artifact.get("source"), dict) else {}
                artifact_source["reading_title"] = _reading_title_from_source(artifact_source)
                artifact["source"] = artifact_source
                existing_source_card = read_json(card_path) if card_path.exists() else {}
                length_budget = build_printout_length_budget(
                    source=artifact.get("source") if isinstance(artifact.get("source"), dict) else source,
                    source_card=existing_source_card if isinstance(existing_source_card, dict) else None,
                )
                if variant_metadata:
                    existing_variant = artifact.get("variant") if isinstance(artifact.get("variant"), dict) else {}
                    artifact["variant"] = {**existing_variant, **dict(variant_metadata)}
                artifact_variant = artifact.get("variant") if isinstance(artifact.get("variant"), dict) else {}
                artifact_variant.setdefault("mode", _default_variant_mode_for_output_layout(output_layout))
                artifact["variant"] = artifact_variant
                if existing_schema_version >= SCHEMA_VERSION:
                    artifact["schema_version"] = SCHEMA_VERSION
                    normalized = validate_printout_payload(
                        normalize_scaffold_payload(
                            artifact.get("printouts") or artifact.get("scaffolds", {}),
                            legacy_compat=True,
                            length_budget=length_budget,
                        ),
                        length_budget=length_budget,
                        validate_exam_bridge=_exam_bridge_render_enabled(artifact),
                    )
                    artifact["length_budget"] = length_budget
                    artifact["printouts"] = normalized
                    artifact["scaffolds"] = normalized
                else:
                    artifact["schema_version"] = LEGACY_SCHEMA_VERSION
                    artifact["scaffolds"] = validate_v2_scaffold_payload(
                        normalize_v2_scaffold_payload(artifact.get("scaffolds", {}))
                    )
                rendered = render_printout_files(artifact=artifact, output_dir=out_dir, render_pdf=render_pdf)
                write_json(json_path, artifact)
                legacy_json_in_output = _legacy_json_path_in_output_dir(out_dir)
                if legacy_json_in_output.exists() and legacy_json_in_output.resolve() != json_path.resolve():
                    legacy_json_in_output.unlink()
                _cleanup_legacy_review_dirs(
                    output_root=output_root,
                    legacy_dirs=[
                        path
                        for path in [legacy_printout_dir, legacy_scaffolding_dir]
                        if path.resolve() != out_dir.resolve()
                    ],
                )
                return {
                    "source_id": source_id,
                    "status": "rerendered_existing",
                    "output_dir": str(out_dir),
                    "json_path": str(json_path),
                    "markdown_paths": rendered["markdown_paths"],
                    "pdf_paths": rendered["pdf_paths"],
                }
            return {
                "source_id": source_id,
                "status": "skipped_existing",
                "output_dir": str(out_dir),
                "json_path": str(existing_json_path),
                "pdf_paths": existing_pdf_paths,
            }
    source_card = read_json(card_path)
    lecture_key = str(source.get("lecture_key") or source_card.get("source", {}).get("lecture_key") or "").strip()
    source_card_source = source_card.get("source") if isinstance(source_card.get("source"), dict) else {}
    reading_title = _reading_title_from_source({**source_card_source, **source})
    length_budget = build_printout_length_budget(source=source, source_card=source_card)
    generation_stats: dict[str, Any] = {}
    try:
        response = call_json_generator(
            backend=backend,
            json_generator=json_generator,
            model=model,
            system_instruction=system_instruction or printout_system_instruction(),
            user_prompt=(user_prompt_builder or printout_user_prompt)(
                source=source,
                source_card=source_card,
                lecture_context=_compact_lecture_context(revised_lecture_substrate_dir, lecture_key),
                course_context=_compact_course_context(course_synthesis_path),
                length_budget=length_budget,
            ),
            source_paths=source_paths,
            max_output_tokens=32768,
            response_json_schema=None,
            generation_stats=generation_stats,
        )
    except Exception as exc:
        generation_stats["last_error_kind"] = type(exc).__name__
        generation_stats["last_error_summary"] = _sanitized_generation_error(exc)
        raise GenerationFailure(
            f"generation failed after {int(generation_stats.get('attempt_count') or 0)} attempt(s): "
            f"{generation_stats['last_error_summary']}",
            generation_stats=generation_stats,
        ) from exc
    validate_exam_bridge = bool((variant_metadata or {}).get(RENDER_EXAM_BRIDGE_KEY, False))
    printouts = validate_printout_payload(
        normalize_scaffold_payload(response, length_budget=length_budget),
        length_budget=length_budget,
        validate_exam_bridge=validate_exam_bridge,
    )
    artifact = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "reading_printouts",
        "subject_slug": SUBJECT_SLUG,
        "generated_at": utc_now_iso(),
        "generator": {
            "provider": generation_provider,
            "model": model,
            "prompt_version": prompt_version,
            "generation_config": generation_config_metadata_override or printout_generation_config_metadata(),
            "run": generation_stats,
        },
        "provenance": {
            "source_file": recursive.sha256_file(source_paths[0])
            if len(source_paths) == 1
            else recursive.signature_for_files(source_paths),
            "source_files_signature": recursive.signature_for_files(source_paths),
            "source_card": recursive.sha256_file(card_path),
            "revised_lecture_substrate": _sha256_if_exists(revised_lecture_substrate_dir / f"{lecture_key}.json"),
            "course_synthesis": _sha256_if_exists(course_synthesis_path),
        },
        "source": {
            "source_id": source_id,
            "lecture_key": lecture_key,
            "title": str(source.get("title") or ""),
            "reading_title": reading_title,
            "source_family": str(source.get("source_family") or ""),
            "evidence_origin": str(source.get("evidence_origin") or ""),
            "length_band": str(source.get("length_band") or source_card.get("source", {}).get("length_band") or ""),
            "page_count": source_card.get("source", {}).get("page_count"),
            "estimated_token_count": source_card.get("source", {}).get("estimated_token_count"),
            "source_path": str(source_paths[0].resolve()),
            "source_paths": [str(path.resolve()) for path in source_paths],
            "repo_display_path": recursive.display_path(source_paths[0], repo_root),
            "repo_display_paths": [recursive.display_path(path, repo_root) for path in source_paths],
        },
        "length_budget": length_budget,
        "printouts": printouts,
        "scaffolds": printouts,
    }
    artifact["variant"] = dict(variant_metadata or {})
    artifact["variant"].setdefault("mode", _default_variant_mode_for_output_layout(output_layout))
    rendered = render_printout_files(artifact=artifact, output_dir=out_dir, render_pdf=render_pdf)
    write_json(json_path, artifact)
    legacy_json_in_output = _legacy_json_path_in_output_dir(out_dir)
    if legacy_json_in_output.exists() and legacy_json_in_output.resolve() != json_path.resolve():
        legacy_json_in_output.unlink()
    _cleanup_legacy_review_dirs(
        output_root=output_root,
        legacy_dirs=[
            path
            for path in [legacy_printout_dir, legacy_scaffolding_dir]
            if path.resolve() != out_dir.resolve()
        ],
    )
    return {
        "source_id": source_id,
        "status": "written",
        "output_dir": str(out_dir),
        "json_path": str(json_path),
        "markdown_paths": rendered["markdown_paths"],
        "pdf_paths": rendered["pdf_paths"],
        "generation_stats": generation_stats,
    }


def _sha256_if_exists(path: Path) -> str:
    return recursive.sha256_file(path) if path.exists() and path.is_file() else ""


def _existing_pdf_paths(out_dir: Path) -> list[str]:
    return [str(path) for path in sorted(out_dir.glob("*.pdf"))]


def _filename_slug(value: Any) -> str:
    raw = str(value or "").strip().replace(".", "_")
    text = re.sub(r"[^A-Za-z0-9_-]+", "-", raw)
    text = re.sub(r"-{2,}", "-", text).strip("-._")
    return text or "unknown"


def _generator_provider_slug(artifact: dict[str, Any]) -> str:
    generator = artifact.get("generator") if isinstance(artifact.get("generator"), dict) else {}
    return _filename_slug(generator.get("provider") or "unknown-provider")


def _generator_model_slug(artifact: dict[str, Any]) -> str:
    generator = artifact.get("generator") if isinstance(artifact.get("generator"), dict) else {}
    return _filename_slug(generator.get("model") or "unknown-model")


def _artifact_generator_matches(artifact: dict[str, Any], *, provider: str, model: str) -> bool:
    generator = artifact.get("generator") if isinstance(artifact.get("generator"), dict) else {}
    artifact_provider = str(generator.get("provider") or "").strip()
    artifact_model = str(generator.get("model") or "").strip()
    if not artifact_provider and not artifact_model:
        return True
    return _filename_slug(artifact_provider) == _filename_slug(provider) and _filename_slug(artifact_model) == _filename_slug(model)


def _review_pdf_prefix(artifact: dict[str, Any]) -> str:
    source_id = _artifact_source_id(artifact, fallback_output_dir=Path("source"))
    return f"{_generator_provider_slug(artifact)}-{_generator_model_slug(artifact)}--{_filename_slug(source_id)}"


def _review_pdf_filename(artifact: dict[str, Any], stem: str) -> str:
    return f"{_review_pdf_prefix(artifact)}--{stem}.pdf"


def _canonical_pdf_prefix(artifact: dict[str, Any]) -> str:
    source = artifact.get("source") if isinstance(artifact.get("source"), dict) else {}
    lecture_key = str(source.get("lecture_key") or "UNKNOWN").strip().upper() or "UNKNOWN"
    source_id = _artifact_source_id(artifact, fallback_output_dir=Path("source"))
    return f"{_filename_slug(lecture_key)}--{_filename_slug(source_id)}"


def canonical_pdf_filename(artifact: dict[str, Any], stem: str) -> str:
    return f"{_canonical_pdf_prefix(artifact)}--{stem}.pdf"


def _artifact_output_layout(artifact: dict[str, Any]) -> str:
    variant = artifact.get("variant") if isinstance(artifact.get("variant"), dict) else {}
    if str(variant.get("mode") or "").strip() == "evaluation_sandbox":
        return OUTPUT_LAYOUT_REVIEW
    return OUTPUT_LAYOUT_CANONICAL


def _output_pdf_filename(artifact: dict[str, Any], stem: str) -> str:
    if _artifact_output_layout(artifact) == OUTPUT_LAYOUT_REVIEW:
        return _review_pdf_filename(artifact, stem)
    return canonical_pdf_filename(artifact, stem)


def _output_pdf_path(output_dir: Path, artifact: dict[str, Any], stem: str) -> Path:
    return output_dir / _output_pdf_filename(artifact, stem)


def _review_pdf_path(output_dir: Path, artifact: dict[str, Any], stem: str) -> Path:
    return output_dir / _review_pdf_filename(artifact, stem)


def _artifact_pdf_paths_for_stems(output_dir: Path, artifact: dict[str, Any], stems: set[str]) -> list[Path]:
    return [_output_pdf_path(output_dir, artifact, stem) for stem in sorted(stems)]


def _expected_pdf_stems_for_artifact(artifact: dict[str, Any]) -> set[str]:
    if _artifact_schema_version(artifact) < SCHEMA_VERSION:
        return set(V2_RENDER_STEMS)
    if _exam_bridge_render_enabled(artifact):
        return set(V3_RENDER_STEMS)
    return {stem for stem in V3_RENDER_STEMS if stem != "05-exam-bridge"}


def _existing_pdf_paths_for_artifact(
    output_dir: Path,
    artifact: dict[str, Any],
    *,
    stems: set[str] | None = None,
) -> list[str]:
    expected_stems = stems or {stem for stem in V3_RENDER_STEMS + V3_LEGACY_RENDER_STEMS + V2_RENDER_STEMS}
    return [
        str(path)
        for path in _artifact_pdf_paths_for_stems(output_dir, artifact, expected_stems)
        if path.exists() and path.is_file()
    ]


def _artifact_source_id(artifact: dict[str, Any], *, fallback_output_dir: Path) -> str:
    source = artifact.get("source") if isinstance(artifact.get("source"), dict) else {}
    source_id = str(source.get("source_id") or "").strip()
    if source_id:
        return source_id
    metadata = artifact.get("metadata") if isinstance(artifact.get("metadata"), dict) else {}
    source_id = str(metadata.get("source_id") or "").strip()
    if source_id:
        return source_id
    return fallback_output_dir.name


def _internal_markdown_dir_for_artifact(output_dir: Path, artifact: dict[str, Any]) -> Path:
    source_id = _artifact_source_id(artifact, fallback_output_dir=output_dir)
    if _artifact_output_layout(artifact) == OUTPUT_LAYOUT_CANONICAL:
        return output_dir / CANONICAL_PRINTOUT_JSON_DIRNAME / _filename_slug(source_id) / "rendered_markdown"
    generator = artifact.get("generator") if isinstance(artifact.get("generator"), dict) else {}
    provider = str(generator.get("provider") or "").strip()
    model = str(generator.get("model") or "").strip()
    if provider and model:
        return artifact_dir_for_source_id(
            output_dir,
            source_id=source_id,
            provider=provider,
            model=model,
        ) / "rendered_markdown"
    return output_dir / INTERNAL_REVIEW_ARTIFACT_DIRNAME / source_id / "rendered_markdown"


def _internal_pdf_staging_parent_for_artifact(output_dir: Path, artifact: dict[str, Any]) -> Path:
    source_id = _artifact_source_id(artifact, fallback_output_dir=output_dir)
    if _artifact_output_layout(artifact) == OUTPUT_LAYOUT_CANONICAL:
        return output_dir / CANONICAL_PRINTOUT_JSON_DIRNAME / _filename_slug(source_id) / PDF_STAGING_DIRNAME
    generator = artifact.get("generator") if isinstance(artifact.get("generator"), dict) else {}
    provider = str(generator.get("provider") or "").strip()
    model = str(generator.get("model") or "").strip()
    if provider and model:
        return artifact_dir_for_source_id(
            output_dir,
            source_id=source_id,
            provider=provider,
            model=model,
        ) / PDF_STAGING_DIRNAME
    return output_dir / INTERNAL_REVIEW_ARTIFACT_DIRNAME / source_id / PDF_STAGING_DIRNAME


def _remove_empty_dir(path: Path) -> None:
    try:
        path.rmdir()
    except OSError:
        return


def _remove_output_pdf_files(output_dir: Path, artifact: dict[str, Any], *, stems: set[str] | None = None) -> None:
    if not output_dir.exists():
        return
    expected_stems = stems or {stem for stem in V3_RENDER_STEMS + V3_LEGACY_RENDER_STEMS + V2_RENDER_STEMS}
    for path in _artifact_pdf_paths_for_stems(output_dir, artifact, expected_stems):
        if path.exists() and path.is_file():
            path.unlink()


def _remove_output_markdown_files(output_dir: Path) -> None:
    if not output_dir.exists():
        return
    for path in output_dir.glob("*.md"):
        if path.is_file():
            path.unlink()


def _remove_output_json_files(output_dir: Path) -> None:
    if not output_dir.exists():
        return
    for path in output_dir.glob("*.json"):
        if path.is_file():
            path.unlink()


def _remove_stale_v3_output_files(output_dir: Path, artifact: dict[str, Any], *, expected_stems: set[str]) -> None:
    if not output_dir.exists():
        return
    known_stems = set(V3_RENDER_STEMS) | set(V3_LEGACY_RENDER_STEMS) | set(V2_RENDER_STEMS)
    stale_stems = known_stems - expected_stems
    for path in _artifact_pdf_paths_for_stems(output_dir, artifact, stale_stems):
        if path.exists() and path.is_file():
            path.unlink()


def _remove_stale_v3_markdown_files(markdown_output_dir: Path, *, expected_stems: set[str]) -> None:
    if not markdown_output_dir.exists():
        return
    known_stems = set(V3_RENDER_STEMS) | set(V3_LEGACY_RENDER_STEMS)
    for path in markdown_output_dir.iterdir():
        if not path.is_file() or path.suffix != ".md":
            continue
        if path.stem in known_stems and path.stem not in expected_stems:
            path.unlink()


def _artifact_schema_version(artifact: dict[str, Any]) -> int:
    try:
        return int(artifact.get("schema_version") or 0)
    except (TypeError, ValueError):
        return 0


def _validate_staged_pdf(path: Path) -> None:
    if not path.exists() or not path.is_file():
        raise PrintoutError(f"staged PDF was not created: {path}")
    if path.stat().st_size <= 0:
        raise PrintoutError(f"staged PDF is empty: {path}")


def _commit_staged_pdf_bundle(
    *,
    output_dir: Path,
    artifact: dict[str, Any],
    staged_pdf_paths: dict[str, Path],
    expected_stems: set[str],
    known_pdf_stems: set[str],
) -> list[str]:
    missing_stems = sorted(expected_stems - set(staged_pdf_paths))
    if missing_stems:
        raise PrintoutError("rendered PDF bundle is incomplete: missing " + ", ".join(missing_stems))
    for stem in sorted(expected_stems):
        _validate_staged_pdf(staged_pdf_paths[stem])

    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_paths: list[str] = []
    for stem in sorted(expected_stems):
        target_path = _output_pdf_path(output_dir, artifact, stem)
        staged_pdf_paths[stem].replace(target_path)
        pdf_paths.append(str(target_path))

    stale_stems = known_pdf_stems - expected_stems
    for path in _artifact_pdf_paths_for_stems(output_dir, artifact, stale_stems):
        if path.exists() and path.is_file():
            path.unlink()
    return pdf_paths


def render_printout_files(*, artifact: dict[str, Any], output_dir: Path, render_pdf: bool = True) -> dict[str, list[str]]:
    if _artifact_schema_version(artifact) < SCHEMA_VERSION:
        return render_v2_printout_files(artifact=artifact, output_dir=output_dir, render_pdf=render_pdf)
    return render_v3_printout_files(artifact=artifact, output_dir=output_dir, render_pdf=render_pdf)


def render_v2_printout_files(*, artifact: dict[str, Any], output_dir: Path, render_pdf: bool = True) -> dict[str, list[str]]:
    scaffolds = artifact.get("scaffolds") if isinstance(artifact.get("scaffolds"), dict) else {}
    markdown_items = [
        ("01-abridged-guide", render_abridged_markdown(artifact, scaffolds.get("abridged_guide", {}))),
        ("02-unit-test-suite", render_unit_test_markdown(artifact, scaffolds.get("unit_test_suite", {}))),
        ("03-cloze-scaffold", render_cloze_markdown(artifact, scaffolds.get("cloze_scaffold", {}))),
    ]
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_output_dir = _internal_markdown_dir_for_artifact(output_dir, artifact)
    markdown_paths: list[str] = []
    pdf_paths: list[str] = []
    known_pdf_stems = {stem for stem, _ in markdown_items} | set(V2_RENDER_STEMS)
    if render_pdf:
        preflight_render_toolchain()
        _remove_output_markdown_files(output_dir)
        _remove_output_json_files(output_dir)
        staging_parent = _internal_pdf_staging_parent_for_artifact(output_dir, artifact)
        staging_parent.mkdir(parents=True, exist_ok=True)
        try:
            with tempfile.TemporaryDirectory(prefix="pdf-bundle-", dir=staging_parent) as temp_dir_str:
                temp_dir = Path(temp_dir_str)
                staged_pdf_paths: dict[str, Path] = {}
                for stem, markdown in markdown_items:
                    markdown_path = temp_dir / f"{stem}.md"
                    write_text(markdown_path, markdown)
                    pdf_path = temp_dir / _output_pdf_filename(artifact, stem)
                    markdown_to_pdf(markdown_path, pdf_path)
                    staged_pdf_paths[stem] = pdf_path
                pdf_paths = _commit_staged_pdf_bundle(
                    output_dir=output_dir,
                    artifact=artifact,
                    staged_pdf_paths=staged_pdf_paths,
                    expected_stems={stem for stem, _ in markdown_items},
                    known_pdf_stems=known_pdf_stems,
                )
        finally:
            _remove_empty_dir(staging_parent)
    else:
        _remove_output_markdown_files(output_dir)
        _remove_output_json_files(output_dir)
        _remove_output_pdf_files(output_dir, artifact, stems=known_pdf_stems)
        markdown_output_dir.mkdir(parents=True, exist_ok=True)
        for stem, markdown in markdown_items:
            markdown_path = markdown_output_dir / f"{stem}.md"
            write_text(markdown_path, markdown)
            markdown_paths.append(str(markdown_path))
    return {"markdown_paths": markdown_paths, "pdf_paths": pdf_paths}


def render_v3_printout_files(*, artifact: dict[str, Any], output_dir: Path, render_pdf: bool = True) -> dict[str, list[str]]:
    scaffolds = artifact.get("printouts") if isinstance(artifact.get("printouts"), dict) else {}
    if not scaffolds:
        scaffolds = artifact.get("scaffolds") if isinstance(artifact.get("scaffolds"), dict) else {}
    markdown_items = [
        ("00-cover", render_compendium_cover_markdown(artifact)),
        ("01-reading-guide", render_reading_guide_markdown(artifact, scaffolds.get("reading_guide", {}))),
        ("02-active-reading", render_active_reading_markdown(artifact, scaffolds.get("active_reading", {}))),
        ("03-abridged-version", render_abridged_reader_markdown(artifact, scaffolds.get("abridged_reader", {}))),
        ("04-consolidation-sheet", render_consolidation_markdown(artifact, scaffolds.get("consolidation_sheet", {}))),
    ]
    if _exam_bridge_render_enabled(artifact):
        markdown_items.append(("05-exam-bridge", render_exam_bridge_markdown(artifact, scaffolds.get("exam_bridge", {}))))
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_output_dir = _internal_markdown_dir_for_artifact(output_dir, artifact)
    markdown_paths: list[str] = []
    pdf_paths: list[str] = []
    expected_stems = {stem for stem, _ in markdown_items}
    known_pdf_stems = expected_stems | set(V3_RENDER_STEMS) | set(V3_LEGACY_RENDER_STEMS) | set(V2_RENDER_STEMS)
    if render_pdf:
        preflight_render_toolchain()
        _remove_output_markdown_files(output_dir)
        _remove_output_json_files(output_dir)
        staging_parent = _internal_pdf_staging_parent_for_artifact(output_dir, artifact)
        staging_parent.mkdir(parents=True, exist_ok=True)
        try:
            with tempfile.TemporaryDirectory(prefix="pdf-bundle-", dir=staging_parent) as temp_dir_str:
                temp_dir = Path(temp_dir_str)
                staged_pdf_paths: dict[str, Path] = {}
                for stem, markdown in markdown_items:
                    markdown_path = temp_dir / f"{stem}.md"
                    write_text(markdown_path, markdown)
                    pdf_path = temp_dir / _output_pdf_filename(artifact, stem)
                    markdown_to_pdf(markdown_path, pdf_path)
                    staged_pdf_paths[stem] = pdf_path
                pdf_paths = _commit_staged_pdf_bundle(
                    output_dir=output_dir,
                    artifact=artifact,
                    staged_pdf_paths=staged_pdf_paths,
                    expected_stems=expected_stems,
                    known_pdf_stems=known_pdf_stems,
                )
        finally:
            _remove_empty_dir(staging_parent)
    else:
        _remove_stale_v3_output_files(output_dir, artifact, expected_stems=expected_stems)
        _remove_output_markdown_files(output_dir)
        _remove_output_json_files(output_dir)
        _remove_output_pdf_files(output_dir, artifact, stems=known_pdf_stems)
        markdown_output_dir.mkdir(parents=True, exist_ok=True)
        _remove_stale_v3_markdown_files(markdown_output_dir, expected_stems=expected_stems)
        for stem, markdown in markdown_items:
            markdown_path = markdown_output_dir / f"{stem}.md"
            write_text(markdown_path, markdown)
            markdown_paths.append(str(markdown_path))
    return {"markdown_paths": markdown_paths, "pdf_paths": pdf_paths}


def _sync_and_cleanup_legacy_aliases(*, canonical_out_dir: Path, legacy_out_dir: Path, render_pdf: bool) -> None:
    del render_pdf
    _cleanup_legacy_review_dirs(output_root=legacy_out_dir.parents[2], legacy_dirs=[legacy_out_dir])
    _remove_output_markdown_files(canonical_out_dir)


def render_v3_printout_files_old_removed_marker() -> None:
    return None


def _source_id_from_source(source: dict[str, Any]) -> str:
    return str(source.get("source_id") or "").strip()


def _reading_title_from_source(source: dict[str, Any]) -> str:
    source_id = _source_id_from_source(source)
    explicit_title = (
        source.get("reading_title")
        or source.get("document_title")
        or source.get("full_title")
        or READING_TITLE_OVERRIDES.get(source_id)
    )
    return str(explicit_title or source.get("title") or "Ukendt kilde").strip()


def _source_heading(artifact: dict[str, Any]) -> str:
    source = artifact.get("source") if isinstance(artifact.get("source"), dict) else {}
    title = _reading_title_from_source(source)
    lecture_key = str(source.get("lecture_key") or "").strip()
    return f"**Kilde:** {title}\n\n**Forelæsning:** {lecture_key}"


def _as_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _as_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _compendium_cover_items(artifact: dict[str, Any]) -> list[str]:
    items = [
        _fixed_v3_title("reading_guide"),
        _fixed_v3_title("active_reading"),
        _fixed_v3_title("abridged_reader"),
        _fixed_v3_title("consolidation_sheet"),
    ]
    if _exam_bridge_render_enabled(artifact):
        items.append(_fixed_v3_title("exam_bridge"))
    return items


def render_compendium_cover_markdown(artifact: dict[str, Any]) -> str:
    source = artifact.get("source") if isinstance(artifact.get("source"), dict) else {}
    source_title = _reading_title_from_source(source)
    lecture_key = str(source.get("lecture_key") or "").strip()
    lecture_label = _format_margin_lecture_key(lecture_key)
    contents = _compendium_cover_items(artifact)

    lines = [
        f"<!-- printout-title: {_fixed_v3_title('cover')} -->",
        f"<!-- printout-source: {source_title} -->",
        f"<!-- printout-lecture: {lecture_key} -->",
        "",
        r"\vspace*{1.8cm}",
        "",
        r"\begin{center}",
        r"{\small\texttt{personlighedspsykologi}}\\[0.55cm]",
        rf"{{\Large\textbf{{{_latex_escape_inline(_fixed_v3_title('cover'))}}}}}\\[0.32cm]",
        rf"\parbox{{0.88\linewidth}}{{\centering\Huge\textbf{{{_latex_escape_inline(source_title)}}}}}\\[0.42cm]",
        rf"{{\normalsize\texttt{{{_latex_escape_inline(lecture_label)}}}}}\\[1.00cm]",
        r"\rule{0.52\linewidth}{0.6pt}\\[0.70cm]",
    ]
    for index, item in enumerate(contents, start=1):
        escaped_item = _latex_escape_inline(item)
        lines.append(rf"{{\large\textbf{{{index}.}} {escaped_item}}}\\[0.22cm]")
    lines.extend(
        [
            r"\vfill",
            r"{\normalsize\textit{Printes i denne rækkefølge som ét kompendium.}}",
            r"\end{center}",
        ]
    )
    return "\n".join(lines)


def render_reading_guide_markdown(artifact: dict[str, Any], guide: dict[str, Any]) -> str:
    lines = [f"# {_fixed_v3_title('reading_guide')}", "", _source_heading(artifact), ""]
    paragraphs = _as_strings(guide.get("teaser_paragraphs"))
    for index, paragraph in enumerate(paragraphs, start=1):
        if paragraph.strip():
            lines.extend([_style_reading_guide_paragraph(paragraph.strip(), index), ""])
            if index < len(paragraphs):
                _append_spacing_gap(lines, "guide_paragraph_gap")
    _append_completion_footer(lines, artifact, ["læst", "1 spørgsmål valgt"])
    return "\n".join(lines)


def render_abridged_reader_markdown(artifact: dict[str, Any], reader: dict[str, Any]) -> str:
    lines = [f"# {_fixed_v3_title('abridged_reader')}", "", _source_heading(artifact), ""]
    prefix = _check_prefix(artifact)
    for index, section in enumerate(_as_dicts(reader.get("sections")), start=1):
        number = _number_label(section, index)
        heading = str(section.get("heading") or "").strip()
        source_location = _normalized_source_location(section.get("source_location") or "")
        lines.extend(["", f"## {prefix}{number}. {heading}", ""])
        if source_location:
            lines.extend([_md_mono(source_location), ""])
        for paragraph in _as_strings(section.get("explanation_paragraphs")):
            lines.extend([paragraph, ""])
        key_points = _as_strings(section.get("key_points"))
        if key_points:
            lines.extend([_md_bold("Kort sagt:"), ""])
            for item in key_points:
                lines.append(f"- {item}")
            lines.append("")
        # quote_anchors are search metadata. Showing them as standalone quotes
        # makes short fragments look like contextless source citations.
        source_passages = _as_dicts(section.get("source_passages"))
        for passage in source_passages:
            passage_block = _render_source_passage_block(passage.get("passage"), passage.get("source_location"))
            if passage_block:
                lines.extend([passage_block, ""])
    _append_completion_footer(lines, artifact, ["hele teksten læst"])
    return "\n".join(lines)


def render_active_reading_markdown(artifact: dict[str, Any], active: dict[str, Any]) -> str:
    lines = [f"# {_fixed_v3_title('active_reading')}", "", _source_heading(artifact), ""]
    solve_steps = _as_dicts(active.get("solve_steps"))
    last_index = len(solve_steps)
    prefix = _check_prefix(artifact)
    for index, item in enumerate(solve_steps, start=1):
        number = _number_label(item, index)
        prompt = str(item.get("prompt") or "").strip()
        task_type = str(item.get("task_type") or "").strip()
        answer_shape = str(item.get("answer_shape") or "").strip()
        blank_lines = int(item.get("blank_lines") or 1)
        if task_type == "decision":
            blank_lines = max(blank_lines, 3)
        lines.extend(["", fr"\printoutneedspace{{{_active_step_needspace_baselines(task_type, blank_lines)}\baselineskip}}", ""])
        label = f"{prefix}**{number}.**" if prefix else f"**{number}.**"
        lines.append(f"{label} {_style_task_prompt(prompt)}")
        if index == last_index and task_type == "short_paragraph":
            final_lines = max(blank_lines, 4)
            _append_fill_page_ruled_space(lines, line_count=final_lines)
        elif index == last_index:
            final_lines = max(blank_lines, 4 if task_type == "short_paragraph" else 3)
            _append_response_space(lines, answer_shape=answer_shape, blank_lines=final_lines, final_block=True)
        else:
            _append_response_space(lines, answer_shape=answer_shape, blank_lines=blank_lines)
        if index < last_index:
            _append_spacing_gap(lines, "active_step_gap")
        else:
            lines.append("")
    return "\n".join(lines)


def _diagram_space_cm(hint: str, diagram_count: int) -> float:
    text = str(hint or "").casefold()
    count_index = min(max(diagram_count, 1), 3) - 1
    if any(token in text for token in ("2x2", "gitter", "tabel", "fire felter", "fire felt", "fire bokse")):
        return DIAGRAM_SPACE_PROFILES_CM["grid"][count_index]
    if any(token in text for token in ("pile", "pil", "noder", "relation", "kæde")):
        return DIAGRAM_SPACE_PROFILES_CM["network"][count_index]
    return DIAGRAM_SPACE_PROFILES_CM["default"][count_index]


def render_consolidation_markdown(artifact: dict[str, Any], consolidation: dict[str, Any]) -> str:
    lines = [f"# {_fixed_v3_title('consolidation_sheet')}", "", _source_heading(artifact), ""]
    overview = _as_strings(consolidation.get("overview"))
    if overview:
        lines.extend([_md_bold("Overblik"), ""])
    for sentence in overview:
        lines.append(f"- {sentence}")
    fill_in_items = _as_dicts(consolidation.get("fill_in_sentences"))
    fill_group_open = False
    if fill_in_items:
        lines.extend(
            [
                "",
                _md_bold("Udfyld"),
                "",
                rf"\begingroup\linespread{{{PDF_CONSOLIDATION_FILL_BODY_LINE_SPREAD}}}\selectfont",
                "",
            ]
        )
        fill_group_open = True
    for index, item in enumerate(fill_in_items, start=1):
        number = _number_label(item, index)
        sentence = str(item.get("sentence") or "").strip()
        lines.extend(_render_consolidation_fill_in_sentence(number, sentence))
    if fill_group_open:
        lines.extend([r"\endgroup", ""])
    diagram_items = _as_dicts(consolidation.get("diagram_tasks"))
    diagram_count = len(diagram_items)
    if diagram_items:
        _append_spacing_gap(lines, "guide_paragraph_gap")
        if fill_in_items and diagram_count >= 2:
            lines.extend(["", r"\newpage", ""])
        lines.extend([_md_bold("Tegn"), ""])
    last_index = len(diagram_items)
    for index, item in enumerate(diagram_items, start=1):
        number = _number_label(item, index)
        dedicated_page = diagram_count >= 2
        if dedicated_page and index > 1:
            lines.extend(["", r"\newpage", "", _md_bold("Tegn"), ""])
        lines.append(f"{_md_bold('Diagram ' + number + '.')} {str(item.get('task') or '').strip()}")
        elements = _as_strings(item.get("required_elements"))
        if elements:
            lines.append("")
            for element in elements:
                lines.append(f"- {element}")
        hint = str(item.get("blank_space_hint") or "").strip()
        space_cm = _diagram_space_cm(hint, diagram_count)
        lines.append("")
        if index == last_index and diagram_count == 1:
            _append_fill_to_page_response_area(lines, minimum_cm=space_cm)
        elif dedicated_page:
            _append_fill_to_page_response_area(
                lines,
                minimum_cm=max(space_cm, _spacing_cm("diagram_dedicated_page_floor")),
            )
        else:
            inline_space_cm = min(space_cm, _spacing_cm("diagram_inline_space_ceiling"))
            lines.append(_vspace_cm(inline_space_cm))
        lines.append("")
    _append_completion_footer(lines, artifact, ["blanks udfyldt", "diagrammer lavet", "svar tjekket"])
    return "\n".join(lines)


def render_exam_bridge_markdown(artifact: dict[str, Any], exam_bridge: dict[str, Any]) -> str:
    lines = [f"# {_fixed_v3_title('exam_bridge')}", "", _source_heading(artifact), ""]
    lines.extend(["## Brug", ""])
    for item in _as_strings(exam_bridge.get("use_this_text_for")):
        lines.append(f"- {item}")
    lines.extend(["", "## Kobl", ""])
    for item in _as_dicts(exam_bridge.get("course_connections")):
        lines.append(f"- **{str(item.get('course_theme') or '').strip()}**: {str(item.get('connection') or '').strip()}")
    lines.extend(["", "## Sammenlign", ""])
    for item in _as_dicts(exam_bridge.get("comparison_targets")):
        lines.append(f"- **{str(item.get('compare_with') or '').strip()}**: {str(item.get('how_to_compare') or '').strip()}")
    lines.extend(["", "## Sig Højt", ""])
    for index, item in enumerate(_as_dicts(exam_bridge.get("exam_moves")), start=1):
        prompt_type = str(item.get("prompt_type") or "").strip().rstrip(" .")
        use_in_answer = str(item.get("use_in_answer") or "").strip().rstrip(" .")
        caution = str(item.get("caution") or "").strip().rstrip(" .")
        if prompt_type:
            lines.append(f"{index}. **{prompt_type}**")
        if use_in_answer:
            lines.append(use_in_answer)
        if caution:
            lines.append(f"{_md_bold('Undgå:')} {caution}")
        lines.append("")
    lines.extend(["", "## Fælder", ""])
    for item in _as_dicts(exam_bridge.get("misunderstanding_traps")):
        trap = str(item.get("trap") or "").strip().rstrip(" .")
        better = str(item.get("better_reading") or "").strip().rstrip(" .")
        sentence = ". ".join(part for part in [trap, better] if part)
        if sentence:
            lines.append(f"- {sentence}")
    lines.extend(["", "## Mini-eksamen", "", str(exam_bridge.get("mini_exam_prompt_question") or "").strip(), ""])
    for item in _as_strings(exam_bridge.get("mini_exam_answer_plan_slots")):
        lines.append(f"- {_md_bold(item + ':')} ______________________________")
    _append_completion_footer(lines, artifact, ["30 sek start", "2 min svar højt", "1 sammenligning lavet"])
    return "\n".join(lines)


def render_abridged_markdown(artifact: dict[str, Any], guide: dict[str, Any]) -> str:
    lines = [f"# {guide.get('title') or 'Forberedende oversigt'}", "", _source_heading(artifact), ""]
    how_to_use = str(guide.get("how_to_use") or "").strip()
    if how_to_use:
        lines.extend(["## Sådan bruger du arket", "", how_to_use, ""])
    why_this_text_matters = str(guide.get("why_this_text_matters") or "").strip()
    if why_this_text_matters:
        lines.extend(["## Hvorfor teksten er vigtig", "", why_this_text_matters, ""])
    lines.extend(["## Tre-sætningsoversigt", ""])
    for sentence in _as_strings(guide.get("overview")):
        lines.append(f"- {sentence}")
    lines.extend(["", "## Læserute", ""])
    for index, item in enumerate(_as_dicts(guide.get("structure_map")), start=1):
        number = _number_label(item, index)
        section_hint = str(item.get("section_hint") or "").strip()
        what_to_get = str(item.get("what_to_get") or "").strip()
        why_it_matters = str(item.get("why_it_matters") or "").strip()
        stop_after = str(item.get("stop_after") or "").strip()
        lines.append(f"{number}. **{section_hint}**")
        lines.append(f"   - Fang: {what_to_get}")
        lines.append(f"   - Hvorfor: {why_it_matters}")
        lines.append(f"   - Stop når: {stop_after}")
        lines.append("")
    lines.extend(["", "## Nøgleformuleringer at finde", ""])
    for item in _as_dicts(guide.get("key_quote_targets")):
        target = str(item.get("target") or "").strip()
        why = str(item.get("why") or "").strip()
        where_to_look = str(item.get("where_to_look") or "").strip()
        fragment = _quote_anchor_fragment(target)
        if not fragment:
            continue
        lines.append(f"- **Find formuleringen:** {fragment}")
        if why:
            lines.append(f"  - Hvorfor: {why}")
        if where_to_look:
            lines.append(f"  - Led efter: {where_to_look}")
    stuck_items = _as_strings(guide.get("do_not_get_stuck_on"))
    if stuck_items:
        lines.extend(["", "## Brug ikke for meget energi på", ""])
        for item in stuck_items:
            lines.append(f"- {item}")
    return "\n".join(lines)


def render_unit_test_markdown(artifact: dict[str, Any], suite: dict[str, Any]) -> str:
    lines = [f"# {suite.get('title') or 'Unit Test Suite'}", "", _source_heading(artifact), ""]
    instructions = str(suite.get("instructions") or "").strip()
    if instructions:
        lines.extend([f"*{instructions}*", ""])
    lines.extend(["## Spørgsmål i tekstens rækkefølge", ""])
    for index, item in enumerate(_as_dicts(suite.get("questions")), start=1):
        number = _number_label(item, index)
        question = str(item.get("question") or "").strip()
        where_to_look = str(item.get("where_to_look") or "").strip()
        answer_shape = str(item.get("answer_shape") or "kort svar").strip()
        done_signal = str(item.get("done_signal") or "").strip()
        lines.append(f"{number}. {question}")
        if where_to_look:
            lines.append(f"   - Led efter: {where_to_look}")
        lines.append(f"   - Svar ({answer_shape}): ______________________________")
        if done_signal:
            lines.append(f"   - Stop når: {done_signal}")
        lines.append("")
    return "\n".join(lines)


def render_cloze_markdown(artifact: dict[str, Any], cloze: dict[str, Any]) -> str:
    lines = [f"# {cloze.get('title') or 'Printout-opgaver'}", "", _source_heading(artifact), ""]
    lines.extend(["## Tre-sætningsoversigt", ""])
    for sentence in _as_strings(cloze.get("overview")):
        lines.append(f"- {sentence}")
    lines.extend(["", "## Udfyldningssætninger", ""])
    for index, item in enumerate(_as_dicts(cloze.get("fill_in_sentences")), start=1):
        number = _number_label(item, index)
        sentence = str(item.get("sentence") or "").strip()
        where_to_look = str(item.get("where_to_look") or "").strip()
        answer_shape = str(item.get("answer_shape") or "").strip()
        lines.append(f"{number}. {sentence}")
        if where_to_look or answer_shape:
            detail = " | ".join(part for part in [f"Led efter: {where_to_look}" if where_to_look else "", f"Svarform: {answer_shape}" if answer_shape else ""] if part)
            lines.append(f"   - {detail}")
        lines.append("")
    lines.extend(["", "## Tomme diagramopgaver", ""])
    diagram_items = _as_dicts(cloze.get("diagram_tasks"))
    for index, item in enumerate(diagram_items, start=1):
        number = _number_label(item, index)
        task = str(item.get("task") or "").strip()
        hint = str(item.get("blank_space_hint") or "Brug feltet nedenfor.").strip()
        space_cm = _diagram_space_cm(hint, len(diagram_items))
        lines.append(f"{number}. {task}")
        elements = _as_strings(item.get("required_elements"))
        if elements:
            lines.append("")
            lines.append("Diagrammet skal indeholde:")
            for element in elements:
                lines.append(f"- {element}")
        lines.append("")
        lines.append(f"*{hint}*")
        lines.append("")
        lines.append(_vspace_cm(space_cm))
        lines.append("")
    return "\n".join(lines)


def markdown_to_pdf(markdown_path: Path, pdf_path: Path) -> None:
    toolchain = preflight_render_toolchain()
    engine = str(toolchain["pdf_engine"])
    with tempfile.TemporaryDirectory(prefix="printout-pdf-md-") as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        raw_markdown = markdown_path.read_text(encoding="utf-8")

        def run_pandoc(*, wrapped_markdown: str, target_pdf: Path) -> None:
            temp_markdown_path = temp_dir / markdown_path.name
            temp_markdown_path.write_text(wrapped_markdown, encoding="utf-8")
            command = [
                "pandoc",
                str(temp_markdown_path),
                "-o",
                str(target_pdf),
                "-V",
                "papersize=a4",
                "-V",
                "geometry:margin=1.8cm",
                "-V",
                "fontsize=11pt",
                "--pdf-engine",
                engine,
            ]
            try:
                subprocess.run(command, check=True, capture_output=True, text=True)
            except subprocess.CalledProcessError as exc:
                detail = (exc.stderr or exc.stdout or str(exc)).strip()
                raise PrintoutError(f"pandoc failed for {markdown_path}: {detail}") from exc

        first_pass_pdf = temp_dir / "first-pass.pdf"
        run_pandoc(wrapped_markdown=_pdf_wrapped_markdown(raw_markdown), target_pdf=first_pass_pdf)
        total_pages = _pdf_page_count(first_pass_pdf)
        run_pandoc(wrapped_markdown=_pdf_wrapped_markdown(raw_markdown, total_pages=total_pages), target_pdf=pdf_path)


def _select_pdf_engine() -> str:
    for engine in PDF_RENDER_ENGINES:
        if shutil.which(engine):
            return engine
    raise PrintoutError(
        "a LaTeX PDF engine is required to render printout PDFs; install one of: "
        + ", ".join(PDF_RENDER_ENGINES)
    )


def preflight_render_toolchain(*, render_pdf: bool = True) -> dict[str, str]:
    if not render_pdf:
        return {}
    tool_paths: dict[str, str] = {}
    pandoc_path = shutil.which("pandoc")
    if not pandoc_path:
        raise PrintoutError("pandoc is required to render printout PDFs")
    tool_paths["pandoc"] = pandoc_path
    tool_paths["pdf_engine"] = _select_pdf_engine()
    pdfinfo_path = shutil.which("pdfinfo")
    if not pdfinfo_path:
        raise PrintoutError("pdfinfo is required to compute total page counts for printout PDFs")
    tool_paths["pdfinfo"] = pdfinfo_path
    return tool_paths


def build_printouts(
    *,
    repo_root: Path,
    subject_root: Path,
    source_catalog_path: Path,
    source_card_dir: Path,
    revised_lecture_substrate_dir: Path,
    course_synthesis_path: Path,
    output_root: Path,
    lecture_keys: list[str] | None = None,
    source_ids: list[str] | None = None,
    source_families: set[str] | None = None,
    model: str = DEFAULT_GEMINI_PREPROCESSING_MODEL,
    backend: GeminiPreprocessingBackend | None = None,
    json_generator: JsonGenerator | None = None,
    render_pdf: bool = True,
    force: bool = False,
    rerender_existing: bool = False,
    dry_run: bool = False,
    continue_on_error: bool = False,
    prompt_version: str = PROMPT_VERSION,
    system_instruction: str | None = None,
    user_prompt_builder: UserPromptBuilder | None = None,
    variant_metadata: dict[str, Any] | None = None,
    generation_provider: str = "gemini",
    generation_config_metadata_override: dict[str, Any] | None = None,
    output_layout: str = OUTPUT_LAYOUT_CANONICAL,
) -> dict[str, Any]:
    output_layout = _normalize_output_layout(output_layout)
    sources = select_sources(
        source_catalog_path=source_catalog_path,
        lecture_keys=lecture_keys,
        source_ids=source_ids,
        source_families=source_families,
    )
    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    if dry_run:
        return {
            "status": "planned",
            "source_count": len(sources),
            "sources": [
                {
                    "source_id": str(source.get("source_id") or ""),
                    "lecture_key": str(source.get("lecture_key") or ""),
                    "title": str(source.get("title") or ""),
                    "output_dir": str(output_dir_for_source(output_root, source, output_layout=output_layout)),
                }
                for source in sources
            ],
        }
    for source in sources:
        source_id = str(source.get("source_id") or "").strip()
        try:
            results.append(
                build_printout_for_source(
                    repo_root=repo_root,
                    subject_root=subject_root,
                    source=source,
                    source_card_dir=source_card_dir,
                    revised_lecture_substrate_dir=revised_lecture_substrate_dir,
                    course_synthesis_path=course_synthesis_path,
                    output_root=output_root,
                    model=model,
                    backend=backend,
                    json_generator=json_generator,
                    render_pdf=render_pdf,
                    force=force,
                    rerender_existing=rerender_existing,
                    prompt_version=prompt_version,
                    system_instruction=system_instruction,
                    user_prompt_builder=user_prompt_builder,
                    variant_metadata=variant_metadata,
                    generation_provider=generation_provider,
                    generation_config_metadata_override=generation_config_metadata_override,
                    output_layout=output_layout,
                )
            )
        except Exception as exc:
            errors.append({"source_id": source_id, "error": recursive.format_error(exc)})
            if not continue_on_error:
                break
    return {
        "status": "error" if errors else "ok",
        "source_count": len(sources),
        "written_count": sum(1 for item in results if item.get("status") == "written"),
        "rerendered_count": sum(1 for item in results if item.get("status") == "rerendered_existing"),
        "skipped_count": sum(1 for item in results if item.get("status") == "skipped_existing"),
        "error_count": len(errors),
        "results": results,
        "errors": errors,
    }


def parse_source_families(values: list[str], *, all_families: bool = False) -> set[str] | None:
    if all_families:
        return None
    families = {item.strip() for value in values for item in value.split(",") if item.strip()}
    return families or {"reading"}


# Legacy compatibility aliases for the renamed printout engine.
ScaffoldingError = PrintoutError
scaffold_generation_config_metadata = printout_generation_config_metadata
scaffold_system_instruction = printout_system_instruction
scaffold_user_prompt = printout_user_prompt
validate_scaffold_payload = validate_printout_payload
build_scaffold_for_source = build_printout_for_source
render_scaffold_files = render_printout_files
render_v2_scaffold_files = render_v2_printout_files
render_v3_scaffold_files = render_v3_printout_files
build_scaffolds = build_printouts
