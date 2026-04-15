#!/usr/bin/env python3
"""
RedditStudy pipeline orchestrator for Personlighedspsykologi.

Runs Layers 2–5 of the content pipeline (content-pipeline.md) for a given week,
using the existing content manifest, reading summaries, weekly overview summaries,
and (when available) full PDF text extracted from OneDrive-synced reading files.

Usage:
    python generate_reddit_threads.py --week W01 --lecture L1
    python generate_reddit_threads.py --week W11 --lecture L2 --dry-run
    python generate_reddit_threads.py --week W01 --lecture L1 --layer 4 --thread-id W01T1
    python generate_reddit_threads.py --week W11 --lecture L2 --no-pdf  # skip PDF extraction

Outputs are written to:
    shows/personlighedspsykologi-en/reddit/<lecture_key>/
    ├── week_plan.json
    ├── reading_chunks_<reading_id>.json  (one per reading)
    ├── thread_<thread_id>.json           (one per planned thread)
    └── weekly_feed.json

Requirements:
    pip install anthropic pypdf
    ANTHROPIC_API_KEY environment variable must be set.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

try:
    import anthropic
except ImportError:
    anthropic = None  # type: ignore[assignment]

# ─── Paths ────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parents[3]
SHOW_DIR = REPO_ROOT / "shows" / "personlighedspsykologi-en"
REDDIT_DIR = SHOW_DIR / "reddit"
CONTENT_MANIFEST = SHOW_DIR / "content_manifest.json"
READING_SUMMARIES = SHOW_DIR / "reading_summaries.json"
WEEKLY_OVERVIEW_SUMMARIES = SHOW_DIR / "weekly_overview_summaries.json"
OVERBLIK = SHOW_DIR / "docs" / "overblik.md"

# ─── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ─── Claude client ────────────────────────────────────────────────────────────

MODEL = "claude-opus-4-6"  # Most capable for creative + analytical pipeline
MODEL_FAST = "claude-sonnet-4-6"  # Faster for extraction layers (3)

# Max chars of PDF text to include per reading.
# ~4000 chars ≈ 2 pages; enough to give the LLM real content without blowing context.
PDF_TEXT_MAX_CHARS = 6000


def call_claude(system: str, user: str, model: str = MODEL, max_tokens: int = 8192) -> dict[str, Any]:
    """Call Claude and parse JSON response. Retries once on rate limit."""
    if anthropic is None:
        raise RuntimeError("anthropic package not installed — pip install anthropic")
    client = anthropic.Anthropic()
    for attempt in range(2):
        try:
            message = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            raw = message.content[0].text.strip()
            # Strip any accidental markdown fencing
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            return json.loads(raw)
        except anthropic.RateLimitError:
            if attempt == 0:
                log.warning("Rate limit hit, waiting 60s...")
                time.sleep(60)
            else:
                raise
        except json.JSONDecodeError as e:
            log.error("JSON parse failed: %s\nRaw output:\n%s", e, raw[:500])
            raise


# ─── PDF text extraction ─────────────────────────────────────────────────────

def extract_pdf_text(pdf_path: Path, max_chars: int = PDF_TEXT_MAX_CHARS) -> str | None:
    """Extract text from a PDF using pypdf. Returns None on failure."""
    try:
        from pypdf import PdfReader
    except ImportError:
        log.debug("pypdf not installed — skipping PDF extraction")
        return None

    if not pdf_path.exists():
        return None

    try:
        reader = PdfReader(str(pdf_path))
        text_parts: list[str] = []
        total = 0
        for page in reader.pages:
            page_text = page.extract_text() or ""
            text_parts.append(page_text)
            total += len(page_text)
            if total >= max_chars:
                break
        text = "\n".join(text_parts)
        if len(text) > max_chars:
            text = text[:max_chars] + "\n[...truncated...]"
        return text.strip() or None
    except Exception as e:
        log.debug("PDF extraction failed for %s: %s", pdf_path.name, e)
        return None


# ─── Data loaders ─────────────────────────────────────────────────────────────

def load_manifest() -> dict:
    with open(CONTENT_MANIFEST) as f:
        return json.load(f)


def load_reading_summaries() -> dict:
    with open(READING_SUMMARIES) as f:
        return json.load(f)


def load_weekly_overview_summaries() -> dict:
    if not WEEKLY_OVERVIEW_SUMMARIES.exists():
        return {"by_name": {}}
    with open(WEEKLY_OVERVIEW_SUMMARIES) as f:
        return json.load(f)


def find_lecture(manifest: dict, week: str, lecture: str) -> dict | None:
    """Find a lecture in the manifest by week and lecture number."""
    week_num = week.lstrip("W").lstrip("0") or "0"
    for lec in manifest.get("lectures", []):
        lk = lec.get("lecture_key", "")
        # W01L1, W1L1, w01l1 all match
        lk_num = lk.lstrip("Ww").split("L")[0].lstrip("0") or "0"
        lk_lec = lk.split("L")[-1] if "L" in lk else ""
        target_lec = lecture.lstrip("Ll")
        if lk_num == week_num and lk_lec == target_lec:
            return lec
    return None


def _find_reading_summary(
    title: str,
    source_filename: str,
    lecture_key: str,
    by_name: dict[str, dict],
) -> dict | None:
    """
    Match a reading from the content manifest to its entry in reading_summaries.json.

    The reading_summaries keys are audio episode filenames like:
      "W11L2 - Raggatt (2002) [EN].mp3"
    The manifest title might be:
      "Raggatt (2002) (Øvelseshold)"

    Strategy: normalize both sides and match on the author/title core.
    """
    # Extract the core: strip (Øvelseshold), whitespace, lecture key prefix
    def core(s: str) -> str:
        s = s.lower()
        s = re.sub(r"\(øvelseshold\)", "", s)
        s = re.sub(r"\(tekst for øvelseshold\)", "", s)
        s = re.sub(r"^\[(?:short|brief)\]\s*", "", s)
        s = re.sub(r"\s*\[en\].*$", "", s)
        s = re.sub(r"\s*\.mp3$", "", s)
        # Strip leading W#L# -
        s = re.sub(r"^w\d+l\d+\s*[-–]\s*", "", s)
        return s.strip()

    title_core = core(title)
    source_core = core(source_filename) if source_filename else ""

    # Normalize further for fuzzy matching: / → -, strip periods after "et al"
    def normalize_extra(s: str) -> str:
        s = s.replace("/", "-").replace(" + ", " og ")
        s = re.sub(r"\bet al\b\.?", "et al", s)
        return s

    title_core_n = normalize_extra(title_core)
    source_core_n = normalize_extra(source_core) if source_core else ""

    # Also extract "Surname (Year)" pattern for fallback matching
    surname_year = re.match(r"^([a-zæøåäöü]+)\s*[,.]?\s*\w*\.?\s*\((\d{4})", title_core)
    surname_year_pat = None
    if surname_year:
        surname_year_pat = re.compile(
            re.escape(surname_year.group(1)) + r"[^(]*\(" + re.escape(surname_year.group(2)) + r"\)"
        )

    lk_lower = lecture_key.lower().replace("w0", "w")

    best: dict | None = None
    for ep_key, ep_data in by_name.items():
        # Skip short variants - prefer the full version.
        if re.match(r"^\[(?:short|brief)\]", ep_key, re.IGNORECASE):
            continue
        # Check lecture_key match first (W11L2 in key)
        ep_lk_match = re.match(r"^(w\d+l\d+)", ep_key.lower())
        if ep_lk_match:
            ep_lk = ep_lk_match.group(1).replace("w0", "w")
            if ep_lk != lk_lower:
                continue

        ep_core = core(ep_key)
        ep_core_n = normalize_extra(ep_core)

        # Direct substring match
        if title_core and title_core in ep_core:
            best = ep_data
            break
        if source_core and source_core in ep_core:
            best = ep_data
            break
        if ep_core and ep_core in title_core:
            best = ep_data
            break
        # Normalized match (/ → -, "et al" normalization, + → og)
        if title_core_n and title_core_n in ep_core_n:
            best = ep_data
            break
        if source_core_n and source_core_n in ep_core_n:
            best = ep_data
            break
        if ep_core_n and ep_core_n in title_core_n:
            best = ep_data
            break
        # Surname(Year) fuzzy match — handles "Bank (2014)" vs "Bank, M. (2014)..."
        if surname_year_pat and surname_year_pat.search(ep_core_n):
            best = ep_data
            break
    return best


def _find_weekly_overview(lecture_key: str, overviews: dict) -> dict | None:
    """Find the weekly overview summary for a lecture key."""
    lk_lower = lecture_key.lower().replace("w0", "w")
    for ep_key, ep_data in overviews.get("by_name", {}).items():
        if "alle kilder" not in ep_key.lower():
            continue
        ep_lk_match = re.match(r"^(w\d+l\d+)", ep_key.lower())
        if ep_lk_match:
            ep_lk = ep_lk_match.group(1).replace("w0", "w")
            if ep_lk == lk_lower:
                return ep_data
    return None


def _resolve_pdf_path(reading: dict, summaries_by_name: dict, lecture_key: str) -> Path | None:
    """Try to find the local PDF path for a reading via reading_summaries metadata."""
    title = reading.get("reading_title", "")
    source_filename = reading.get("source_filename", "")
    rs = _find_reading_summary(title, source_filename, lecture_key, summaries_by_name)
    if rs:
        src = (rs.get("meta") or {}).get("source_file")
        if src:
            p = Path(src)
            if p.exists():
                return p
    return None


def build_reading_context(
    lecture: dict,
    summaries: dict,
    overviews: dict,
    extract_pdfs: bool = True,
) -> list[dict]:
    """
    Build reading context from the content manifest lecture entry.

    Layers:
    1. Manifest summaries (always available for 58/59 readings)
    2. reading_summaries.json enrichment (matched via improved fuzzy logic)
    3. PDF text extraction (when OneDrive-synced PDFs are on disk)
    """
    lecture_key = lecture.get("lecture_key", "")
    by_name = summaries.get("by_name", {})
    readings = []

    for reading in lecture.get("readings", []):
        reading_id = reading.get("reading_key", "")
        title = reading.get("reading_title", "")
        source_filename = reading.get("source_filename", "")
        is_missing = reading.get("is_missing", False)
        summary_data = reading.get("summary") or {}

        context: dict[str, Any] = {
            "reading_id": reading_id,
            "title": title,
            "source_filename": source_filename,
            "is_missing": is_missing,
            "summary_lines": summary_data.get("summary_lines", []),
            "key_points": summary_data.get("key_points", []),
        }

        # Enrichment from reading_summaries.json
        rs = _find_reading_summary(title, source_filename, lecture_key, by_name)
        if rs:
            context["rich_summary_lines"] = rs.get("summary_lines", [])
            context["rich_key_points"] = rs.get("key_points", [])
            context["_rs_matched"] = True
        else:
            context["_rs_matched"] = False

        # PDF text extraction
        if extract_pdfs and not is_missing:
            pdf_path = _resolve_pdf_path(reading, by_name, lecture_key)
            if pdf_path:
                pdf_text = extract_pdf_text(pdf_path)
                if pdf_text:
                    context["pdf_text"] = pdf_text
                    context["_pdf_chars"] = len(pdf_text)

        readings.append(context)

    return readings


def build_week_context(lecture: dict, overviews: dict) -> dict:
    """
    Build the course context for a lecture — replaces the old course_map.json dependency.
    Derived entirely from content_manifest.json + weekly_overview_summaries.json.
    """
    lecture_key = lecture.get("lecture_key", "")
    lecture_title = lecture.get("lecture_title", "")
    lecture_summary = lecture.get("summary") or {}
    readings = lecture.get("readings", [])

    # Weekly overview summary (cross-reading synthesis)
    overview = _find_weekly_overview(lecture_key, overviews)

    return {
        "lecture_key": lecture_key,
        "topic": lecture_title,
        "lecture_summary": {
            "summary_lines": lecture_summary.get("summary_lines", []),
            "key_points": lecture_summary.get("key_points", []),
        },
        "weekly_overview": {
            "summary_lines": overview.get("summary_lines", []) if overview else [],
            "key_points": overview.get("key_points", []) if overview else [],
        },
        "readings": [
            {
                "reading_id": r.get("reading_key", ""),
                "title": r.get("reading_title", ""),
                "is_missing": r.get("is_missing", False),
            }
            for r in readings
        ],
    }


# ─── Layer 2: Week Planner ────────────────────────────────────────────────────

LAYER_2_SYSTEM = """You are an expert educational content strategist specialising in active learning design
for psychology students. Your task is to analyse the readings for a single university
lecture week and design a Reddit-style thread sequence that covers the key concepts.

