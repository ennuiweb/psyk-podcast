# RedditStudy — Project Handoff Document

## What Is This?

RedditStudy is a learning tool that converts university psychology course material into realistic Reddit-style threads. The user (Oskar) is a psychology undergraduate with ADHD who struggles to read academic texts but can consume Reddit threads rapidly. The core insight is that Reddit's format — short chunks, conversational tone, social framing, visual hierarchy — activates a different attentional mode that works with ADHD rather than against it.

This is not a toy. It's a serious study tool that needs to preserve academic precision while making the content genuinely engaging.

---

## Project Files

All files are in the `reddit-study/` directory:

| File | What It Is |
|---|---|
| `content-pipeline.md` | **The main deliverable.** Complete 5-layer prompt pipeline with system prompts, JSON schemas, user prompt templates, and appendices. This is the engine. |
| `reddit-study-prompt.md` | Earlier design doc — the initial exploration of subreddit types, post types, comment patterns, and meta-features. Superseded by `content-pipeline.md` but contains useful reference material and thinking. |
| `reddit-study.jsx` | React prototype of the Reddit thread renderer. Contains 3 hardcoded sample threads (r/AITA on research ethics, r/ELI5 on working memory, r/CMV on personality types) with full comment threading, collapsible comments, flairs, awards, upvotes, and a key terms sidebar. |

---

## Architecture: The 5-Layer Pipeline

```
Course Plan PDF ──┐
                  ├──▶ [Layer 1: Course Mapper] ──▶ course_map.json
Learning Goals PDF┘

All readings for Week N ──┐
course_map.json (week N) ─┤
                          ├──▶ [Layer 2: Week Planner] ──▶ week_plan.json
                          │
                          └──▶ [Layer 3: Reading Processor] ──▶ reading_chunks.json (per reading)

reading_chunks.json ──────┐
week_plan.json ───────────┤
                          └──▶ [Layer 4: Thread Generator] ──▶ thread.json (per chunk)

All thread.json for week ─┐
week_plan.json ───────────┤
                          └──▶ [Layer 5: Weekly Curator] ──▶ weekly_feed.json
```

### Layer 1: Course Mapper (run once per semester)
- **Input:** Course plan PDF + Learning goals PDF
- **Output:** `course_map.json`
- Maps weeks → topics → readings → learning objectives
- Classifies reading roles (foundational, contrasting, applied, etc.)
- Identifies dependency chains between weeks
- Uses Bloom's taxonomy to classify learning objective depth

### Layer 2: Week Planner (run once per week)
- **Input:** All reading PDFs for the week + relevant slice of `course_map.json`
- **Output:** `week_plan.json`
- This is the brain of the system — most important layer to get right
- Analyzes how readings relate: overlap, complementarity, tension, gaps
- Decides what threads to create, what subreddit each should use, what comment patterns to employ
- Routes content: synthesis threads (combine readings), debate threads (pit readings against each other), bridge threads (recap prerequisites)
- Sequences threads for optimal learning progression
- Performs learning objective coverage check — flags any objectives not addressed

### Layer 3: Reading Processor (run once per reading)
- **Input:** Single reading PDF + relevant thread assignments from `week_plan.json`
- **Output:** `reading_chunks.json`
- Chunks each reading into self-contained units mapped to specific threads
- Preserves all statistics, citations, key terms, study details
- Handles edge cases: figures/tables (described textually), stats-heavy sections, very short/long readings
- Flags unassigned content

### Layer 4: Thread Generator (run per thread)
- **Input:** All chunks for a thread + thread plan entry + subreddit format rules
- **Output:** `thread.json`
- The creative generation layer
- Produces complete Reddit threads with posts, nested comments, flairs, awards, upvotes
- Must feel authentic — like a real Reddit conversation, not a textbook in costume
- Includes a self-check: verifies all key terms embedded, all learning objectives addressed
- Contains detailed format rules for each subreddit (r/ELI5, r/AITA, r/CMV, r/AskScience, r/TIL, r/AcademicPsychology, r/OutOfTheLoop, r/AskPsychology)

### Layer 5: Weekly Curator (run once per week, after all threads)
- **Input:** All thread JSONs for the week + `week_plan.json`
- **Output:** `weekly_feed.json`
- Assembles the final feed with optimal sequencing
- Creates a pinned overview post (week landing page / study guide)
- Inserts cross-references between threads
- Performs final coverage audit against learning objectives
- Checks engagement quality and difficulty curve
- Estimates read times

---

## Subreddit System

Each subreddit activates a different reading/thinking mode:

| Subreddit | When to Use | Cognitive Mode |
|---|---|---|
| r/explainlikeimfive | Dense theory, abstract concepts | "Do I get this?" — comprehension checking |
| r/AmItheAsshole | Ethics, clinical dilemmas, case studies | Moral reasoning, judgment, high engagement |
| r/changemyview | Competing theories, contested claims | Evaluation, comparison, argument analysis |
| r/AskScience | Methodology, mechanisms, measurement | Precision, expertise, structured thinking |
| r/todayilearned | Surprising findings, historical facts | Quick memorability, curiosity |
| r/AcademicPsychology | Advanced/precise content | Full academic register, no simplification |
| r/OutOfTheLoop | Contextualizing debates/movements | Why something matters, historical framing |
| r/AskPsychology | Clinical application, therapy | Bridging theory and practice |

## Comment Thread Patterns

| Pattern | Structure | Pedagogical Purpose |
|---|---|---|
| Correction Chain | Simple → Nuanced → Exception | Progressive depth |
| Analogy Thread | Analogy → Limitation → Alternative | Multiple mental models |
| Source Battle | Claim → "Source?" → Citation → Critique | Evidence evaluation |
| Personal Experience | Anecdote → Research connection | Concrete examples |
| Debate Fork | Position A → Position B → Synthesis | Multi-perspective |
| ELI5-Within-Thread | Dense answer → "ELI5?" → Simple | Dual-level understanding |

---

## User Context

- Oskar has a course plan PDF listing all readings by week
- Oskar has a learning goals PDF for the semester
- These are the two inputs that bootstrap the entire system (Layer 1)
- He currently uses NotebookLM to convert readings to podcasts — this system adds another modality
- He's a software developer who can build the pipeline himself — he needs the prompts and architecture, not hand-holding on implementation
- The content is psychology coursework — concepts, theories, research methods, ethics, statistics

---

## Implementation Notes

### What Needs Building
1. **PDF text extraction** — readings come as PDFs, need clean text for the LLM prompts
2. **Pipeline orchestrator** — script that runs Layers 1-5 in sequence, passing outputs between layers
3. **LLM API calls** — each layer is a system prompt + user prompt sent to an LLM. All prompts request JSON output with no markdown fencing.
4. **Renderer** — the React app that displays the thread JSON. A working prototype exists in `reddit-study.jsx`.

### Technical Decisions Left Open
- Which LLM to use for each layer (Claude, GPT-4, etc.) — some layers need more creativity (Layer 4), others need more precision (Layer 3)
- Whether to run locally or as a web app
- How to handle PDF extraction (PyMuPDF, pdfplumber, etc.)
- Storage format for generated content
- Whether the renderer should be a standalone app or embedded somewhere

### Key Risks
- **Accuracy loss in conversion** — the biggest risk. The self-check in Layer 4 and the coverage audit in Layer 5 are the safety nets.
- **Hallucinated studies/statistics** — the prompts explicitly forbid this, but it needs testing
- **Threads that feel like "textbook in Reddit costume"** — authenticity is hard. The engagement check in Layer 5 flags this.
- **Content chunking failures** — some readings won't chunk cleanly. The edge case appendix in `content-pipeline.md` covers common scenarios.

---

## Sample Thread JSON Schema (Layer 4 Output)

```json
{
  "thread_id": "W1T1",
  "subreddit": "explainlikeimfive",
  "subreddit_icon": "🧒",
  "subreddit_description": "...",
  "subreddit_color": "#0079d3",
  "content_metadata": {
    "source_readings": ["W1R1"],
    "learning_objectives": ["LO3"],
    "bloom_levels": ["understand", "analyze"],
    "key_terms_embedded": ["classical conditioning", "extinction"],
    "concept_cluster": "Learning — Classical Conditioning"
  },
  "post": {
    "title": "ELI5: How does classical conditioning actually work?",
    "body": "...",
    "author": "curious_about_psych",
    "author_flair": null,
    "upvotes": 3847,
    "awards": [],
    "timestamp": "14 hours ago",
    "flair": "Biology/Psychology",
    "comment_count": 234
  },
  "comments": [
    {
      "id": "c1",
      "author": "neuro_nerd_42",
      "author_flair": "Behavioural Neuroscience MSc",
      "body": "...",
      "upvotes": 4521,
      "awards": ["best_explanation"],
      "timestamp": "13 hours ago",
      "parent_id": null,
      "depth": 0
    }
  ],
  "sidebar": {
    "key_terms": [{"term": "...", "definition": "..."}],
    "related_threads": ["W1T2"]
  },
  "quality_self_check": {
    "all_key_terms_embedded": true,
    "all_learning_objectives_addressed": true,
    "bloom_levels_achieved": ["understand", "analyze"],
    "comment_pattern_coverage": ["correction_chain", "analogy"],
    "potential_accuracy_concerns": []
  }
}
```

---

## What's Next

1. **Test Layer 1** with Oskar's actual course plan and learning goals PDFs — validate the mapping
2. **Test Layer 2** with one week's readings — see if the content planning logic holds
3. **Test Layer 4** on a single thread — evaluate engagement and accuracy
4. **Iterate prompts** based on real output quality
5. **Build the pipeline orchestrator**
6. **Polish the renderer** — currently hardcoded sample data, needs to consume thread JSON dynamically
