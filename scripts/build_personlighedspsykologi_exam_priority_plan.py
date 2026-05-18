#!/usr/bin/env python3
"""Build an oral-exam printout priority plan from course intelligence artifacts."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = "shows/personlighedspsykologi-en/exam_priority_config.narrative.json"
DEFAULT_SOURCE_WEIGHTING_PATH = "shows/personlighedspsykologi-en/source_weighting.json"
DEFAULT_CONCEPT_GRAPH_PATH = "shows/personlighedspsykologi-en/course_concept_graph.json"
DEFAULT_COURSE_SYNTHESIS_PATH = "shows/personlighedspsykologi-en/source_intelligence/course_synthesis.json"
DEFAULT_REVISED_LECTURE_SUBSTRATES_DIR = "shows/personlighedspsykologi-en/source_intelligence/revised_lecture_substrates"
PLAN_VERSION = 1


def _utc_now_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _resolve(repo_root: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else repo_root / path


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json_if_changed(path: Path, payload: dict[str, Any]) -> bool:
    rendered = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == rendered:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")
    return True


def _write_text_if_changed(path: Path, text: str) -> bool:
    rendered = text.rstrip() + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == rendered:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")
    return True


def _relpath(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def _normalize_lecture_key(value: str) -> str | None:
    match = re.search(r"\bW(\d{1,2})L(\d)\b", value, flags=re.IGNORECASE)
    if not match:
        return None
    return f"W{int(match.group(1)):02d}L{int(match.group(2))}"


def _normalize_lecture_keys(value: Any) -> list[str]:
    if isinstance(value, list):
        keys: list[str] = []
        for item in value:
            keys.extend(_normalize_lecture_keys(item))
        return sorted(set(keys))
    if not isinstance(value, str):
        return []
    return sorted(
        {
            f"W{int(match.group(1)):02d}L{int(match.group(2))}"
            for match in re.finditer(r"\bW(\d{1,2})L(\d)\b", value, flags=re.IGNORECASE)
        }
    )


def _as_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _flatten_text(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_flatten_text(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_flatten_text(item) for item in value)
    if value is None:
        return ""
    return str(value)


def _lecture_sort_key(lecture_key: str) -> tuple[int, int]:
    match = re.match(r"^W(\d{2})L(\d)$", lecture_key)
    if not match:
        return (999, 999)
    return (int(match.group(1)), int(match.group(2)))


def _source_title(source: dict[str, Any]) -> str:
    return str(source.get("title") or source.get("source_title") or source.get("source_id") or "").strip()


def _short_title(title: str, max_len: int = 62) -> str:
    title = " ".join(title.split())
    if len(title) <= max_len:
        return title
    return title[: max_len - 1].rstrip() + "..."


def _course_priority_index(course_synthesis: dict[str, Any]) -> dict[str, dict[str, int]]:
    index: dict[str, dict[str, int]] = defaultdict(lambda: {"top_down": 0, "sideways": 0})
    analysis = course_synthesis.get("analysis") if isinstance(course_synthesis.get("analysis"), dict) else {}
    for item in analysis.get("top_down_priorities", []):
        if not isinstance(item, dict):
            continue
        for lecture_key in _normalize_lecture_keys(item.get("lecture_keys")):
            index[lecture_key]["top_down"] += 1
    for relation in analysis.get("sideways_relations", []):
        if not isinstance(relation, dict):
            continue
        for field in ("from", "to"):
            for lecture_key in _normalize_lecture_keys(relation.get(field)):
                index[lecture_key]["sideways"] += 1
    return index


def _load_lecture_contexts(substrates_dir: Path) -> dict[str, dict[str, Any]]:
    contexts: dict[str, dict[str, Any]] = {}
    if not substrates_dir.exists():
        return contexts
    for path in sorted(substrates_dir.glob("W??L?.json")):
        payload = _load_json(path)
        lecture_key = _normalize_lecture_key(path.stem) or _normalize_lecture_key(_flatten_text(payload.get("lecture")))
        if lecture_key:
            contexts[lecture_key] = payload
    return contexts


def _score_lecture_context(
    lecture_key: str,
    lecture_contexts: dict[str, dict[str, Any]],
    keyword_bonus: dict[str, Any],
    cap: int,
) -> tuple[int, list[str]]:
    payload = lecture_contexts.get(lecture_key)
    if not payload:
        return 0, []
    text = _flatten_text(payload.get("analysis")).casefold()
    matched: list[str] = []
    score = 0
    for keyword, raw_bonus in keyword_bonus.items():
        if str(keyword).casefold() in text:
            matched.append(str(keyword))
            score += int(raw_bonus)
    return min(score, cap), matched


def _distinction_indexes(concept_graph: dict[str, Any]) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_lecture: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for distinction in concept_graph.get("distinctions", []):
        if not isinstance(distinction, dict):
            continue
        for source_id in _as_string_list(distinction.get("supporting_source_ids")):
            by_source[source_id].append(distinction)
        for lecture_key in _normalize_lecture_keys(distinction.get("lecture_keys")):
            by_lecture[lecture_key].append(distinction)
    return by_source, by_lecture


def _matched_weighted_values(ids: list[str], weights: dict[str, Any]) -> tuple[int, list[dict[str, Any]]]:
    matches: list[dict[str, Any]] = []
    total = 0
    for item_id in ids:
        if item_id not in weights:
            continue
        value = int(weights[item_id])
        total += value
        matches.append({"id": item_id, "score": value})
    matches.sort(key=lambda item: (-int(item["score"]), str(item["id"])))
    return total, matches


def score_source(
    source: dict[str, Any],
    *,
    config: dict[str, Any],
    concept_graph: dict[str, Any],
    course_priority_by_lecture: dict[str, dict[str, int]],
    lecture_contexts: dict[str, dict[str, Any]],
    distinctions_by_source: dict[str, list[dict[str, Any]]],
    distinctions_by_lecture: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    weights = config["score_weights"]
    lecture_key = str(source.get("lecture_key") or "").strip()
    source_id = str(source.get("source_id") or "").strip()
    term_ids = _as_string_list(source.get("term_ids"))
    theory_ids = _as_string_list(source.get("theory_ids"))
    weight_score = int(source.get("weight_score") or 0)
    weight_band = str(source.get("weight_band") or "").strip()
    length_band = str(source.get("length_band") or "unknown").strip() or "unknown"

    weight_band_score = int(weights.get("weight_band_bonus", {}).get(weight_band, 0))
    theory_score, matched_theories = _matched_weighted_values(theory_ids, weights.get("theory_bonus", {}))
    term_score, matched_terms = _matched_weighted_values(term_ids, weights.get("term_bonus", {}))
    lecture_role_score = int(weights.get("lecture_role_bonus", {}).get(lecture_key, 0))

    distinction_bonus = weights.get("distinction_bonus", {})
    direct_distinction_score = 0
    direct_distinctions: list[dict[str, Any]] = []
    for distinction in distinctions_by_source.get(source_id, []):
        distinction_id = str(distinction.get("distinction_id") or "")
        value = int(distinction_bonus.get(distinction_id, int(distinction.get("importance") or 1) * 10))
        direct_distinction_score += value
        direct_distinctions.append(
            {
                "distinction_id": distinction_id,
                "label": str(distinction.get("label") or "").strip(),
                "score": value,
            }
        )
    direct_distinctions.sort(key=lambda item: (-int(item["score"]), str(item["label"])))

    context_multiplier = int(weights.get("lecture_distinction_context_multiplier", 0))
    lecture_distinction_score = 0
    lecture_distinctions: list[dict[str, Any]] = []
    for distinction in distinctions_by_lecture.get(lecture_key, []):
        distinction_id = str(distinction.get("distinction_id") or "")
        value = int(distinction.get("importance") or 1) * context_multiplier
        lecture_distinction_score += value
        lecture_distinctions.append(
            {
                "distinction_id": distinction_id,
                "label": str(distinction.get("label") or "").strip(),
                "score": value,
            }
        )

    course_priority = course_priority_by_lecture.get(lecture_key, {})
    course_priority_score = int(course_priority.get("top_down", 0)) * int(weights.get("course_priority_bonus", 0))
    sideways_relation_score = int(course_priority.get("sideways", 0)) * int(weights.get("sideways_relation_bonus", 0))
    lecture_context_score, lecture_context_keywords = _score_lecture_context(
        lecture_key,
        lecture_contexts,
        weights.get("lecture_context_keyword_bonus", {}),
        int(weights.get("lecture_context_bonus_cap", 0)),
    )
    time_cost = int(weights.get("length_cost", {}).get(length_band, weights.get("length_cost", {}).get("unknown", 0)))

    academic_breakdown = {
        "source_weight": weight_score,
        "weight_band_bonus": weight_band_score,
        "theory_bonus": theory_score,
        "term_bonus": term_score,
        "lecture_role_bonus": lecture_role_score,
        "direct_distinction_bonus": direct_distinction_score,
        "lecture_distinction_context_bonus": lecture_distinction_score,
        "course_priority_bonus": course_priority_score,
        "sideways_relation_bonus": sideways_relation_score,
        "lecture_context_bonus": lecture_context_score,
    }
    academic_score = sum(academic_breakdown.values())
    evidence = build_evidence(
        source=source,
        matched_theories=matched_theories,
        matched_terms=matched_terms,
        direct_distinctions=direct_distinctions,
        lecture_context_keywords=lecture_context_keywords,
    )
    return {
        "source_id": source_id,
        "lecture_key": lecture_key,
        "lecture_title": str(source.get("lecture_title") or "").strip(),
        "title": _source_title(source),
        "source_family": str(source.get("source_family") or "").strip(),
        "weight_score": weight_score,
        "weight_band": weight_band,
        "priority_band": str(source.get("priority_band") or "").strip(),
        "length_band": length_band,
        "term_ids": term_ids,
        "theory_ids": theory_ids,
        "academic_score": academic_score,
        "time_cost": time_cost,
        "academic_breakdown": academic_breakdown,
        "matched_theories": matched_theories,
        "matched_terms": matched_terms,
        "direct_distinctions": direct_distinctions,
        "lecture_distinctions": lecture_distinctions,
        "lecture_context_keywords": lecture_context_keywords,
        "evidence": evidence,
    }


def build_evidence(
    *,
    source: dict[str, Any],
    matched_theories: list[dict[str, Any]],
    matched_terms: list[dict[str, Any]],
    direct_distinctions: list[dict[str, Any]],
    lecture_context_keywords: list[str],
) -> list[str]:
    evidence = [
        f"{source.get('weight_band')} ({source.get('weight_score')} i kildevægtning)",
    ]
    if matched_theories:
        evidence.append("teori: " + ", ".join(item["id"] for item in matched_theories[:3]))
    if matched_terms:
        evidence.append("begreb: " + ", ".join(item["id"] for item in matched_terms[:3]))
    if direct_distinctions:
        evidence.append("distinktion: " + ", ".join(item["label"] for item in direct_distinctions[:2]))
    if lecture_context_keywords:
        evidence.append("lektionssignal: " + ", ".join(lecture_context_keywords[:3]))
    return evidence


def _assign_bucket(record: dict[str, Any], config: dict[str, Any]) -> str:
    context = config.get("exam_context", {})
    rules = config.get("bucket_rules", {})
    already_covered = set(_as_string_list(context.get("already_covered_lecture_keys")))
    baseline_lectures = set(_as_string_list(rules.get("baseline_lecture_keys")))
    academic = int(record["academic_score"])
    lecture_key = str(record["lecture_key"])

    if lecture_key in already_covered:
        return "already_covered"
    if lecture_key in baseline_lectures:
        return "contrast_baseline"
    if academic >= int(rules.get("start_here_academic_threshold", 0)):
        return "start_here"
    if academic >= int(rules.get("read_after_academic_threshold", 0)):
        return "read_after"
    if academic >= int(rules.get("overview_academic_threshold", 0)):
        return "expand_if_time"
    if academic >= int(rules.get("overview_academic_threshold", 0)) - 40:
        return "bridge_overview"
    return "deprioritized"


def _bucket_sort_key(bucket_key: str, record: dict[str, Any]) -> tuple[int, int, tuple[int, int], str]:
    primary = int(record["academic_score"])
    return (-primary, -int(record["academic_score"]), _lecture_sort_key(str(record["lecture_key"])), str(record["title"]).casefold())


def _limited_buckets(records: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    rules = config.get("bucket_rules", {})
    limits = rules.get("limits") if isinstance(rules.get("limits"), dict) else {}
    max_per_lecture = rules.get("max_per_lecture") if isinstance(rules.get("max_per_lecture"), dict) else {}
    bucket_keys = [
        "start_here",
        "read_after",
        "expand_if_time",
        "contrast_baseline",
        "bridge_overview",
        "already_covered",
        "deprioritized",
    ]
    buckets: dict[str, list[dict[str, Any]]] = {}
    for bucket_key in bucket_keys:
        candidates = [record for record in records if record["bucket"] == bucket_key]
        candidates.sort(key=lambda record: _bucket_sort_key(bucket_key, record))
        limit = int(limits.get(bucket_key, 999))
        per_lecture_limit = int(max_per_lecture.get(bucket_key, 999))
        lecture_counts: Counter[str] = Counter()
        selected: list[dict[str, Any]] = []
        for record in candidates:
            if len(selected) >= limit:
                break
            lecture_key = str(record["lecture_key"])
            if lecture_counts[lecture_key] >= per_lecture_limit:
                continue
            selected.append(record)
            lecture_counts[lecture_key] += 1
        buckets[bucket_key] = selected
    return buckets


def build_exam_priority_plan(
    *,
    repo_root: Path,
    config_path: Path,
    source_weighting_path: Path,
    concept_graph_path: Path,
    course_synthesis_path: Path,
    lecture_substrates_dir: Path,
    generated_at: str | None = None,
) -> dict[str, Any]:
    config = _load_json(config_path)
    source_weighting = _load_json(source_weighting_path)
    concept_graph = _load_json(concept_graph_path)
    course_synthesis = _load_json(course_synthesis_path)
    course_priority_by_lecture = _course_priority_index(course_synthesis)
    lecture_contexts = _load_lecture_contexts(lecture_substrates_dir)
    distinctions_by_source, distinctions_by_lecture = _distinction_indexes(concept_graph)

    records: list[dict[str, Any]] = []
    for source in source_weighting.get("sources", []):
        if not isinstance(source, dict):
            continue
        if source.get("source_family") != "reading":
            continue
        if int(source.get("weight_score") or 0) <= 0:
            continue
        source_id = str(source.get("source_id") or "").strip()
        if not source_id:
            continue
        record = score_source(
            source,
            config=config,
            concept_graph=concept_graph,
            course_priority_by_lecture=course_priority_by_lecture,
            lecture_contexts=lecture_contexts,
            distinctions_by_source=distinctions_by_source,
            distinctions_by_lecture=distinctions_by_lecture,
        )
        records.append(record)

    records.sort(key=lambda record: (-int(record["academic_score"]), str(record["source_id"])))
    for index, record in enumerate(records, start=1):
        record["academic_rank"] = index
    records.sort(key=lambda record: (-int(record["academic_score"]), str(record["source_id"])))
    for index, record in enumerate(records, start=1):
        record["action_rank"] = index
        record["bucket"] = _assign_bucket(record, config)

    buckets = _limited_buckets(records, config)
    public_buckets = {
        bucket: [_public_record(record) for record in bucket_records]
        for bucket, bucket_records in buckets.items()
    }
    public_records = [_public_record(record) for record in sorted(records, key=lambda record: int(record["academic_rank"]))]
    return {
        "schema_version": PLAN_VERSION,
        "generated_at": generated_at or _utc_now_iso(),
        "subject_slug": "personlighedspsykologi",
        "config_path": _relpath(config_path, repo_root),
        "exam_context": config.get("exam_context", {}),
        "inputs": {
            "source_weighting": _relpath(source_weighting_path, repo_root),
            "course_concept_graph": _relpath(concept_graph_path, repo_root),
            "course_synthesis": _relpath(course_synthesis_path, repo_root),
            "revised_lecture_substrates_dir": _relpath(lecture_substrates_dir, repo_root),
        },
        "method": {
            "academic_score": "source_weight + band bonus + theory/term relevance + distinction support + course synthesis + lecture-context signals",
            "visible_order": "The visible plan is ordered by academic priority and relative study phase.",
            "score_weights": config.get("score_weights", {}),
            "bucket_rules": config.get("bucket_rules", {}),
        },
        "stats": {
            "source_count": len(records),
        },
        "buckets": {bucket: [record["source_id"] for record in bucket_records] for bucket, bucket_records in public_buckets.items()},
        "bucket_records": public_buckets,
        "records": public_records,
        "start_here_source_ids": [record["source_id"] for record in public_buckets["start_here"]],
    }


def _public_record(record: dict[str, Any]) -> dict[str, Any]:
    return dict(record)


def _record_table(records: list[dict[str, Any]], *, include_action: bool = True) -> str:
    if not records:
        return "_Ingen tekster i denne kategori._"
    headers = ["Prioritet", "Tekst", "Faglig score", "Hvorfor"]
    rows = ["| " + " | ".join(headers) + " |", "|---|---|---:|---|"]
    for index, record in enumerate(records, start=1):
        score = f"{record['academic_score']}"
        why = "; ".join(record["evidence"][:4])
        rows.append(
            "| "
            + " | ".join(
                [
                    str(index),
                    f"{record['lecture_key']}: {_source_title(record)}",
                    score,
                    why.replace("|", "/"),
                ]
            )
            + " |"
        )
    return "\n".join(rows)


def render_markdown(plan: dict[str, Any]) -> str:
    context = plan["exam_context"]
    buckets = plan["bucket_records"]
    days = context.get("available_reading_days", 12)
    return "\n\n".join(
        [
            "# Prioriteret printoutlæsning til mundtlig eksamen",
            (
                "Denne fil opdateres af "
                "`scripts/build_personlighedspsykologi_exam_priority_plan.py`. "
                "Den dokumenterer både planen og den præcise vurderingsmetode, så "
                    "prioriteringen kan genberegnes, når kursusartefakterne ændrer sig."
            ),
            "Der bruges ingen faste kalenderdatoer. Arbejd i relative læsedage og prioritetspakker.",
            "## Implementeret plan",
            (
                "Målet er at prioritere ikke-narrative tekster, fordi narrativ psykologi "
                "allerede er gennemgået. W11L2 bevares som eksamensanker i datasættet, "
                "men fjernes fra aktiv ny-læsning."
            ),
            (
                "Pipeline-designet løser den vigtigste svaghed i den tidligere manuelle plan: "
                "prioriteringen styres af faglig eksamensværdi frem for om et materiale allerede "
                "findes i en bestemt teknisk outputform. Derfor viser planen kun hvornår en tekst "
                "bør ind i læsearbejdet."
            ),
            "## Datagrundlag",
            "\n".join(
                [
                    f"- `{path}`"
                    for path in [
                        plan["config_path"],
                        plan["inputs"]["source_weighting"],
                        plan["inputs"]["course_concept_graph"],
                        plan["inputs"]["course_synthesis"],
                        plan["inputs"]["revised_lecture_substrates_dir"],
                    ]
                ]
            ),
            "## Vurderingsmetode",
            "\n".join(
                [
                    "For hver læsetekst beregnes én synlig prioritetsscore:",
                    "",
                    "- `academic_score`: kildevægtning, anchor/major-status, teori- og begrebsrelevans, distinktionsstøtte, kursussyntese og revised lecture-substrate signaler.",
                    "",
                    "Den synlige plan bruger derfor faglig prioritet og relativ læserytme."
                ]
            ),
            "## Scorekomponenter",
            "\n".join(
                [
                    "- `source_weight`: eksisterende repo-vægtning fra `source_weighting.json`.",
                    "- `theory_bonus` og `term_bonus`: narrativ relevans, socialkonstruktionisme, subjektivering, kritisk psykologi, mening, historicitet og baseline-kontraster.",
                    "- `direct_distinction_bonus`: støtte til centrale mundtlige akser i `course_concept_graph.json`.",
                    "- `lecture_context_bonus`: signaler som `narrative psychology`, `subjectivation`, `historicity`, `agency`, `discourse` og `deconstruction` i revised lecture substrates.",
                ]
            ),
            "## Start her",
            (
                "Disse tekster har størst eksamensværdi for at kunne tale om narrativ "
                "psykologi gennem kontrast, forudsætning og metaperspektiv."
            ),
            _record_table(buckets["start_here"]),
            "## Læs derefter",
            (
                "Disse tekster kommer lige efter startpakken og udbygger praksis, "
                "agens, historicitet, erfaring og kritisk sammenligning."
            ),
            _record_table(buckets["read_after"]),
            "## Udbyg hvis der er tid",
            "Disse tekster er stadig relevante, men bør først tages efter de to første faser.",
            _record_table(buckets["expand_if_time"]),
            "## Kontrastbaseline",
            (
                "Tidlige træk-, assessment- og biosociale tekster skal primært bruges som "
                "kontrast til narrativ psykologi, ikke som dybdelæsningskerne."
            ),
            _record_table(buckets["contrast_baseline"]),
            "## Bro- og overblikstekster",
            (
                "Disse tekster har faglig værdi, men bør læses selektivt eller efter de "
                "højere prioriterede kategorier."
            ),
            _record_table(buckets["bridge_overview"]),
            "## Allerede dækket eksamensanker",
            (
                "Narrative tekster holdes synlige som sammenligningsanker, men de er ikke "
                "en ny læseopgave i denne plan."
            ),
            _record_table(buckets["already_covered"], include_action=False),
            "## Relativ læserytme",
            "\n".join(
                [
                    f"Brug {days} relative læsedage uden faste datoer:",
                    "",
                    "| Læsedage | Fokus | Output |",
                    "|---|---|---|",
                    "| 1-3 | Start her | De stærkeste broer og kontraster til narrativ psykologi |",
                    "| 4-6 | Læs derefter | Sammenligningsmatrix mod narrativ psykologi |",
                    "| 7-8 | Udbyg hvis der er tid | Agens/praksis/mening koblet til de fire orienteringspunkter |",
                    "| 9 | Kontrastbaseline | Træk, stabilitet og assessment som modpol |",
                    "| 10 | Bro- og overblikstekster | Fyld svage huller uden perfektionisme |",
                    "| 11 | Mundtlig syntese | Tre stærke sammenligninger på tværs af teorier |",
                    "| 12 | Prøvefremlæggelse | 8-10 minutters svar med narrativ psykologi som centrum |",
                ]
            ),
            "## Reproducerbarhed",
            "\n".join(
                [
                    "Genskab planen med:",
                    "",
                    "```bash",
                    "python3 scripts/build_personlighedspsykologi_exam_priority_plan.py",
                    "```",
                    "",
                    "Spring rendering af onepage-PDF'en over med:",
                    "",
                    "```bash",
                    "python3 scripts/build_personlighedspsykologi_exam_priority_plan.py --no-pdf",
                    "```",
                ]
            ),
        ]
    )


def _latex_escape(value: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in value)


def _tex_item(record: dict[str, Any]) -> str:
    title = _latex_escape(_short_title(f"{record['lecture_key']} {record['title']}", 50))
    score = f"A{record['academic_rank']}"
    return rf"\readingitem{{{title}}}{{{score}}}"


def _tex_plain_records(records: list[dict[str, Any]], limit: int = 5) -> str:
    lines = []
    for record in records[:limit]:
        label = _latex_escape(_short_title(f"{record['lecture_key']} {record['title']}", 54))
        lines.append(rf"\plainitem{{{label}}}")
    return "\n".join(lines) if lines else r"\plainitem{Ingen tekster i kategorien.}"


def render_onepage_tex(plan: dict[str, Any]) -> str:
    buckets = plan["bucket_records"]
    start_here = "\n".join(_tex_item(record) for record in buckets["start_here"][:7])
    read_after = "\n".join(_tex_item(record) for record in buckets["read_after"][:7])
    expand_if_time = "\n".join(_tex_item(record) for record in buckets["expand_if_time"][:4])
    baseline = "\n".join(_tex_item(record) for record in buckets["contrast_baseline"][:6])
    overview = _tex_plain_records(buckets["bridge_overview"], 7)
    return rf"""\documentclass[a4paper]{{article}}