You will output a single JSON object and nothing else — no markdown fencing, no prose.

DESIGN PRINCIPLES:
1. Each thread must serve a clear pedagogical purpose — not just "cover content".
2. Readings should talk to each other: look for overlap, tension, complementarity, and gaps.
3. Choose the subreddit that activates the most productive thinking mode for each topic.
4. Sequence threads so the week builds: foundational understanding first, then complexity,
   then synthesis and critique.
5. The total thread count should be 3 to 6 threads per week.
   Fewer, richer threads are better than many thin ones.
6. Use the lecture-level overview summary to understand how the readings fit together
   before planning individual threads.

SUBREDDIT OPTIONS: explainlikeimfive, AmItheAsshole, changemyview, AskScience,
todayilearned, AcademicPsychology, OutOfTheLoop, AskPsychology

THREAD TYPES:
- "synthesis": Combines content from 2+ readings into one thread.
- "deep_dive": One reading gets its own thread.
- "debate": Pits two readings or positions against each other.
- "bridge": Connects current week to a previous week.
- "application": Takes theory and asks "so what?" in a practical context.

COMMENT THREAD PATTERNS (pick 2-3 per thread):
- "correction_chain": Simple → nuanced → exception
- "analogy_thread": Analogy → limitation → better analogy
- "source_battle": Claim → "source?" → citation → critique
- "personal_experience": Anecdote → research connection
- "debate_fork": Position A → Position B → synthesis
- "eli5_within_thread": Dense answer → "ELI5?" → simple version

