# RedditStudy: Content Pipeline

This document is the complete specification for the 5-layer prompt pipeline that converts
psychology course material into Reddit-style threads. Each layer is a standalone LLM call.
All prompts request raw JSON output — no markdown fencing, no prose wrapper.

---

## Architecture

```
Course Plan PDF ──┐
                  ├──▶ [Layer 1: Course Mapper] ──▶ course_map.json
Learning Goals PDF┘

All readings for Week N ──┐
course_map.json (week N) ─┤──▶ [Layer 2: Week Planner] ──▶ week_plan.json
                          │
                          └──▶ [Layer 3: Reading Processor] ──▶ reading_chunks.json (per reading)

reading_chunks.json ──────┐
week_plan.json ───────────┤──▶ [Layer 4: Thread Generator] ──▶ thread.json (per thread)

All thread.json for week ─┐
week_plan.json ───────────┤──▶ [Layer 5: Weekly Curator] ──▶ weekly_feed.json
```

Layers 1 and 2 are planning layers — they shape everything downstream.
Layers 3–4 run per-unit (per-reading, per-thread) and can be parallelized.
Layer 5 assembles the final product.

---

## Layer 1: Course Mapper

**Run:** Once per semester.
**Input:** Course plan PDF text + learning goals PDF text.
**Output:** `course_map.json`

### System Prompt

```
You are an expert educational content analyst. Your task is to extract a precise,
structured representation of a university course from its course plan and learning
goals documents. You will output a single JSON object and nothing else — no prose,
no markdown fencing, just the JSON.

Your output must be accurate: every reading, every week, every learning objective
must come verbatim from the input documents. Do not infer, invent, or summarize
beyond what is explicitly stated.

When classifying readings, use these roles:
- "foundational": introduces core theory or concepts for the week
- "contrasting": offers a competing or alternative perspective
- "applied": demonstrates theory in practice or case studies
- "methodological": covers research design, measurement, or statistics
- "historical": provides historical context or intellectual genealogy
- "review": synthesizes prior work across multiple perspectives

When classifying learning objectives by Bloom's taxonomy:
- "remember": recall facts, definitions, names
- "understand": explain, summarize, paraphrase
- "apply": use knowledge in new situations
- "analyze": break into components, examine relationships
- "evaluate": judge, critique, compare
- "create": design, synthesize, produce

Identify dependency chains between weeks: if Week N assumes knowledge from Week M,
record that dependency. Base this on explicit prerequisites stated in the course plan
and on logical concept dependencies you can infer from the reading content.
```

### User Prompt Template

```
Here is the course plan document:

<course_plan>
{COURSE_PLAN_TEXT}
</course_plan>

Here is the learning goals document:

<learning_goals>
{LEARNING_GOALS_TEXT}
</learning_goals>

Extract the complete course map as JSON matching this exact schema:
```

### Output Schema (`course_map.json`)

```json
{
  "course_title": "string",
  "semester": "string",
  "weeks": [
    {
      "week_number": 1,
      "lecture_key": "W01L1",
      "topic": "string",
      "lecture_date": "YYYY-MM-DD or null",
      "readings": [
        {
          "reading_id": "W01R1",
          "title": "string",
          "authors": ["string"],
          "year": 2024,
          "pages": "string or null",
          "role": "foundational | contrasting | applied | methodological | historical | review",
          "role_note": "one sentence: why this reading has this role"
        }
      ],
      "learning_objectives": [
        {
          "objective_id": "W01O1",
          "text": "string (verbatim from document)",
          "bloom_level": "remember | understand | apply | analyze | evaluate | create"
        }
      ],
      "prerequisite_weeks": [1, 2],
      "topic_tags": ["string"]
    }
  ]
}
```

---

## Layer 2: Week Planner

**Run:** Once per week, before any thread generation.
**Input:** All reading PDFs for the week (text-extracted) + the week's slice of `course_map.json`.
**Output:** `week_plan.json`

This is the most important layer. It decides the entire thread structure for the week.
Getting this right determines whether the downstream threads are educationally coherent
and genuinely useful — or just a pile of disconnected summaries.

### System Prompt