\usepackage[a4paper,portrait,left=9mm,right=9mm,top=10mm,bottom=11mm,headheight=9pt,headsep=3mm,footskip=6mm]{{geometry}}
\usepackage{{fontspec}}
\usepackage{{xcolor}}
\usepackage{{fancyhdr}}

\setmainfont{{lmroman12-regular.otf}}[
  BoldFont = lmroman12-bold.otf,
  ItalicFont = lmroman10-italic.otf
]
\setmonofont{{lmmono10-regular.otf}}
\pagestyle{{fancy}}
\setlength{{\parindent}}{{0pt}}
\setlength{{\parskip}}{{0pt}}
\emergencystretch=1em

\definecolor{{textgray}}{{HTML}}{{111111}}
\definecolor{{softgray}}{{HTML}}{{444444}}
\definecolor{{midgray}}{{HTML}}{{777777}}

\newcommand{{\metafont}}{{\fontsize{{6.25}}{{6.95}}\selectfont\ttfamily}}
\fancyhf{{}}
\fancyhead[L]{{\metafont side 1/1}}
\fancyhead[C]{{\metafont personlighedspsykologi | prioriteret printoutlæsning}}
\fancyhead[R]{{\metafont side 1/1}}
\fancyfoot[L]{{\metafont ingen faste datoer}}
\fancyfoot[C]{{\metafont akademisk rank A}}
\fancyfoot[R]{{\metafont side 1/1}}
\renewcommand{{\headrulewidth}}{{0.4pt}}
\renewcommand{{\footrulewidth}}{{0.4pt}}