INPUT NOTES:
- You receive summaries and key points per reading, a lecture-level overview, and (when
  available) extracted PDF text for deeper context.
- Readings marked is_missing=true have no content — do not plan threads around them.
- source_readings in your output should use the reading_id values from the input."""


def run_layer_2(
    lecture_key: str,
    week_context: dict,
    readings: list[dict],
    dry_run: bool = False,
) -> dict:
    log.info("Layer 2 — Week Planner for %s", lecture_key)

    readings_text = ""
    for r in readings:
        if r.get("is_missing"):
            readings_text += f'\n<reading id="{r["reading_id"]}" title="{r["title"]}" status="MISSING" />\n'
            continue
        readings_text += f'\n<reading id="{r["reading_id"]}" title="{r["title"]}">\n'
        if r.get("summary_lines"):
            readings_text += "Summary:\n"
            for line in r["summary_lines"]:
                readings_text += f"  - {line}\n"
        if r.get("key_points"):
            readings_text += "Key points:\n"
            for point in r["key_points"]:
                readings_text += f"  - {point}\n"
        if r.get("pdf_text"):
            readings_text += f"\nExtracted text (first ~{r.get('_pdf_chars', '?')} chars):\n"
            readings_text += r["pdf_text"] + "\n"
        elif r.get("rich_summary_lines"):
            readings_text += "Additional context:\n"
            for line in r["rich_summary_lines"]:
                readings_text += f"  - {line}\n"
        readings_text += "</reading>\n"

    user_prompt = f"""Here is the lecture context for this week:

