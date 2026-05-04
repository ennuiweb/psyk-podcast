#!/usr/bin/env python3
"""Build cross-lecture concept graph artifacts for Personlighedspsykologi."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_GLOSSARY_PATH = "shows/personlighedspsykologi-en/course_glossary.json"
DEFAULT_THEORY_MAP_PATH = "shows/personlighedspsykologi-en/course_theory_map.json"
DEFAULT_WEIGHTING_PATH = "shows/personlighedspsykologi-en/source_weighting.json"
DEFAULT_SEED_PATH = "shows/personlighedspsykologi-en/source_intelligence_seed.json"
DEFAULT_OUTPUT_PATH = "shows/personlighedspsykologi-en/course_concept_graph.json"
DEFAULT_STALENESS_PATH = "shows/personlighedspsykologi-en/source_intelligence_staleness.json"
CONCEPT_GRAPH_VERSION = 1


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _display_path(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path.resolve())


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _normalize_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def build_concept_graph(
    *,
    repo_root: Path,
    glossary_path: Path,
    theory_map_path: Path,
    weighting_path: Path,
    seed_path: Path,
    output_path: Path,
    staleness_path: Path,
) -> dict[str, Any]:
    glossary_payload = _load_json(glossary_path)
    theory_map_payload = _load_json(theory_map_path)
    weighting_payload = _load_json(weighting_path)
    seed_payload = _load_json(seed_path)

    glossary_terms = glossary_payload.get("terms")
    theory_entries = theory_map_payload.get("theories")
    theory_relations = theory_map_payload.get("relations")
    distinctions_seed = seed_payload.get("distinctions")
    if not isinstance(glossary_terms, list):
        raise SystemExit(f"invalid glossary terms in {glossary_path}")
    if not isinstance(theory_entries, list):
        raise SystemExit(f"invalid theory entries in {theory_map_path}")
    if not isinstance(theory_relations, list):
        raise SystemExit(f"invalid theory relations in {theory_map_path}")
    if not isinstance(distinctions_seed, list):
        raise SystemExit(f"invalid distinctions in {seed_path}")

    term_by_id = {
        str(term.get("term_id") or "").strip(): term
        for term in glossary_terms
        if isinstance(term, dict) and str(term.get("term_id") or "").strip()
    }
    theory_by_id = {
        str(theory.get("theory_id") or "").strip(): theory
        for theory in theory_entries
        if isinstance(theory, dict) and str(theory.get("theory_id") or "").strip()
    }

    lecture_term_map: dict[str, list[str]] = defaultdict(list)
    for term_id, term in term_by_id.items():
        for lecture_key in _normalize_list(term.get("lecture_keys")):
            lecture_term_map[lecture_key].append(term_id)

    source_weight_by_id = {
        str(source.get("source_id") or "").strip(): source
        for source in weighting_payload.get("sources", [])
        if isinstance(source, dict) and str(source.get("source_id") or "").strip()
    }

    nodes: list[dict[str, Any]] = []
    for term_id, term in sorted(term_by_id.items()):
        nodes.append(
            {
                "node_id": term_id,
                "node_type": "term",
                "label": str(term.get("label") or "").strip(),
                "importance": int(term.get("importance") or 1),
                "salience_score": int(term.get("salience_score") or 0),
                "lecture_keys": _normalize_list(term.get("lecture_keys")),
                "theory_ids": _normalize_list(term.get("linked_theories")),
            }
        )
    for theory_id, theory in sorted(theory_by_id.items()):
        nodes.append(
            {
                "node_id": theory_id,
                "node_type": "theory",
                "label": str(theory.get("label") or "").strip(),
                "importance": int(theory.get("importance") or 1),
                "salience_score": int(theory.get("salience_score") or 0),
                "lecture_keys": _normalize_list(theory.get("lecture_keys")),
                "term_ids": _normalize_list(theory.get("core_term_ids")),
            }
        )

    edges: list[dict[str, Any]] = []
    seen_edges: set[tuple[str, str, str]] = set()

    def add_edge(source_id: str, target_id: str, edge_type: str, **extra: Any) -> None:
        key = (source_id, target_id, edge_type)
        if key in seen_edges:
            return
        seen_edges.add(key)
        payload = {
            "source_id": source_id,
            "target_id": target_id,
            "edge_type": edge_type,
        }
        payload.update(extra)
        edges.append(payload)

    for term_id, term in term_by_id.items():
        for linked_term in _normalize_list(term.get("linked_terms")):
            if linked_term in term_by_id:
                add_edge(
                    term_id,
                    linked_term,
                    "term_link",
                    relation="linked_term",
                )
        for theory_id in _normalize_list(term.get("linked_theories")):
            if theory_id in theory_by_id:
                add_edge(
                    term_id,
                    theory_id,
                    "term_to_theory",
                    relation="linked_theory",
                )

    for relation in theory_relations:
        if not isinstance(relation, dict):
            continue
        source_id = str(relation.get("source_theory_id") or "").strip()
        target_id = str(relation.get("target_theory_id") or "").strip()
        if source_id in theory_by_id and target_id in theory_by_id:
            add_edge(
                source_id,
                target_id,
                "theory_relation",
                relation=str(relation.get("relation_type") or "").strip(),
                supporting_term_ids=_normalize_list(relation.get("supporting_term_ids")),
            )

    for lecture_key, term_ids in lecture_term_map.items():
        unique_terms = sorted(set(term_ids))
        for index, source_term_id in enumerate(unique_terms):
            for target_term_id in unique_terms[index + 1 :]:
                add_edge(
                    source_term_id,
                    target_term_id,
                    "lecture_co_occurrence",
                    relation="shared_lecture",
                    lecture_key=lecture_key,
                )

    distinctions: list[dict[str, Any]] = []
    for raw_distinction in distinctions_seed:
        if not isinstance(raw_distinction, dict):
            continue
        distinction_id = str(raw_distinction.get("distinction_id") or "").strip()
        if not distinction_id:
            continue
        term_ids = [term_id for term_id in _normalize_list(raw_distinction.get("term_ids")) if term_id in term_by_id]
        lecture_keys = _normalize_list(raw_distinction.get("lecture_keys"))
        supporting_source_ids: list[str] = []
        for term_id in term_ids:
            supporting_source_ids.extend(_normalize_list(term_by_id[term_id].get("core_source_ids")))
        weighted_sources = [
            source_weight_by_id[source_id]
            for source_id in _unique(supporting_source_ids)
            if source_id in source_weight_by_id
        ]
        weighted_sources.sort(key=lambda item: -int(item.get("weight_score") or 0))
        distinctions.append(
            {
                "distinction_id": distinction_id,
                "label": str(raw_distinction.get("label") or "").strip(),
                "importance": int(raw_distinction.get("importance") or 1),
                "summary": str(raw_distinction.get("summary") or "").strip(),
                "lecture_keys": lecture_keys,
                "term_ids": term_ids,
                "term_labels": [str(term_by_id[term_id].get("label") or "").strip() for term_id in term_ids],
                "supporting_source_ids": [str(item.get("source_id") or "").strip() for item in weighted_sources[:6]],
            }
        )

    payload = {
        "version": CONCEPT_GRAPH_VERSION,
        "subject_slug": "personlighedspsykologi",
        "generated_at": _now(),
        "build_inputs": {
            "course_glossary": _display_path(glossary_path, repo_root),
            "course_theory_map": _display_path(theory_map_path, repo_root),
            "source_weighting": _display_path(weighting_path, repo_root),
            "semantic_seed": _display_path(seed_path, repo_root),
        },
        "stats": {
            "node_count": len(nodes),
            "term_node_count": sum(1 for node in nodes if node["node_type"] == "term"),
            "theory_node_count": sum(1 for node in nodes if node["node_type"] == "theory"),
            "edge_count": len(edges),
            "distinction_count": len(distinctions),
        },
        "nodes": nodes,
        "edges": edges,
        "distinctions": distinctions,
    }
    _write_json(output_path, payload)

    staleness_payload = _load_json(staleness_path) if staleness_path.exists() else {
        "version": CONCEPT_GRAPH_VERSION,
        "subject_slug": "personlighedspsykologi",
        "generated_at": _now(),
        "artifacts": {},
        "derivations": [],
    }
    staleness_payload["generated_at"] = _now()
    artifacts = staleness_payload.setdefault("artifacts", {})
    derivations = staleness_payload.setdefault("derivations", [])
    builder_path = Path(__file__).resolve()
    artifacts["course_concept_graph"] = {
        "path": _display_path(output_path, repo_root),
        "sha256": _sha256_file(output_path),
        "input_signature_sha256": _sha256_bytes(
            "\n".join(
                [
                    _sha256_file(glossary_path),
                    _sha256_file(theory_map_path),
                    _sha256_file(weighting_path),
                    _sha256_file(seed_path),
                    _sha256_file(builder_path),
                ]
            ).encode("utf-8")
        ),
        "builder_script": _display_path(builder_path, repo_root),
    }
    derivation_entry = {
        "artifact_path": _display_path(output_path, repo_root),
        "depends_on": [
            _display_path(glossary_path, repo_root),
            _display_path(theory_map_path, repo_root),
            _display_path(weighting_path, repo_root),
            _display_path(seed_path, repo_root),
            _display_path(builder_path, repo_root),
        ],
    }
    derivations = [
        entry
        for entry in derivations
        if not (isinstance(entry, dict) and str(entry.get("artifact_path") or "").strip() == derivation_entry["artifact_path"])
    ]
    derivations.append(derivation_entry)
    staleness_payload["derivations"] = derivations
    _write_json(staleness_path, staleness_payload)
    return payload


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--glossary-path", default=DEFAULT_GLOSSARY_PATH)
    parser.add_argument("--theory-map-path", default=DEFAULT_THEORY_MAP_PATH)
    parser.add_argument("--weighting-path", default=DEFAULT_WEIGHTING_PATH)
    parser.add_argument("--seed-path", default=DEFAULT_SEED_PATH)
    parser.add_argument("--output-path", default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--staleness-path", default=DEFAULT_STALENESS_PATH)
    return parser.parse_args()


def _resolve_path(repo_root: Path, value: str) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (repo_root / path).resolve()


def main() -> int:
    args = _parse_args()
    repo_root = _repo_root()
    payload = build_concept_graph(
        repo_root=repo_root,
        glossary_path=_resolve_path(repo_root, args.glossary_path),
        theory_map_path=_resolve_path(repo_root, args.theory_map_path),
        weighting_path=_resolve_path(repo_root, args.weighting_path),
        seed_path=_resolve_path(repo_root, args.seed_path),
        output_path=_resolve_path(repo_root, args.output_path),
        staleness_path=_resolve_path(repo_root, args.staleness_path),
    )
    print(
        "Built concept graph "
        f"(nodes={payload['stats']['node_count']} edges={payload['stats']['edge_count']} distinctions={payload['stats']['distinction_count']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