\newcommand{{\blockfont}}{{\fontsize{{6.55}}{{7.10}}\selectfont}}
\newcommand{{\readingfont}}{{\fontsize{{5.85}}{{6.42}}\selectfont}}
\newcommand{{\smallfont}}{{\fontsize{{5.55}}{{6.12}}\selectfont}}
\newcommand{{\checkfont}}{{\fontsize{{5.0}}{{5.65}}\selectfont\ttfamily\color{{softgray}}}}
\newcommand{{\tickbox}}{{\begingroup\setlength{{\fboxsep}}{{0pt}}\fbox{{\rule{{0pt}}{{3.55pt}}\rule{{3.55pt}}{{0pt}}}}\endgroup}}
\newcommand{{\bigbox}}{{\begingroup\setlength{{\fboxsep}}{{0pt}}\fbox{{\rule{{0pt}}{{4.75pt}}\rule{{4.75pt}}{{0pt}}}}\endgroup}}
\newcommand{{\readingbox}}{{\begingroup\setlength{{\fboxsep}}{{0pt}}\fbox{{\rule{{0pt}}{{5.7pt}}\rule{{5.7pt}}{{0pt}}}}\endgroup}}
\newcommand{{\track}}{{1~\tickbox\hspace{{2.25mm}}2~\bigbox\hspace{{2.25mm}}3~\tickbox\hspace{{2.25mm}}4~\tickbox}}