<lecture_context>
{json.dumps(week_context, ensure_ascii=False, indent=2)}
</lecture_context>

Here are the readings for this week:
{readings_text}

Design the complete thread plan for this week as a JSON object with these fields:
- lecture_key: string
- week_topic: string
- reading_analysis: array of {{reading_id, core_argument, key_concepts, relates_to: array of {{reading_id, relationship, note}}}}
- threads: array of {{thread_id, thread_type, subreddit, source_readings, post_title_sketch, post_body_sketch, comment_patterns, sequence_position, pedagogical_purpose}}
- thread_sequence_rationale: string"""

    if dry_run:
        log.info("[DRY RUN] Would call Layer 2")
        log.info("  User prompt: %d chars", len(user_prompt))
        log.info("  Readings with PDF text: %d/%d",
                 sum(1 for r in readings if r.get("pdf_text")), len(readings))
        log.info("  Readings with summaries: %d/%d",
                 sum(1 for r in readings if r.get("summary_lines")), len(readings))
        return {"lecture_key": lecture_key, "threads": [], "_dry_run": True}

    return call_claude(LAYER_2_SYSTEM, user_prompt)


# ─── Layer 3: Reading Processor ───────────────────────────────────────────────

LAYER_3_SYSTEM = """You are an expert academic content extractor. Your task is to process a single academic
reading and extract all content needed to generate Reddit-style threads about it.

You will output a single JSON object and nothing else — no markdown fencing, no prose.