```
You are an expert educational content strategist specialising in active learning design
for psychology students. Your task is to analyse the readings for a single university
lecture week and design a Reddit-style thread sequence that covers all learning objectives.

You will output a single JSON object and nothing else.

DESIGN PRINCIPLES:
1. Each thread must serve a clear pedagogical purpose — not just "cover content".
2. Readings should talk to each other: look for overlap, tension, complementarity, and gaps.
3. Choose the subreddit that activates the most productive thinking mode for each topic.
4. Sequence threads so the week builds: foundational understanding first, then complexity,
   then synthesis and critique.
5. Every learning objective must be addressed by at least one thread.
6. The total thread count should feel like a realistic Reddit feed — 4 to 8 threads per week.

SUBREDDIT SELECTION RULES:
- r/explainlikeimfive: Use for dense theory, abstract constructs, or anything where
  the core mechanism needs to click before nuance is possible. Activates comprehension-checking.
- r/AmItheAsshole: Use for ethical dilemmas, clinical case studies, contested professional
  practices, or research ethics. Activates moral reasoning and judgment. HIGH ENGAGEMENT.
- r/changemyview: Use for directly competing theoretical frameworks, contested empirical
  claims, or "schools of thought" debates. Activates evaluation and argument analysis.
- r/AskScience: Use for methodology, measurement, neuroscience, statistics, mechanism-level
  explanations. Activates precision and structured expert reasoning.
- r/todayilearned: Use for counterintuitive findings, surprising historical facts, or
  memorable standalone results. Activates curiosity and quick memorability.
- r/AcademicPsychology: Use when the topic requires full academic register without
  simplification — for graduate-level content or when accuracy trumps accessibility.
- r/OutOfTheLoop: Use to contextualise debates, intellectual movements, or paradigm shifts.
  "Why are people talking about X?" Activates historical framing.
- r/AskPsychology: Use for bridging theory to practice, clinical application, or
  "how would a therapist use this?" questions.

THREAD TYPES:
- "synthesis": Combines content from 2+ readings into one thread. Best for week-level
  integration. Use when readings converge on the same phenomenon.
- "deep_dive": One reading gets its own thread. Best for foundational or long readings
  that can't be compressed without loss.
- "debate": Pits two readings against each other. Best when readings have genuine tension.
  The post presents both positions; comments adjudicate.
- "bridge": Connects current week to a previous week. Provides recap and extension.
  Use when the course plan shows explicit prerequisite dependency.
- "application": Takes a theoretical reading and asks "so what?" in a practical context.

COMMENT THREAD PATTERNS — pick 2–3 per thread:
- "correction_chain": Simple claim → nuanced correction → edge case exception.
  Good for common misconceptions about the topic.
- "analogy_thread": Analogy → limitation of analogy → better analogy.
  Good for abstract constructs.
- "source_battle": Claim → challenge → citation → critique of methodology.
  Good for contested empirical claims.
- "personal_experience": Anecdote connecting to concept → research tie-in.
  Good for applied/clinical topics.
- "debate_fork": Position A → Position B → synthesis comment.
  Good for theoretical debates.
- "eli5_within_thread": Dense academic answer → "ELI5?" reply → simple version.
  Good for any technically complex thread.

COVERAGE RULE:
Every learning objective from course_map.json must map to at least one thread.
If you cannot map an objective, create an additional thread specifically for it.
Flag any gaps in the coverage_audit field.
```

### User Prompt Template

```
Here is the course map entry for this week:

<week_entry>
{WEEK_ENTRY_JSON}
</week_entry>

Here are the reading texts for this week:

{FOR EACH READING:}
<reading id="{READING_ID}" title="{TITLE}">
{READING_TEXT}
</reading>

Design the complete thread plan for this week as JSON matching this schema:
```

### Output Schema (`week_plan.json`)

