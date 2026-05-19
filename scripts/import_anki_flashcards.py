#!/usr/bin/env python3
"""Import an Anki .apkg deck into a Freudd flashcard artifact."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import sqlite3
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


FIELD_SEPARATOR = "\x1f"
DEFAULT_TITLE = "Biologisk psykologi og neuropsykologi"
DEFAULT_DECK_SLUG = "biologisk-psykologi-og-neuropsykologi"
COMPATIBILITY_PLACEHOLDER = "Please update to the latest Anki version"

ALLOWED_TAGS = {
    "b",
    "br",
    "code",
    "div",
    "em",
    "i",
    "li",
    "ol",
    "p",
    "span",
    "strong",
    "sub",
    "sup",
    "u",
    "ul",
}
VOID_TAGS = {"br"}
DROP_CONTENT_TAGS = {"script", "style", "iframe", "object", "embed"}
WHITESPACE_RE = re.compile(r"\s+")


class SanitizingHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.drop_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_name = tag.lower()
        if tag_name in DROP_CONTENT_TAGS:
            self.drop_depth += 1
            return
        if self.drop_depth:
            return
        if tag_name in ALLOWED_TAGS:
            self.parts.append(f"<{tag_name}>")

    def handle_endtag(self, tag: str) -> None:
        tag_name = tag.lower()
        if tag_name in DROP_CONTENT_TAGS:
            if self.drop_depth:
                self.drop_depth -= 1
            return
        if self.drop_depth:
            return
        if tag_name in ALLOWED_TAGS and tag_name not in VOID_TAGS:
            self.parts.append(f"</{tag_name}>")

    def handle_data(self, data: str) -> None:
        if self.drop_depth:
            return
        self.parts.append(html.escape(data, quote=False))

    def handle_entityref(self, name: str) -> None:
        if self.drop_depth:
            return
        self.parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if self.drop_depth:
            return
        self.parts.append(f"&#{name};")

    def value(self) -> str:
        return "".join(self.parts).strip()


class TextHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.drop_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_name = tag.lower()
        if tag_name in DROP_CONTENT_TAGS:
            self.drop_depth += 1
            return
        if tag_name in {"br", "p", "div", "li"}:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        tag_name = tag.lower()
        if tag_name in DROP_CONTENT_TAGS:
            if self.drop_depth:
                self.drop_depth -= 1
            return
        if tag_name in {"p", "div", "li"}:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if self.drop_depth:
            return
        self.parts.append(data)

    def value(self) -> str:
        return WHITESPACE_RE.sub(" ", "".join(self.parts)).strip()


@dataclass(frozen=True)
class ImportedCard:
    card_id: str
    front_text: str
    back_html_sanitized: str
    back_text: str
    source_note_id: str
    source_card_id: str
    source_ord: int
    tags: list[str]
    category_slug: str
    category_title: str
    content_sha256: str


@dataclass(frozen=True)
class CategoryRule:
    slug: str
    title: str
    terms: tuple[str, ...]


@dataclass(frozen=True)
class CardCategory:
    slug: str
    title: str


CATEGORY_FALLBACK = CardCategory(slug="grundbegreber", title="Grundbegreber")
CATEGORY_RULES: tuple[CategoryRule, ...] = (
    CategoryRule(
        slug="metoder-og-forskning",
        title="Metoder og forskning",
        terms=(
            "research",
            "approach",
            "approaches",
            "somatic intervention",
            "behavioral intervention",
            "correlation",
            "experiment",
            "experimental",
            "method",
            "methods",
            "technique",
            "techniques",
            "reductionism",
            "model",
            "models",
            "stimulation",
            "recording",
            "imaging",
            "optogenetic",
            "optogenetics",
            "halorhodopsin",
            "channelrhodopsin",
            "researcher",
            "researchers",
            "evidence",
        ),
    ),
    CategoryRule(
        slug="klinik-og-forstyrrelser",
        title="Klinik og forstyrrelser",
        terms=(
            "schizophrenia",
            "depression",
            "anxiety",
            "disorder",
            "disorders",
            "disease",
            "diseases",
            "damage",
            "lesion",
            "lesions",
            "patient",
            "patients",
            "symptom",
            "symptoms",
            "aphasia",
            "amusia",
            "parkinson",
            "huntington",
            "alzheimer",
            "autism",
            "adhd",
            "dsm-5",
            "substance use disorder",
        ),
    ),
    CategoryRule(
        slug="neuroner-og-synapser",
        title="Neuroner og synapser",
        terms=(
            "neuron",
            "neurons",
            "glia",
            "glial",
            "axon",
            "axons",
            "dendrite",
            "dendrites",
            "myelin",
            "membrane",
            "ion",
            "ions",
            "channel",
            "channels",
            "action potential",
            "resting potential",
            "synapse",
            "synapses",
            "synaptic",
            "presynaptic",
            "postsynaptic",
            "neurotransmitter",
            "neurotransmitters",
            "receptor",
            "receptors",
            "epsp",
            "ipsp",
            "vesicle",
            "vesicles",
            "transport",
        ),
    ),
    CategoryRule(
        slug="neurokemi-og-rusmidler",
        title="Neurokemi og rusmidler",
        terms=(
            "drug",
            "drugs",
            "substance",
            "addiction",
            "tolerance",
            "withdrawal",
            "alcohol",
            "opioid",
            "opioids",
            "cocaine",
            "amphetamine",
            "nicotine",
            "cannabis",
            "thc",
            "lsd",
            "agonist",
            "antagonist",
            "dopamine",
            "serotonin",
            "acetylcholine",
            "gaba",
            "glutamate",
            "peptide",
            "peptides",
            "endorphin",
            "neurochemistry",
        ),
    ),
    CategoryRule(
        slug="hormoner-og-homeostase",
        title="Hormoner og homeostase",
        terms=(
            "hormone",
            "hormones",
            "endocrine",
            "pituitary",
            "testosterone",
            "estrogen",
            "oestrogen",
            "androgen",
            "steroid",
            "cortisol",
            "stress",
            "thyroid",
            "adrenal",
            "gland",
            "glands",
            "homeostasis",
            "homeostatic",
            "temperature",
            "hunger",
            "thirst",
            "hypothalamus",
            "bloodstream",
            "releasing hormone",
        ),
    ),
    CategoryRule(
        slug="sanser-og-perception",
        title="Sanser og perception",
        terms=(
            "sensory",
            "sensation",
            "perception",
            "retina",
            "vision",
            "visual",
            "photoreceptor",
            "photoreceptors",
            "rod",
            "rods",
            "cone",
            "cones",
            "optic",
            "auditory",
            "hearing",
            "cochlea",
            "sound",
            "somatosensory",
            "touch",
            "pain",
            "nociceptor",
            "nociceptors",
            "olfactory",
            "smell",
            "taste",
            "skin",
            "receptive field",
        ),
    ),
    CategoryRule(
        slug="motorik-og-autonom-regulering",
        title="Motorik og autonom regulering",
        terms=(
            "motor",
            "movement",
            "muscle",
            "muscles",
            "reflex",
            "spinal reflex",
            "autonomic",
            "sympathetic",
            "parasympathetic",
            "basal ganglia",
            "cerebellum",
            "neural control",
            "visceral",
            "fight-or-flight",
            "rest-and-digest",
        ),
    ),
    CategoryRule(
        slug="hukommelse-og-kognition",
        title="Hukommelse og kognition",
        terms=(
            "memory",
            "memories",
            "learning",
            "declarative",
            "nondeclarative",
            "hippocampus",
            "amnesia",
            "language",
            "aphasia",
            "broca",
            "wernicke",
            "lateralization",
            "cognitive",
            "cognition",
            "attention",
            "sleep",
            "circadian",
            "scn",
            "suprachiasmatic",
            "dream",
            "rem",
        ),
    ),
    CategoryRule(
        slug="emotion-og-motivation",
        title="Emotion og motivation",
        terms=(
            "emotion",
            "emotions",
            "emotional",
            "fear",
            "amygdala",
            "motivation",
            "motivational",
            "reward",
            "pleasure",
            "appetite",
            "aggression",
            "stress response",
            "sexual behavior",
            "maternal",
            "attachment",
        ),
    ),
    CategoryRule(
        slug="udvikling-og-plasticitet",
        title="Udvikling og plasticitet",
        terms=(
            "development",
            "developing",
            "neural tube",
            "embryonic",
            "embryo",
            "neurogenesis",
            "migration",
            "differentiation",
            "synaptogenesis",
            "cell death",
            "apoptosis",
            "growth cone",
            "sensitive period",
            "plasticity",
            "neuroplasticity",
            "rearrangement",
            "pruning",
            "regeneration",
            "stem cell",
            "stem cells",
        ),
    ),
    CategoryRule(
        slug="nervesystemets-opbygning",
        title="Nervesystemets opbygning",
        terms=(
            "central nervous system",
            "peripheral nervous system",
            "cns",
            "pns",
            "brain region",
            "spinal cord",
            "brainstem",
            "cerebellum",
            "cerebral",
            "cortex",
            "thalamus",
            "hypothalamus",
            "hippocampus",
            "amygdala",
            "basal ganglia",
            "lobe",
            "lobes",
            "forebrain",
            "midbrain",
            "hindbrain",
            "autonomic nervous system",
            "sympathetic",
            "parasympathetic",
            "reticular",
            "limbic",
        ),
    ),
    CategoryRule(
        slug="evolution-og-adfaerd",
        title="Evolution og adfærd",
        terms=(
            "evolution",
            "evolutionary",
            "species",
            "selection",
            "natural selection",
            "sexual selection",
            "adaptation",
            "adaptive",
            "gene",
            "genes",
            "genetic",
            "genetics",
            "heritability",
            "reproductive",
            "behavioral neuroscience",
            "social",
            "mating",
        ),
    ),
)


def sanitize_html(raw_value: str) -> str:
    parser = SanitizingHTMLParser()
    parser.feed(raw_value or "")
    parser.close()
    return parser.value()


def html_to_text(raw_value: str) -> str:
    parser = TextHTMLParser()
    parser.feed(raw_value or "")
    parser.close()
    return parser.value()


def normalized_text_hash(*values: str) -> str:
    normalized = "\n".join(WHITESPACE_RE.sub(" ", value or "").strip() for value in values)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def term_score(text: str, term: str) -> int:
    pattern = rf"(?<![a-z0-9]){re.escape(term.lower())}(?![a-z0-9])"
    if not re.search(pattern, text):
        return 0
    return 2 if " " in term or "-" in term else 1


def derive_category(front_text: str, back_text: str) -> CardCategory:
    text = f"{front_text} {back_text}".lower()
    best_category = CATEGORY_FALLBACK
    best_score = 0
    for rule in CATEGORY_RULES:
        score = sum(term_score(text, term) for term in rule.terms)
        if score > best_score:
            best_score = score
            best_category = CardCategory(slug=rule.slug, title=rule.title)
    return best_category


def source_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def zip_generated_at(path: Path) -> str:
    latest: datetime | None = None
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            timestamp = datetime(*info.date_time, tzinfo=timezone.utc)
            if latest is None or timestamp > latest:
                latest = timestamp
    return (latest or datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)).isoformat().replace("+00:00", "Z")


def extract_collection_database(package_path: Path, destination: Path) -> str:
    with zipfile.ZipFile(package_path) as archive:
        names = set(archive.namelist())
        if "collection.anki21b" in names:
            compressed_path = destination.with_suffix(".anki21b.zst")
            compressed_path.write_bytes(archive.read("collection.anki21b"))
            zstd_bin = shutil.which("zstd")
            if not zstd_bin:
                raise RuntimeError("collection.anki21b requires the `zstd` CLI, but it was not found.")
            with destination.open("wb") as output:
                result = subprocess.run(
                    [zstd_bin, "-q", "-d", "-c", str(compressed_path)],
                    stdout=output,
                    stderr=subprocess.PIPE,
                    text=False,
                    check=False,
                )
            if result.returncode != 0:
                stderr = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
                raise RuntimeError(f"zstd failed to decompress collection.anki21b: {stderr.strip()}")
            return "collection.anki21b"
        if "collection.anki2" in names:
            destination.write_bytes(archive.read("collection.anki2"))
            return "collection.anki2"
    raise RuntimeError("Anki package does not contain collection.anki21b or collection.anki2.")


def table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "select 1 from sqlite_master where type = 'table' and name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def load_cards_from_database(database_path: Path) -> list[ImportedCard]:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        if not table_exists(connection, "notes") or not table_exists(connection, "cards"):
            raise RuntimeError("Anki database is missing required notes/cards tables.")

        rows = connection.execute(
            """
            select
              cards.id as source_card_id,
              cards.nid as source_note_id,
              cards.ord as source_ord,
              notes.flds as fields,
              notes.tags as tags
            from cards
            join notes on notes.id = cards.nid
            order by cards.due, cards.id
            """
        ).fetchall()
    finally:
        connection.close()

    imported: list[ImportedCard] = []
    for row in rows:
        fields = str(row["fields"] or "").split(FIELD_SEPARATOR)
        if len(fields) < 2:
            continue
        raw_front = fields[0]
        raw_back = fields[1]
        front_text = html_to_text(raw_front)
        back_html = sanitize_html(raw_back)
        back_text = html_to_text(back_html)
        if front_text.startswith(COMPATIBILITY_PLACEHOLDER):
            continue
        if not front_text or not back_text:
            continue
        source_card_id = str(row["source_card_id"])
        source_note_id = str(row["source_note_id"])
        content_hash = normalized_text_hash(front_text, back_text)
        category = derive_category(front_text, back_text)
        imported.append(
            ImportedCard(
                card_id=f"anki-{source_card_id}",
                front_text=front_text,
                back_html_sanitized=back_html,
                back_text=back_text,
                source_note_id=source_note_id,
                source_card_id=source_card_id,
                source_ord=int(row["source_ord"] or 0),
                tags=[tag for tag in str(row["tags"] or "").split() if tag],
                category_slug=category.slug,
                category_title=category.title,
                content_sha256=content_hash,
            )
        )

    if not imported:
        raise RuntimeError("No usable Anki cards were found in the package.")
    return imported


def build_artifact(
    *,
    package_path: Path,
    subject_slug: str,
    deck_slug: str,
    title: str,
    cards: list[ImportedCard],
    collection_member: str,
) -> dict[str, Any]:
    category_counts: dict[tuple[str, str], int] = {}
    for card in cards:
        key = (card.category_slug, card.category_title)
        category_counts[key] = category_counts.get(key, 0) + 1
    categories = [
        {"slug": slug, "title": title, "card_count": count}
        for (slug, title), count in sorted(
            category_counts.items(),
            key=lambda item: (-item[1], item[0][1].casefold(), item[0][0]),
        )
    ]
    return {
        "version": 1,
        "artifact_type": "freudd_flashcards",
        "subject_slug": subject_slug,
        "deck_slug": deck_slug,
        "title": title,
        "source_file": package_path.name,
        "source_sha256": source_sha256(package_path),
        "source_collection": collection_member,
        "generated_at": zip_generated_at(package_path),
        "card_count": len(cards),
        "categories": categories,
        "cards": [
            {
                "card_id": card.card_id,
                "front_text": card.front_text,
                "back_html_sanitized": card.back_html_sanitized,
                "back_text": card.back_text,
                "source_note_id": card.source_note_id,
                "source_card_id": card.source_card_id,
                "source_ord": card.source_ord,
                "tags": card.tags,
                "category_slug": card.category_slug,
                "category_title": card.category_title,
                "content_sha256": card.content_sha256,
            }
            for card in cards
        ],
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path, help="Path to the .apkg source file.")
    parser.add_argument("--output", type=Path, required=True, help="Output Freudd flashcards JSON artifact.")
    parser.add_argument("--subject-slug", default="bioneuro", help="Freudd subject slug.")
    parser.add_argument("--deck-slug", default=DEFAULT_DECK_SLUG, help="Freudd deck slug.")
    parser.add_argument("--title", default=DEFAULT_TITLE, help="Learner-facing deck title.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    package_path = args.package.resolve()
    if not package_path.is_file():
        raise SystemExit(f"Anki package does not exist: {package_path}")

    with tempfile.TemporaryDirectory() as temp_dir:
        database_path = Path(temp_dir) / "collection.sqlite"
        collection_member = extract_collection_database(package_path, database_path)
        cards = load_cards_from_database(database_path)

    artifact = build_artifact(
        package_path=package_path,
        subject_slug=str(args.subject_slug).strip().lower(),
        deck_slug=str(args.deck_slug).strip().lower(),
        title=str(args.title).strip() or DEFAULT_TITLE,
        cards=cards,
        collection_member=collection_member,
    )
    write_json(args.output, artifact)
    print(f"Imported cards: {len(cards)}")
    print(f"Collection: {collection_member}")
    print(f"Output: {args.output}")


if __name__ == "__main__":
    main()