EXTRACTION RULES:
1. Preserve ALL specific claims, findings, statistics, and arguments exactly as stated.
2. Identify key terms and provide their definitions as used in this reading.
3. Flag contested or surprising claims — these are high-value for thread generation.
4. Assign each chunk to the threads listed in thread_assignments.
5. Each chunk should be one coherent idea unit (~100-200 words of source content).

INPUT NOTES:
- You may receive extracted PDF text, summaries, or both.
- When PDF text is available, extract chunks from the actual text — this is primary.
- When only summaries are available, extract what you can and mark chunks as
  content_type "summary_derived".
- Do not invent claims not present in the input."""


def run_layer_3(
    reading: dict,
    thread_assignments: list[dict],
    dry_run: bool = False,
) -> dict:
    reading_id = reading["reading_id"]
    log.info("Layer 3 — Reading Processor for %s", reading_id)

    reading_text = ""
    if reading.get("pdf_text"):
        reading_text += f"Full text (extracted from PDF, first ~{reading.get('_pdf_chars', '?')} chars):\n"
        reading_text += reading["pdf_text"] + "\n\n"
    if reading.get("summary_lines"):
        reading_text += "Summary:\n"
        for line in reading["summary_lines"]:
            reading_text += f"  - {line}\n"
    if reading.get("key_points"):
        reading_text += "Key points:\n"
        for point in reading["key_points"]:
            reading_text += f"  - {point}\n"

    user_prompt = f"""Here is the reading:

<reading id="{reading_id}" title="{reading['title']}">
{reading_text}
</reading>

Here are the thread assignments for this reading:
<thread_assignments>
{json.dumps(thread_assignments, ensure_ascii=False, indent=2)}
</thread_assignments>

Extract all content chunks as JSON with these fields:
- reading_id: string
- reading_title: string
- chunks: array of {{chunk_id, content_type, source_text, extracted_claim, key_terms, statistics, citations, assigned_threads, is_contested_in_text, is_inferred, pedagogy_note}}
- unassigned_chunks: array of chunk_ids
- key_terms_glossary: array of {{term, definition, chunk_ids}}"""

    if dry_run:
        log.info("[DRY RUN] Would call Layer 3 for %s (%s)",
                 reading_id, "with PDF" if reading.get("pdf_text") else "summary only")
        return {"reading_id": reading_id, "chunks": [], "_dry_run": True}

    return call_claude(LAYER_3_SYSTEM, user_prompt, model=MODEL_FAST)


# ─── Layer 4: Thread Generator ────────────────────────────────────────────────

LAYER_4_SYSTEM = """You are an expert at writing realistic Reddit threads that teach university-level psychology
without readers realising they are being taught. Your threads must be academically accurate
AND genuinely engaging. Both requirements are non-negotiable.

You will output a single JSON object and nothing else — no markdown fencing, no prose.

AUTHENTICITY RULES:
1. Reddit users do not lecture. They share observations, argue, correct each other, admit
   uncertainty, tell stories, make jokes occasionally, and sometimes get things wrong
   before being corrected.
2. Every commenter has a distinct voice: the confident expert, the curious student,
   the pedantic corrector, the personal-experience-sharer, the skeptic, the synthesiser.
3. Upvotes reflect engagement quality: clarity, surprise, being right, good analogies.
4. Awards are rare (0–2 per thread). Post titles must sound like real Reddit.
5. At least one commenter should be wrong about something minor and get corrected.
6. At least one moment of genuine surprise, humour, or personal connection.

ACCURACY RULES:
1. Every factual claim must be traceable to the provided chunks.
2. Do not fabricate studies, statistics, or author names.
3. Key terms from the glossary must appear and be implicitly defined in context.
4. Contested claims must be represented as contested in the thread.

SUBREDDIT FORMAT RULES:
- r/explainlikeimfive: "ELI5: ..." post, accessible top comment with analogies
- r/AmItheAsshole: first-person narrative dilemma, NTA/YTA verdict comments
- r/changemyview: "CMV: ..." with clear thesis, delta granted in comments
- r/AskScience: precise question, expert-register answer, methodological caveats
- r/todayilearned: "TIL ..." punchy one-liner, reactions + depth in comments
- r/AcademicPsychology: any format, full academic register, no dumbing down
- r/OutOfTheLoop: "What's the deal with ...?" historical overview response
- r/AskPsychology: personal question, theory-to-practice bridge in comments

Generate 6–12 comments per thread. Use nested replies (parent_id = comment id) for depth.