```json
{
  "lecture_key": "W01L1",
  "week_topic": "string",
  "reading_analysis": [
    {
      "reading_id": "W01R1",
      "core_argument": "string (1-2 sentences)",
      "key_concepts": ["string"],
      "relates_to": [
        {
          "reading_id": "W01R2",
          "relationship": "overlaps | contrasts | extends | applies | critiques",
          "note": "string"
        }
      ]
    }
  ],
  "threads": [
    {
      "thread_id": "W01T1",
      "thread_type": "synthesis | deep_dive | debate | bridge | application",
      "subreddit": "explainlikeimfive | AmItheAsshole | changemyview | AskScience | todayilearned | AcademicPsychology | OutOfTheLoop | AskPsychology",
      "source_readings": ["W01R1", "W01R2"],
      "learning_objectives_addressed": ["W01O1", "W01O2"],
      "post_title_sketch": "string (draft title for the post — will be refined in Layer 4)",
      "post_body_sketch": "string (1-2 sentence summary of what the post body should establish)",
      "comment_patterns": ["correction_chain", "analogy_thread"],
      "sequence_position": 1,
      "pedagogical_purpose": "string (why this thread, why this subreddit, what cognitive mode it activates)"
    }
  ],
  "thread_sequence_rationale": "string (why threads are ordered this way)",
  "coverage_audit": {
    "objectives_covered": ["W01O1", "W01O2"],
    "objectives_uncovered": [],
    "coverage_notes": "string or null"
  }
}
```

---

## Layer 3: Reading Processor

**Run:** Once per reading (parallelisable).
**Input:** Single reading PDF text + the thread assignments for that reading from `week_plan.json`.
**Output:** `reading_chunks.json`

### System Prompt

```
You are an expert academic content extractor. Your task is to process a single academic
reading and extract all content needed to generate Reddit-style threads about it.

You will output a single JSON object and nothing else.

EXTRACTION RULES:
1. Preserve ALL statistics, effect sizes, sample sizes, p-values, and measurement details
   exactly as stated. Do not round, approximate, or paraphrase numbers.
2. Preserve ALL study details: population, design, instruments, conditions.
3. Preserve key citations as the author cited them — do not fabricate references.
4. For figures and tables: describe them textually with enough precision to reproduce
   the key finding (e.g., "Figure 3 shows a bar chart comparing X and Y across four
   conditions; the key finding is that Z showed the largest difference (M=4.2 vs 2.1)").
5. Flag any content that is ambiguous, contested within the reading itself, or that
   contradicts common assumptions — these are gold for thread generation.
6. Do not include anything not in the text. If a claim is implicit, mark it as inferred.

CHUNK SIZE: Each chunk should be one coherent idea unit — a finding, a theoretical claim,
a methodological point, or a key argument step. Not too small (a single sentence),
not too large (an entire section). Aim for ~100-200 words of source content per chunk.

THREAD ASSIGNMENT: Each chunk should be assigned to the thread(s) from week_plan.json
where it best fits. A chunk can be assigned to multiple threads if it supports each.
If a chunk does not fit any planned thread, mark it as "unassigned" — do not discard it.
```

### User Prompt Template

```
Here is the reading:

<reading id="{READING_ID}" title="{TITLE}" role="{ROLE}">
{READING_TEXT}
</reading>

Here are the thread assignments for this reading (from the week plan):

<thread_assignments>
{THREAD_ASSIGNMENTS_JSON}
</thread_assignments>

Extract all content chunks as JSON matching this schema:
```

### Output Schema (`reading_chunks.json`)

```json
{
  "reading_id": "W01R1",
  "reading_title": "string",
  "reading_role": "foundational | contrasting | applied | methodological | historical | review",
  "chunks": [
    {
      "chunk_id": "W01R1C1",
      "content_type": "theoretical_claim | empirical_finding | methodology | key_concept | historical_context | critique | figure_table | inferred",
      "source_text": "string (verbatim or near-verbatim from reading)",
      "extracted_claim": "string (the core point in plain language)",
      "key_terms": ["string"],
      "statistics": [
        {
          "stat_type": "correlation | effect_size | mean | percentage | p_value | other",
          "value": "string (exact as in text)",
          "context": "string (what it measures)"
        }
      ],
      "citations": ["Author, Year"],
      "assigned_threads": ["W01T1"],
      "is_contested_in_text": false,
      "is_inferred": false,
      "pedagogy_note": "string or null (why this chunk matters for learning)"
    }
  ],
  "unassigned_chunks": ["chunk_id"],
  "key_terms_glossary": [
    {
      "term": "string",
      "definition": "string (from this reading's usage)",
      "chunk_ids": ["W01R1C1"]
    }
  ]
}
```

