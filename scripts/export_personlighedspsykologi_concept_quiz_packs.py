#!/usr/bin/env python3
"""Export NotebookLM source packs for Personlighedspsykologi concept quizzes."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
LAB_ROOT = REPO_ROOT / "notebooklm-podcast-auto/personlighedspsykologi/concept_quiz_lab"
SOURCE_ROOT = LAB_ROOT / "sources"
NOTE_PATH = REPO_ROOT / "shows/personlighedspsykologi-en/docs/begrebsnoter-filosofiske-noeglebegreber.md"
GLOSSARY_PATH = REPO_ROOT / "shows/personlighedspsykologi-en/course_glossary.json"
THEORY_MAP_PATH = REPO_ROOT / "shows/personlighedspsykologi-en/course_theory_map.json"
CONCEPT_GRAPH_PATH = REPO_ROOT / "shows/personlighedspsykologi-en/course_concept_graph.json"
COURSE_SYNTHESIS_PATH = REPO_ROOT / "shows/personlighedspsykologi-en/source_intelligence/course_synthesis.json"


@dataclass(frozen=True, slots=True)
class ConceptQuizPack:
    lecture_key: str
    slug: str
    title: str
    note_sections: tuple[str, ...]
    keywords: tuple[str, ...]
    intent: str


PACKS: tuple[ConceptQuizPack, ...] = (
    ConceptQuizPack(
        lecture_key="W90L1",
        slug="videnskabsteori-orienteringspunkter",
        title="Videnskabsteori og orienteringspunkter",
        note_sections=("Videnskabsteoretisk grundsprog", "Tværgående eksamens- og orienteringsbegreber"),
        keywords=(
            "ontologi",
            "epistemologi",
            "episteme",
            "hermeneutik",
            "dualisme",
            "dialektisk",
            "normativ",
            "relativisme",
            "essens",
            "kontekst",
            "determination",
            "historicitet",
            "idiografisk",
            "nomotetisk",
            "ergodic",
            "reificering",
            "orienteringspunkter",
        ),
        intent="Træn det sammenlignende grundsprog, der gør teoriernes personbegreb, metode og forklaringsniveau tydelige.",
    ),
    ConceptQuizPack(
        lecture_key="W90L2",
        slug="faenomenologi-eksistens",
        title="Fænomenologi og eksistens",
        note_sections=("Fænomenologi og eksistens", "Fænomenologi og eksistens: ekstra nøglebegreber"),
        keywords=(
            "fænomenologi",
            "eksistentialisme",
            "eksistentiel",
            "noema",
            "noesis",
            "dasein",
            "kastethed",
            "situerede",
            "intentionalitet",
            "epoché",
            "bracketing",
            "livsverden",
            "kropslighed",
            "førsteperson",
            "autenticitet",
            "finitude",
        ),
        intent="Træn forskellen mellem levet erfaring, væren-i-verden, frihed, situerethed og metodisk beskrivelse.",
    ),
    ConceptQuizPack(
        lecture_key="W90L3",
        slug="psykoanalyse-fortolkning-subjekt",
        title="Psykoanalyse, fortolkning og subjekt",
        note_sections=("Psykoanalyse: ekstra nøglebegreber", "Videnskabsteoretisk grundsprog"),
        keywords=(
            "psykoanalyse",
            "hermeneutik",
            "ubevidste",
            "psykisk realitet",
            "overføring",
            "nachträglichkeit",
            "drift",
            "begær",
            "forsvar",
            "id",
            "ego",
            "superego",
            "spejlstadiet",
            "symbolske",
            "decentreret subjekt",
        ),
        intent="Træn psykoanalysens særlige logik: mening, konflikt, ubevidsthed, struktur og fortolkende evidens.",
    ),
    ConceptQuizPack(
        lecture_key="W90L4",
        slug="traek-maaling-udvikling",
        title="Træk, måling, udvikling og patologi",
        note_sections=("Træk, måling og udvikling", "Tværgående eksamens- og orienteringsbegreber"),
        keywords=(
            "træk",
            "big five",
            "hexaco",
            "leksikal",
            "faktoranalyse",
            "rank-order",
            "mean-level",
            "traits",
            "states",
            "whole trait",
            "personality functioning",
            "lpf",
            "dimensional",
            "nomotetisk",
            "ergodic",
        ),
        intent="Træn variabel-, målings- og udviklingsbegreber uden at forveksle dem med de fortolkende eller kritiske traditioner.",
    ),
    ConceptQuizPack(
        lecture_key="W90L5",
        slug="humanistisk-kritisk-personalisme",
        title="Humanistisk, kritisk psykologi og kritisk personalisme",
        note_sections=("Humanistisk psykologi", "Kritisk psykologi og kritisk personalisme", "Person, handling og mål"),
        keywords=(
            "humanistisk",
            "selvaktualisering",
            "kongruens",
            "ubetinget positiv anerkendelse",
            "growth",
            "deficit",
            "kritisk psykologi",
            "kritisk personalisme",
            "handleevne",
            "restriktiv",
            "ekspansiv",
            "daglig livsførelse",
            "betingelser",
            "deltagelse",
            "social praksis",
            "subjektvidenskab",
            "grunde",
            "genstandsadækvathed",
            "medforsker",
            "introception",
            "agency",
            "agens",
            "locus",
            "autotelic",
            "heterotelic",
        ),
        intent="Træn hvordan humanistiske og kritiske begreber flytter fokus til vækst, person, praksis, grunde og handlemuligheder.",
    ),
    ConceptQuizPack(
        lecture_key="W90L6",
        slug="poststrukturalisme-socialkonstruktionisme",
        title="Poststrukturalisme, socialkonstruktionisme og subjektivering",
        note_sections=(
            "Historie, subjekt og sprog",
            "Poststrukturalisme, socialkonstruktionisme og subjektivering",
        ),
        keywords=(
            "genealogi",
            "foucault",
            "nominalism",
            "historical nominalism",
            "dynamic nominalism",
            "dialogism",
            "bakhtin",
            "sociogenese",
            "ontogenese",
            "fylogenese",
            "diskurs",
            "magt",
            "viden",
            "subjektivering",
            "positionering",
            "anti-essentialisme",
            "decentreret",
            "looping effect",
            "making up people",
            "performativity",
            "heteroglossia",
        ),
        intent="Træn de historiske, sproglige og magtanalytiske begreber uden at reducere dem til relativisme.",
    ),
    ConceptQuizPack(
        lecture_key="W90L7",
        slug="narrativ-blandet-eksamen",
        title="Narrativ psykologi og blandet eksamensrepetition",
        note_sections=("Narrativ psykologi", "Prioritet", "Hurtige eksamensspørgsmål"),
        keywords=(
            "narrativ",
            "livshistorie",
            "kulturelle narrativer",
            "alternative historier",
            "meaning-making",
            "meningsskabelse",
            "plot",
            "folk psychology",
            "orienteringspunkter",
            "eksamen",
        ),
        intent="Træn narrativ teori og blandede eksamensspørgsmål, der kræver at begreber forbindes på tværs af traditioner.",
    ),
)


def _slugify(value: str) -> str:
    normalized = value.lower()
    normalized = (
        normalized.replace("æ", "ae")
        .replace("ø", "oe")
        .replace("å", "aa")
        .replace("é", "e")
    )
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    return normalized or "pack"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _section_blocks(markdown: str, level: int) -> dict[str, str]:
    hashes = "#" * level
    pattern = re.compile(rf"^{re.escape(hashes)}\s+(.+?)\s*$", re.MULTILINE)
    matches = list(pattern.finditer(markdown))
    blocks: dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        title = match.group(1).strip()
        blocks[title] = markdown[start:end].strip()
    return blocks


def _matches_keywords(value: object, keywords: tuple[str, ...]) -> bool:
    text = json.dumps(value, ensure_ascii=False).casefold()
    return any(keyword.casefold() in text for keyword in keywords)


def _compact_term(term: dict[str, Any]) -> dict[str, Any]:
    return {
        key: term.get(key)
        for key in (
            "term_id",
            "label",
            "category",
            "importance",
            "definition",
            "course_role",
            "lecture_keys",
            "linked_terms",
            "linked_theories",
            "representative_excerpts",
        )
        if term.get(key) not in (None, "", [], {})
    }


def _compact_theory(theory: dict[str, Any]) -> dict[str, Any]:
    return {
        key: theory.get(key)
        for key in (
            "theory_id",
            "label",
            "importance",
            "summary",
            "course_role",
            "lecture_keys",
            "core_terms",
            "related_theories",
        )
        if theory.get(key) not in (None, "", [], {})
    }


def _selected_course_intelligence(pack: ConceptQuizPack) -> dict[str, Any]:
    glossary = _load_json(GLOSSARY_PATH)
    theory_map = _load_json(THEORY_MAP_PATH)
    concept_graph = _load_json(CONCEPT_GRAPH_PATH)
    course_synthesis = _load_json(COURSE_SYNTHESIS_PATH)

    terms = [
        _compact_term(term)
        for term in glossary.get("terms", [])
        if isinstance(term, dict) and _matches_keywords(term, pack.keywords)
    ][:10]
    theories = [
        _compact_theory(theory)
        for theory in theory_map.get("theories", [])
        if isinstance(theory, dict) and _matches_keywords(theory, pack.keywords)
    ][:8]

    graph_nodes = [
        node
        for node in concept_graph.get("nodes", [])
        if isinstance(node, dict) and _matches_keywords(node, pack.keywords)
    ][:14]
    analysis = course_synthesis.get("analysis") if isinstance(course_synthesis.get("analysis"), dict) else {}
    selected_analysis: dict[str, Any] = {}
    for key in ("concept_map", "distinction_map", "theory_tradition_map", "sideways_relations"):
        values = analysis.get(key)
        if isinstance(values, list):
            matches = [item for item in values if _matches_keywords(item, pack.keywords)]
            if matches:
                selected_analysis[key] = matches[:8]

    return {
        "matched_terms": terms,
        "matched_theories": theories,
        "matched_concept_graph_nodes": graph_nodes,
        "matched_course_synthesis": selected_analysis,
    }


def _pack_markdown(pack: ConceptQuizPack, note_sections: dict[str, str]) -> str:
    selected_sections = [note_sections[title] for title in pack.note_sections if title in note_sections]
    missing = [title for title in pack.note_sections if title not in note_sections]
    intelligence = _selected_course_intelligence(pack)
    body = [
        f"# {pack.title}",
        "",
        "Denne kildepakke er lavet til en normal dansk begrebsquiz i Personlighedspsykologi.",
        "",
        f"Formål: {pack.intent}",
        "",
        "Quizzen skal teste præcis begrebsforståelse, typiske forvekslinger og evnen til at bruge begreberne i kursets teorier.",
        "",
        "## Udvalgte begrebsnoter",
        "",
        "\n\n".join(selected_sections).strip(),
    ]
    if missing:
        body.extend(["", "## Manglende noteafsnit", "", "\n".join(f"- {item}" for item in missing)])
    body.extend(
        [
            "",
            "## Kursusforankring fra course intelligence",
            "",
            "```json",
            json.dumps(intelligence, indent=2, ensure_ascii=False),
            "```",
            "",
            "## Quiz-kvalitetskrav",
            "",
            "- Spørgsmålene skal være på dansk.",
            "- Brug konkrete kontraster mellem begreber, ikke kun definitionsgenkendelse.",
            "- Undgå interne kildehenvisninger som matrix, note, dokument, kildepakke eller ifølge materialet.",
            "- Undgå at teste filnavne, metadata, forelæsningskoder eller provenance.",
            "- Gør distraktorer plausible, men fagligt forkerte på en tydelig måde.",
        ]
    )
    return "\n".join(body).rstrip() + "\n"


def _prompt_config() -> dict[str, Any]:
    return {
        "language": "da",
        "languages": [{"code": "da", "suffix": ""}],
        "course_title": "Personlighedspsykologi",
        "quiz": {
            "quantity": "more",
            "difficulty": "medium",
            "format": "json",
            "prompt": (
                "Lav en normal dansk multiple-choice quiz til en bachelorstuderende i personlighedspsykologi. "
                "Quizzen skal teste begrebsforståelse, skelnen mellem nærliggende begreber, typiske misforståelser "
                "og anvendelse i kursets teorier. Spørg ikke til filnavne, metadata, forelæsningskoder eller "
                "hvor oplysningerne kommer fra. Brug aldrig formuleringer som 'ifølge matrixen', 'ifølge kilden', "
                "'ifølge noterne', 'dette dokument' eller lignende. Skriv spørgsmål og svarmuligheder, så de kan "
                "stå alene for en bruger på Freudd."
            ),
        },
        "weekly_overview": {"prompt": ""},
        "per_reading": {"prompt": ""},
        "short": {"enabled": False},
        "course_context": {"enabled": False},
        "audio_prompt_strategy": {"enabled": False},
        "audio_prompt_framework": {"enabled": False},
        "exam_focus": {"enabled": False},
        "study_context": {"enabled": False},
        "meta_prompting": {"enabled": False},
    }


def _auto_spec() -> dict[str, Any]:
    return {
        "year": 2026,
        "week_reference_year": 2026,
        "timezone": "Europe/Copenhagen",
        "rules": [
            {
                "aliases": [pack.lecture_key, pack.lecture_key.lower()],
                "topic": pack.title,
                "concept_quiz_slug": pack.slug,
            }
            for pack in PACKS
        ],
    }


def _config() -> dict[str, Any]:
    return {
        "subject_slug": "personlighedspsykologi",
        "publication": {"owner": "manual-concept-quiz-import"},
        "quiz": {"links_file": "shows/personlighedspsykologi-en/quiz_links.json"},
    }


def export() -> dict[str, Any]:
    markdown = NOTE_PATH.read_text(encoding="utf-8")
    note_sections = _section_blocks(markdown, 2)
    SOURCE_ROOT.mkdir(parents=True, exist_ok=True)

    exported_packs: list[dict[str, Any]] = []
    for pack in PACKS:
        folder = SOURCE_ROOT / f"{pack.lecture_key} {pack.title}"
        folder.mkdir(parents=True, exist_ok=True)
        source_file = folder / f"01-{pack.slug}.md"
        source_file.write_text(_pack_markdown(pack, note_sections), encoding="utf-8")
        exported_packs.append(
            {
                "lecture_key": pack.lecture_key,
                "slug": pack.slug,
                "title": pack.title,
                "source_path": source_file.relative_to(REPO_ROOT).as_posix(),
                "keywords": list(pack.keywords),
            }
        )

    (LAB_ROOT / "auto_spec.json").write_text(
        json.dumps(_auto_spec(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (LAB_ROOT / "prompt_config.json").write_text(
        json.dumps(_prompt_config(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (LAB_ROOT / "config.json").write_text(
        json.dumps(_config(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (LAB_ROOT / "manifest.json").write_text(
        json.dumps(
            {
                "version": 1,
                "subject_slug": "personlighedspsykologi",
                "show_slug": "personlighedspsykologi-concept-quizzes",
                "output_root": "notebooklm-podcast-auto/personlighedspsykologi/concept_quiz_lab/output",
                "packs": exported_packs,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (LAB_ROOT / "README.md").write_text(
        "# Personlighedspsykologi Concept Quiz Lab\n\n"
        "Generated source packs for NotebookLM concept quizzes. Regenerate with:\n\n"
        "```bash\n"
        ".venv/bin/python scripts/export_personlighedspsykologi_concept_quiz_packs.py\n"
        "```\n\n"
        "The live generation path is the Hetzner NotebookLM queue show "
        "`personlighedspsykologi-concept-quizzes`; it uses medium difficulty as the single "
        "normal quiz level.\n",
        encoding="utf-8",
    )
    return {"packs": exported_packs}


def main() -> int:
    payload = export()
    print(f"Exported {len(payload['packs'])} concept quiz pack(s) to {SOURCE_ROOT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