SELF-CHECK — complete after generating and include in output:
- all_key_terms_embedded: true/false
- missing_key_terms: array of terms not used
- no_fabricated_claims: true (affirm)
- feels_authentic: true/false + note if false"""


def run_layer_4(
    thread_plan: dict,
    chunks_by_reading: dict[str, dict],
    lecture_key: str,
    dry_run: bool = False,
) -> dict:
    thread_id = thread_plan["thread_id"]
    log.info("Layer 4 — Thread Generator for %s (%s / r/%s)",
             thread_id, thread_plan.get("thread_type"), thread_plan.get("subreddit"))

    # Collect all chunks assigned to this thread
    assigned_chunks = []
    combined_glossary = {}

    for reading_id, chunks_data in chunks_by_reading.items():
        for chunk in chunks_data.get("chunks", []):
            if thread_id in chunk.get("assigned_threads", []):
                assigned_chunks.append({**chunk, "_reading_id": reading_id})
        for term_entry in chunks_data.get("key_terms_glossary", []):
            term = term_entry["term"]
            if term not in combined_glossary:
                combined_glossary[term] = term_entry

    chunks_text = ""
    for chunk in assigned_chunks:
        chunks_text += f'\n<chunk id="{chunk["chunk_id"]}" reading="{chunk["_reading_id"]}">\n'
        chunks_text += json.dumps({k: v for k, v in chunk.items() if k != "_reading_id"},
                                   ensure_ascii=False, indent=2)
        chunks_text += "\n</chunk>\n"

    user_prompt = f"""Here is the thread plan:
<thread_plan>
{json.dumps(thread_plan, ensure_ascii=False, indent=2)}
</thread_plan>

Lecture key: {lecture_key}

Here are the content chunks assigned to this thread:
{chunks_text}

Here is the key terms glossary:
<glossary>
{json.dumps(list(combined_glossary.values()), ensure_ascii=False, indent=2)}
</glossary>

Generate the complete Reddit thread as JSON with these fields:
- thread_id, lecture_key, subreddit, subreddit_icon, subreddit_color
- content_metadata: {{source_readings, key_terms_embedded, concept_cluster}}
- post: {{title, body, author, author_flair, upvotes, awards, timestamp, flair, comment_count}}
- comments: array of {{id, author, author_flair, body, upvotes, awards, timestamp, parent_id, depth}}
- sidebar: {{key_terms: array of {{term, definition}}, related_threads: []}}
- quality_self_check: {{all_key_terms_embedded, missing_key_terms, no_fabricated_claims, feels_authentic, authenticity_note}}"""

    if dry_run:
        log.info("[DRY RUN] Would call Layer 4 for %s (%d chunks, %d glossary terms)",
                 thread_id, len(assigned_chunks), len(combined_glossary))
        return {"thread_id": thread_id, "_dry_run": True}

    return call_claude(LAYER_4_SYSTEM, user_prompt, max_tokens=16384)


# ─── Layer 5: Weekly Curator ──────────────────────────────────────────────────

LAYER_5_SYSTEM = """You are an expert educational content curator. Your task is to assemble a weekly
Reddit-style learning feed from a set of generated threads, optimise their sequence,
add cross-references, and produce a pinned overview post.

You will output a single JSON object and nothing else — no markdown fencing, no prose.

ASSEMBLY RULES:
1. The pinned post (position 0) comes first — it's a weekly study guide.
2. Sequence threads: foundational → complexity → synthesis → critique/debate.
3. Insert cross-references between related threads.
4. Escalate any Layer 4 self-check failures.
5. Flag threads that may have low engagement (few comments, no analogy, academic-only register).
6. Estimate total read time: ~4 min per thread + 1 min per 5 comments."""


def run_layer_5(lecture_key: str, week_plan: dict, threads: list[dict], dry_run: bool = False) -> dict:
    log.info("Layer 5 — Weekly Curator for %s (%d threads)", lecture_key, len(threads))

    threads_text = ""
    for thread in threads:
        threads_text += f'\n<thread id="{thread.get("thread_id")}">\n'
        summary = {
            "thread_id": thread.get("thread_id"),
            "subreddit": thread.get("subreddit"),
            "post_title": thread.get("post", {}).get("title"),
            "comment_count": thread.get("post", {}).get("comment_count"),
            "content_metadata": thread.get("content_metadata"),
            "quality_self_check": thread.get("quality_self_check"),
        }
        threads_text += json.dumps(summary, ensure_ascii=False, indent=2)
        threads_text += "\n</thread>\n"

    user_prompt = f"""Here is the week plan:
<week_plan>
{json.dumps(week_plan, ensure_ascii=False, indent=2)}
</week_plan>

Here are the generated threads:
{threads_text}

Assemble the weekly feed as JSON with these fields:
- lecture_key, week_topic, estimated_total_read_time_minutes
- threads: array of {{thread_id, position, is_pinned, cross_references}}
- pinned_overview: {{thread_id: "pinned", post: {{title, body, author, author_flair, upvotes, awards, timestamp, flair, comment_count}}, comments: []}}
- quality_warnings: array of {{thread_id, warning_type, note}}
- layer4_escalations: array of {{thread_id, issue}}"""

    if dry_run:
        log.info("[DRY RUN] Would call Layer 5 for %s", lecture_key)
        return {"lecture_key": lecture_key, "_dry_run": True}

    return call_claude(LAYER_5_SYSTEM, user_prompt)


# ─── Pipeline orchestrator ────────────────────────────────────────────────────

def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log.info("Saved: %s", path.relative_to(REPO_ROOT))


def run_pipeline(
    week: str,
    lecture: str,
    dry_run: bool = False,
    start_at_layer: int = 2,
    single_thread_id: str | None = None,
    extract_pdfs: bool = True,
) -> None:
    week_num = week.lstrip("W").zfill(2)
    lecture_upper = lecture.upper()
    if not lecture_upper.startswith("L"):
        lecture_upper = "L" + lecture_upper
    lecture_key = f"W{week_num}{lecture_upper}"
    out_dir = REDDIT_DIR / lecture_key

    log.info("=" * 60)
    log.info("RedditStudy pipeline — %s", lecture_key)
    log.info("Output directory: %s", out_dir.relative_to(REPO_ROOT))
    if dry_run:
        log.info("[DRY RUN MODE — no API calls will be made]")
    if not extract_pdfs:
        log.info("[PDF extraction disabled — using summaries only]")
    log.info("=" * 60)

    # Load source data
    manifest = load_manifest()
    summaries = load_reading_summaries()
    overviews = load_weekly_overview_summaries()

    lecture_entry = find_lecture(manifest, week, lecture)
    if not lecture_entry:
        log.error("Lecture %s not found in content manifest", lecture_key)
        log.error("Available: %s", ", ".join(
            l["lecture_key"] for l in manifest.get("lectures", [])
        ))
        sys.exit(1)

    week_context = build_week_context(lecture_entry, overviews)
    readings = build_reading_context(lecture_entry, summaries, overviews, extract_pdfs=extract_pdfs)

    # ── Data summary ──────────────────────────────────────────────────────────
    log.info("Lecture: %s", lecture_entry.get("lecture_title", ""))
    log.info("Readings: %d total, %d with PDF text, %d with manifest summary",
             len(readings),
             sum(1 for r in readings if r.get("pdf_text")),
             sum(1 for r in readings if r.get("summary_lines")))
    has_overview = bool(week_context["weekly_overview"]["summary_lines"])
    log.info("Weekly overview summary: %s", "yes" if has_overview else "no")
    for r in readings:
        sources = []
        if r.get("pdf_text"):
            sources.append(f"pdf({r.get('_pdf_chars', '?')}ch)")
        if r.get("summary_lines"):
            sources.append("manifest")
        if r.get("_rs_matched"):
            sources.append("rs.json")
        if r.get("is_missing"):
            sources.append("MISSING")
        log.info("  %s: %s", r["title"][:50], " + ".join(sources) if sources else "NO DATA")

    # ── Layer 2: Week Planner ──────────────────────────────────────────────────
    week_plan_path = out_dir / "week_plan.json"
    if start_at_layer <= 2:
        week_plan = run_layer_2(lecture_key, week_context, readings, dry_run=dry_run)
        if not dry_run:
            save_json(week_plan_path, week_plan)
    elif week_plan_path.exists():
        log.info("Skipping Layer 2, loading existing week_plan.json")
        with open(week_plan_path) as f:
            week_plan = json.load(f)
    else:
        log.error("Cannot skip Layer 2 — %s does not exist", week_plan_path)
        sys.exit(1)

    if dry_run:
        log.info("[DRY RUN] Pipeline data audit complete")
        return

    threads_to_generate = week_plan.get("threads", [])
    if single_thread_id:
        threads_to_generate = [t for t in threads_to_generate if t["thread_id"] == single_thread_id]
        if not threads_to_generate:
            log.error("Thread %s not found in week plan", single_thread_id)
            sys.exit(1)

    # ── Layer 3: Reading Processor ─────────────────────────────────────────────
    chunks_by_reading: dict[str, dict] = {}
    if start_at_layer <= 3:
        for reading in readings:
            if reading.get("is_missing"):
                continue
            reading_id = reading["reading_id"]
            # Find which threads use this reading
            thread_assignments = [
                t for t in week_plan.get("threads", [])
                if reading_id in t.get("source_readings", [])
            ]
            if not thread_assignments:
                log.warning("Reading %s not assigned to any thread, skipping", reading_id[:40])
                continue

            chunks = run_layer_3(reading, thread_assignments)
            chunks_by_reading[reading_id] = chunks

            # Use a safe filename
            safe_id = re.sub(r"[^a-z0-9-]", "", reading_id[:30])
            chunks_path = out_dir / f"reading_chunks_{safe_id}.json"
            save_json(chunks_path, chunks)
    else:
        for chunks_file in out_dir.glob("reading_chunks_*.json"):
            with open(chunks_file) as f:
                data = json.load(f)
            chunks_by_reading[data.get("reading_id", chunks_file.stem)] = data
        log.info("Loaded %d existing chunk files", len(chunks_by_reading))

    # ── Layer 4: Thread Generator ──────────────────────────────────────────────
    generated_threads = []
    if start_at_layer <= 4:
        for thread_plan in threads_to_generate:
            thread_id = thread_plan["thread_id"]
            thread_path = out_dir / f"thread_{thread_id}.json"

            thread_data = run_layer_4(thread_plan, chunks_by_reading, lecture_key)
            save_json(thread_path, thread_data)
            generated_threads.append(thread_data)

            qsc = thread_data.get("quality_self_check", {})
            if not qsc.get("all_key_terms_embedded"):
                log.warning("Thread %s missing key terms: %s",
                            thread_id, qsc.get("missing_key_terms"))
            if not qsc.get("feels_authentic"):
                log.warning("Thread %s authenticity flag: %s",
                            thread_id, qsc.get("authenticity_note"))
    else:
        for thread_file in sorted(out_dir.glob("thread_W*.json")):
            with open(thread_file) as f:
                generated_threads.append(json.load(f))
        log.info("Loaded %d existing thread files", len(generated_threads))

    if not generated_threads:
        log.warning("No threads generated — skipping Layer 5")
        return

    # ── Layer 5: Weekly Curator ────────────────────────────────────────────────
    if start_at_layer <= 5 and not single_thread_id:
        weekly_feed = run_layer_5(lecture_key, week_plan, generated_threads)
        save_json(out_dir / "weekly_feed.json", weekly_feed)

        warnings = weekly_feed.get("quality_warnings", [])
        if warnings:
            log.warning("%d quality warnings — review weekly_feed.json", len(warnings))

        log.info("Feed estimated read time: %s min",
                 weekly_feed.get("estimated_total_read_time_minutes"))

    log.info("Pipeline complete for %s", lecture_key)
    log.info("Output: %s", out_dir.relative_to(REPO_ROOT))


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="RedditStudy pipeline for Personlighedspsykologi",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--week", required=True, help="Week number, e.g. W01 or 1")
    parser.add_argument("--lecture", required=True, help="Lecture, e.g. L1 or L2")
    parser.add_argument("--dry-run", action="store_true",
                        help="Audit data only — no API calls, no file writes")
    parser.add_argument("--no-pdf", action="store_true",
                        help="Skip PDF text extraction, use summaries only")
    parser.add_argument("--layer", type=int, default=2, choices=[2, 3, 4, 5],
                        help="Start from this layer (skip earlier, load existing outputs)")
    parser.add_argument("--thread-id", default=None,
                        help="Regenerate a single thread only (e.g. W01T1)")

    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY") and not args.dry_run:
        log.error("ANTHROPIC_API_KEY not set")
        sys.exit(1)

    run_pipeline(
        week=args.week,
        lecture=args.lecture,
        dry_run=args.dry_run,
        start_at_layer=args.layer,
        single_thread_id=args.thread_id,
        extract_pdfs=not args.no_pdf,
    )


if __name__ == "__main__":
    main()