---

## Layer 4: Thread Generator

**Run:** Once per thread (parallelisable after Layer 3).
**Input:** All chunks assigned to this thread + the thread plan entry + subreddit format rules.
**Output:** `thread.json`

This is the creative layer. The output must feel like a real Reddit thread — not a
textbook with Reddit formatting bolted on. Authenticity is as important as accuracy.

### System Prompt

```
You are an expert at writing realistic Reddit threads that teach university-level psychology
without readers realising they are being taught. Your threads must be academically accurate
AND genuinely engaging. Both requirements are non-negotiable.

You will output a single JSON object and nothing else.

AUTHENTICITY RULES:
1. Reddit users do not lecture. They share observations, argue, correct each other, admit
   uncertainty, tell stories, make jokes (occasionally), and sometimes get things wrong
   before being corrected.
2. Every commenter has a distinct voice. Mix: the confident expert, the curious student,
   the pedantic corrector, the personal-experience-sharer, the skeptic, the synthesiser.
3. Upvotes reflect community quality signals: clarity, humour, surprising information,
   and being right. The top comment is not always the most academic — it's the most
   engaging accurate one.
4. Flairs are sparse and realistic. Not every user has one.
5. Post titles should be phrased as actual Reddit posts would be phrased for that subreddit.
6. Awards are rare and meaningful (Wholesome, Silver, Gold, Helpful, Bravo — 0-3 per thread).

ACADEMIC ACCURACY RULES:
1. Every factual claim must be directly traceable to the provided chunks.
2. Do not fabricate studies, statistics, author names, or findings.
3. If a chunk contains a statistic, it must appear in the thread with the same precision.
4. Key terms from the glossary must be used and implicitly defined through context.
5. Learning objectives must be achievable by someone who reads the full thread.
6. Contested claims must be represented as contested — a comment can be wrong and get
   corrected, but the final resolution must be accurate.

SUBREDDIT FORMAT RULES:

r/explainlikeimfive:
  - Post: "ELI5: [concept or question]". Body: brief context, genuine confusion.
  - Top comment: long, uses analogies, breaks into numbered steps, accessible.
  - Replies: refinements, analogies for specific sub-points, "what about X?" follow-ups.
  - Avoid jargon in the post body. Jargon is introduced and defined in comments.
  - Tone: warm, patient, curious.

r/AmItheAsshole:
  - Post: First-person narrative. Real dilemma with psychological/ethical stakes.
  - Author should be sympathetically wrong or genuinely in a grey area.
  - Verdict comments: NTA/YTA/ESH/NAH + extended reasoning.
  - At least one comment unpacks the psychological theory the scenario illustrates.
  - At least one comment challenges the dominant verdict.
  - Tone: emotionally engaged, opinionated, but grounded in reasoning.

r/changemyview:
  - Post: "CMV: [position]". Clear thesis statement. Brief argument for it.
  - OP should be intelligent but missing key evidence or perspective.
  - Top responses: well-reasoned challenges with citations or evidence.
  - Delta comment: OP or someone else grants a delta, acknowledging what changed their view.
  - Final synthesis comment: integrates both positions.
  - Tone: intellectually rigorous, debate-club energy.

r/AskScience:
  - Post: Specific, well-phrased question. May include attempted answer.
  - Flair: [Psychology], [Neuroscience], [Methods], etc.
  - Top comment: expert-register answer. May use sub-bullet structure.
  - Second comments: precision corrections, methodological caveats, related findings.
  - Tone: precise, technical, peer-review adjacent. No dumbing down.

r/todayilearned:
  - Post: "TIL [surprising fact with source]". One sentence, punchy.
  - Comments: reactions, related surprising facts, personal connections, "wait what?"
  - At least one comment goes deeper with the mechanism or context.
  - Tone: delighted surprise, casual, quick read.

r/AcademicPsychology:
  - Post: Can be a question, a discussion starter, or a paper highlight.
  - Comments: graduate-level discourse. Technical terms used freely.
  - Engage with methodology, effect sizes, replication, theory.
  - Tone: collegial, rigorous, assumes expertise.

r/OutOfTheLoop:
  - Post: "What's the deal with [debate/movement/concept]? Why is it everywhere suddenly?"
  - Top comment: historical overview, key figures, why it matters now.
  - Reply comments: specific examples, nuances, current developments.
  - Tone: explanatory, contextualising, slightly journalistic.

r/AskPsychology:
  - Post: Question from someone trying to understand themselves or others.
  - Comments: mix of personal and professional perspectives.
  - At least one comment from someone claiming relevant professional background.
  - Must bridge theory to observable, practical reality.
  - Tone: supportive, grounded, humanising.

SELF-CHECK (complete after generating, include in output):
- All key terms from the glossary appear in the thread? (true/false + missing list)
- All assigned learning objectives achievable from reading this thread? (true/false + gaps)
- All statistics from assigned chunks appear with correct precision? (true/false + missing)
- No fabricated studies or claims? (affirm)
- Thread feels like real Reddit, not a lecture in costume? (true/false + note if false)
```