\newcommand{{\block}}[1]{{%
  \vspace{{0.82mm}}
  \rule{{\linewidth}}{{0.68pt}}\par
  \vspace{{0.32mm}}
  {{\blockfont\ttfamily #1}}\par
  \vspace{{0.58mm}}
}}

\newcommand{{\readingitem}}[2]{{%
  \noindent\begin{{minipage}}{{\linewidth}}
    {{\readingfont\raggedright #1\par}}
    \vspace{{0.12mm}}
    {{\checkfont #2\hfill\raisebox{{-0.85pt}}{{\readingbox}}\par}}
    \vspace{{0.10mm}}
    {{\checkfont \track\par}}
  \end{{minipage}}\par
  \vspace{{0.55mm}}
}}

\newcommand{{\plainitem}}[1]{{%
  \noindent{{\readingfont\raggedright #1\par}}
  \vspace{{0.44mm}}
}}

\begin{{document}}
\color{{textgray}}

\vspace*{{-1.4mm}}
\begin{{center}}
{{\fontsize{{7.6}}{{8.3}}\selectfont\ttfamily personlighedspsykologi}}\\[0.55mm]
{{\fontsize{{15.7}}{{16.4}}\selectfont\bfseries PRIORITERET PRINTOUTPLAN}}\\[0.85mm]
{{\fontsize{{6.55}}{{7.2}}\selectfont narrativ psykologi er læst | vælg hvilke tekster der er vigtige hvornår}}\\[0.9mm]
\rule{{0.56\linewidth}}{{0.45pt}}\\[0.9mm]
{{\fontsize{{6.35}}{{7.0}}\selectfont
\textbf{{A}} = akademisk rank \quad
\textbf{{1-4}} = guide, abridged, active, consolidation
}}
\end{{center}}

\vspace{{0.9mm}}
\noindent
\begin{{minipage}}[t]{{0.315\linewidth}}
\block{{START HER}}
{start_here}

\block{{LÆS DEREFTER}}
{read_after}
\end{{minipage}}
\hfill
\begin{{minipage}}[t]{{0.315\linewidth}}
\block{{UDBYG | agens, praksis, mening}}
{expand_if_time}

\block{{BRO-OVERBLIK | selektivt}}
{overview}
\end{{minipage}}
\hfill
\begin{{minipage}}[t]{{0.315\linewidth}}
\block{{KONTRASTBASELINE | brug mindre tid}}
{baseline}

\block{{12 LÆSEDAGE | uden datoer}}
\plainitem{{\textbf{{1-3:}} start her.}}
\plainitem{{\textbf{{4-6:}} læs derefter.}}
\plainitem{{\textbf{{7-8:}} udbyg hvis der er tid.}}
\plainitem{{\textbf{{9:}} baseline: træk, stabilitet, assessment.}}
\plainitem{{\textbf{{10:}} bro- og overblikstekster.}}
\plainitem{{\textbf{{11:}} mundtlig syntese på tværs.}}
\plainitem{{\textbf{{12:}} prøvefremlæggelse med narrativt centrum.}}
\end{{minipage}}

\vfill
\begin{{center}}
{{\smallfont\color{{midgray}}
Planen bygger på kildevægtning, concept graph, course synthesis og revised lecture substrates.
}}
\end{{center}}

\end{{document}}
"""


def compile_pdf(tex_path: Path, pdf_path: Path) -> bool:
    xelatex = shutil.which("xelatex")
    if not xelatex:
        raise SystemExit("xelatex is required to render the one-page PDF; rerun with --no-pdf to skip.")
    existing_pdf_bytes = pdf_path.read_bytes() if pdf_path.exists() else None
    subprocess.run(
        [xelatex, "-halt-on-error", "-interaction=nonstopmode", tex_path.name],
        cwd=tex_path.parent,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    rendered_pdf_path = tex_path.with_suffix(".pdf")
    if not rendered_pdf_path.exists():
        raise SystemExit(f"xelatex did not produce the expected PDF: {rendered_pdf_path}")
    rendered_pdf_bytes = rendered_pdf_path.read_bytes()
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    if rendered_pdf_path.resolve() != pdf_path.resolve():
        if existing_pdf_bytes == rendered_pdf_bytes:
            rendered_pdf_path.unlink()
        else:
            rendered_pdf_path.replace(pdf_path)
    changed = existing_pdf_bytes != rendered_pdf_bytes
    for suffix in (".aux", ".log", ".out"):
        generated = tex_path.with_suffix(suffix)
        if generated.exists():
            generated.unlink()
    return changed


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT), help="Repository root.")
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="Exam-priority config JSON.")
    parser.add_argument("--source-weighting", default=DEFAULT_SOURCE_WEIGHTING_PATH)
    parser.add_argument("--concept-graph", default=DEFAULT_CONCEPT_GRAPH_PATH)
    parser.add_argument("--course-synthesis", default=DEFAULT_COURSE_SYNTHESIS_PATH)
    parser.add_argument("--lecture-substrates-dir", default=DEFAULT_REVISED_LECTURE_SUBSTRATES_DIR)
    parser.add_argument("--generated-at", help="Override generated_at for deterministic tests.")
    parser.add_argument("--no-pdf", action="store_true", help="Write JSON/Markdown/TeX but skip xelatex.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    repo_root = Path(args.repo_root).expanduser().resolve()
    config_path = _resolve(repo_root, args.config)
    plan = build_exam_priority_plan(
        repo_root=repo_root,
        config_path=config_path,
        source_weighting_path=_resolve(repo_root, args.source_weighting),
        concept_graph_path=_resolve(repo_root, args.concept_graph),
        course_synthesis_path=_resolve(repo_root, args.course_synthesis),
        lecture_substrates_dir=_resolve(repo_root, args.lecture_substrates_dir),
        generated_at=args.generated_at,
    )
    outputs = _load_json(config_path).get("outputs", {})
    plan_json_path = _resolve(repo_root, outputs["plan_json"])
    markdown_path = _resolve(repo_root, outputs["markdown"])
    tex_path = _resolve(repo_root, outputs["onepage_tex"])
    pdf_output_value = outputs.get("onepage_pdf") or str(tex_path.with_suffix(".pdf"))
    pdf_path = _resolve(repo_root, pdf_output_value)

    changed = {
        "plan_json": _write_json_if_changed(plan_json_path, plan),
        "markdown": _write_text_if_changed(markdown_path, render_markdown(plan)),
        "onepage_tex": _write_text_if_changed(tex_path, render_onepage_tex(plan)),
    }
    if not args.no_pdf:
        changed["onepage_pdf"] = compile_pdf(tex_path, pdf_path)
    print(
        json.dumps(
            {
                "status": "built",
                "plan_json": _relpath(plan_json_path, repo_root),
                "markdown": _relpath(markdown_path, repo_root),
                "onepage_tex": _relpath(tex_path, repo_root),
                "onepage_pdf": _relpath(pdf_path, repo_root),
                "start_here_count": len(plan["bucket_records"]["start_here"]),
                "read_after_count": len(plan["bucket_records"]["read_after"]),
                "expand_if_time_count": len(plan["bucket_records"]["expand_if_time"]),
                "changed": changed,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