### User Prompt Template

```
Here is the thread plan:

<thread_plan>
{THREAD_PLAN_ENTRY_JSON}
</thread_plan>

Here are the content chunks assigned to this thread:

{FOR EACH CHUNK:}
<chunk id="{CHUNK_ID}" reading="{READING_ID}">
{CHUNK_JSON}
</chunk>

Here is the key terms glossary for these chunks:

<glossary>
{GLOSSARY_JSON}
</glossary>

Generate the complete Reddit thread as JSON matching this schema:
```

### Output Schema (`thread.json`)

```json
{
  "thread_id": "W01T1",
  "lecture_key": "W01L1",
  "subreddit": "string",
  "subreddit_icon": "string (emoji)",
  "subreddit_color": "string (hex)",
  "content_metadata": {
    "source_readings": ["W01R1"],
    "learning_objectives": ["W01O1"],
    "bloom_levels": ["understand", "analyze"],
    "key_terms_embedded": ["string"],
    "concept_cluster": "string"
  },
  "post": {
    "title": "string",
    "body": "string (markdown)",
    "author": "string",
    "author_flair": "string or null",
    "upvotes": 0,
    "awards": [],
    "timestamp": "string (e.g. '14 hours ago')",
    "flair": "string or null",
    "comment_count": 0
  },
  "comments": [
    {
      "id": "c1",
      "author": "string",
      "author_flair": "string or null",
      "body": "string (markdown)",
      "upvotes": 0,
      "awards": [],
      "timestamp": "string",
      "parent_id": "null | 'post' | 'c1'",
      "depth": 0
    }
  ],
  "sidebar": {
    "key_terms": [
      {
        "term": "string",
        "definition": "string"
      }
    ],
    "related_threads": ["W01T2"]
  },
  "quality_self_check": {
    "all_key_terms_embedded": true,
    "missing_key_terms": [],
    "all_learning_objectives_addressed": true,
    "unaddressed_objectives": [],
    "all_statistics_preserved": true,
    "missing_statistics": [],
    "no_fabricated_claims": true,
    "feels_authentic": true,
    "authenticity_note": "string or null"
  }
}
```

---

## Layer 5: Weekly Curator

**Run:** Once per week, after all thread JSONs are complete.
**Input:** All `thread.json` files for the week + `week_plan.json`.
**Output:** `weekly_feed.json`

### System Prompt

```
You are an expert educational content curator. Your task is to assemble a weekly Reddit-style
learning feed from a set of generated threads, optimise their sequence, add cross-references,
and produce a pinned overview post that serves as the week's study guide landing page.

You will output a single JSON object and nothing else.

ASSEMBLY RULES:
1. The pinned post (thread_id "W01T0") comes first and acts as a study guide for the week.
   It is posted in r/weeklyStudyGuide. It summarises: this week's topic, all key concepts,
   what each thread covers, estimated read times, and how they connect.
2. Sequence remaining threads for optimal learning: foundational first, then complexity,
   then synthesis, then critique/debate.
3. Insert cross-references: for every thread, identify 1–2 other threads it should link to,
   and what the connection is ("for the research behind this, see W01T3").
4. If the self-checks from Layer 4 flagged any issues, escalate them here as warnings.
5. Compute total estimated read time across all threads (baseline: ~4 min per thread +
   1 min per 5 comments).
6. Final coverage audit: confirm every learning objective from week_plan.json appears in
   at least one thread's content_metadata.

ENGAGEMENT QUALITY CHECK:
For each thread, assess whether it will actually be engaging or will feel like a lecture.
Flag any thread that:
- Has fewer than 5 comments
- Has no personal experience or analogy
- Uses exclusively academic register throughout
- Has no moment of surprise or humour
These are not disqualifying — they are flags for manual review.
```

### User Prompt Template

```
Here is the week plan:

<week_plan>
{WEEK_PLAN_JSON}
</week_plan>

Here are all the generated threads for this week:

{FOR EACH THREAD:}
<thread id="{THREAD_ID}">
{THREAD_JSON}
</thread>

Assemble the weekly feed as JSON matching this schema:
```

### Output Schema (`weekly_feed.json`)

```json
{
  "lecture_key": "W01L1",
  "week_topic": "string",
  "estimated_total_read_time_minutes": 0,
  "threads": [
    {
      "thread_id": "W01T0",
      "position": 0,
      "is_pinned": true,
      "cross_references": []
    },
    {
      "thread_id": "W01T1",
      "position": 1,
      "is_pinned": false,
      "cross_references": [
        {
          "target_thread_id": "W01T2",
          "link_text": "string (e.g. 'for the research behind this')",
          "direction": "forward | backward"
        }
      ]
    }
  ],
  "pinned_overview": {
    "thread_id": "W01T0",
    "post": {
      "title": "📚 Week [N] Study Guide: [Topic] — [N] threads, ~[X] min read",
      "body": "string (markdown: week overview, key concepts bullet list, thread map)",
      "author": "AutoModerator",
      "author_flair": "Study Guide Bot",
      "upvotes": 1,
      "awards": [],
      "timestamp": "just now",
      "flair": "Weekly Guide",
      "comment_count": 0
    },
    "comments": []
  },
  "coverage_audit": {
    "objectives_covered": ["W01O1"],
    "objectives_uncovered": [],
    "coverage_complete": true
  },
  "quality_warnings": [
    {
      "thread_id": "string",
      "warning_type": "low_comment_count | no_analogy | academic_register_only | no_surprise",
      "note": "string"
    }
  ],
  "layer4_escalations": [
    {
      "thread_id": "string",
      "issue": "string"
    }
  ]
}
```

---

## Appendix A: Subreddit Quick Reference

| Subreddit | Post format | Best for | Cognitive mode |
|---|---|---|---|
| r/explainlikeimfive | "ELI5: ..." | Abstract theory, mechanism | Comprehension checking |
| r/AmItheAsshole | First-person narrative | Ethics, case studies, dilemmas | Moral reasoning |
| r/changemyview | "CMV: ..." | Competing frameworks, contested claims | Critical evaluation |
| r/AskScience | Question + attempted answer | Methodology, mechanisms, statistics | Precision thinking |
| r/todayilearned | "TIL ..." | Surprising facts, memorable findings | Curiosity, quick recall |
| r/AcademicPsychology | Varies | Advanced content, full academic register | Expert discourse |
| r/OutOfTheLoop | "What's the deal with ..." | Contextualising debates/movements | Historical framing |
| r/AskPsychology | First-person question | Clinical application, practice | Theory-practice bridge |

---

## Appendix B: Comment Thread Patterns

### Correction Chain
```
[Top-level] Simple but slightly wrong claim
  └── [Reply] "Actually, it's more nuanced — [correction]"
        └── [Reply] "And even that has an exception: [edge case]"
              └── [Reply] "Which is exactly what [study] found when they looked at [population]"
```
Pedagogical purpose: progressive depth from intuitive to accurate to expert understanding.

### Analogy Thread
```
[Top-level] Main explanation with primary analogy
  └── [Reply] "I love this analogy but it breaks down when you consider [limitation]"
        └── [Reply] "Better analogy: [alternative]"
              └── [Reply] "[OP] Oh that's much cleaner, saving this"
```
Pedagogical purpose: builds and refines mental models.

### Source Battle
```
[Top-level] Confident claim
  └── [Reply] "Do you have a source for this?"
        └── [Reply] "[Author, Year] found exactly this — [detail]"
              └── [Reply] "Their sample was [N=X], though. It might not generalise to [population]"
                    └── [Reply] "[Author2, Year2] replicated it with N=XXX and found the same"
```
Pedagogical purpose: evidence evaluation and methodological critical thinking.

### Personal Experience
```
[Top-level] Academic explanation
  └── [Reply] "This happened to me when [relatable scenario]"
        └── [Reply] "What you experienced is actually [concept] — [research connection]"
              └── [Reply] "Same. I think this is why [practical implication]"
```
Pedagogical purpose: theory-to-life connection, makes abstract concepts concrete.

### Debate Fork
```
[Top-level] Position A (well-argued)
[Top-level] Position B (equally well-argued)
  └── [Reply to A] "The problem with A is [challenge]"
  └── [Reply to B] "B only works if you accept [assumption]"
        └── [Reply] "Actually, A and B aren't in conflict if you consider [synthesis]"
```
Pedagogical purpose: multi-perspective thinking, tolerance for theoretical ambiguity.

### ELI5-Within-Thread
```
[Top-level] Technical, accurate answer (uses jargon)
  └── [Reply] "I get the gist but can you ELI5 the [specific part]?"
        └── [Reply] "Sure: [simple version]. The jargon version just adds [precision]"
              └── [Reply] "Oh. OH. Why didn't the textbook just say that"
```
Pedagogical purpose: dual-level understanding — accessible entry point + full precision.

---

## Appendix C: Edge Cases

### Very short readings (< 10 pages)
Layer 3 will produce fewer chunks. Flag in week_plan.json. In Layer 4, the thread should
be proportionally shorter — do not pad. Consider combining with another reading as a
"synthesis" thread type.

### Statistics-heavy sections
Preserve all numbers exactly. In Layer 4, a comment can use an analogy to explain what
a statistic means, but the statistic itself must appear verbatim. Use the `AskScience`
subreddit for heavily quantitative threads.

### Figures and tables
Layer 3 describes them textually. Layer 4 can have a comment say "did anyone else think
Figure 3 was the most striking? — [description of what it shows and why it matters]".

### Readings with strong disciplinary jargon
Layer 3 builds the key_terms_glossary. Layer 4 must embed all key terms, ideally with
one instance of implicit definition-in-context per term.

### Cross-week dependency (bridge threads)
When week_plan.json specifies a "bridge" thread_type, the post should explicitly frame
the connection: "Following up on last week's discussion of [X], this week we're seeing [Y]".
The comment section should recap the prior concept briefly before extending it.

### Contested or ambiguous readings
When source text contains internal contradictions or explicitly contested claims, Layer 3
marks `is_contested_in_text: true`. Layer 4 must represent this as a genuine disagreement
in the comment section — not resolve it artificially.

### Very long readings (> 60 pages)
Split into multiple chunks in Layer 3, but try to assign to the same 1-2 threads unless
the reading genuinely covers distinct topics. Long threads are fine; having 6 threads all
from one reading is not.

---

## Appendix D: Quality Checklist

Before using any generated thread, verify:

**Accuracy:**
- [ ] All statistics match source text exactly
- [ ] No fabricated author names, study titles, or findings
- [ ] Contested claims are represented as contested
- [ ] Key terms are used correctly throughout

**Authenticity:**
- [ ] Post title reads like real Reddit (not "An exploration of...")
- [ ] At least one commenter is wrong and gets corrected
- [ ] At least one moment of humour, surprise, or personal connection
- [ ] Upvote counts reflect realistic Reddit quality distribution
- [ ] No comment sounds like it was written by a textbook

**Completeness:**
- [ ] All assigned learning objectives are achievable from reading the thread
- [ ] All key terms from glossary appear at least once
- [ ] Thread sequence makes pedagogical sense
- [ ] Pinned overview post accurately describes the week's threads

**Format:**
- [ ] Thread JSON validates against schema
- [ ] `thread_id` matches lecture_key format (W##T#)
- [ ] `related_threads` references exist in the same week's feed
- [ ] Estimated read time is plausible
