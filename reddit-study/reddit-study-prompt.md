# RedditStudy — Design Reference

> **Status:** Superseded by `content-pipeline.md` as the authoritative implementation guide.
> This document captures early design thinking and is useful as reference for the subreddit taxonomy,
> comment patterns, and meta-feature decisions that feed the pipeline.

---

## The Core Problem

Academic texts are written for people who already want to read them. The structure assumes motivation.
ADHD breaks that assumption — not because of capability, but because of attentional activation.

Reddit threads are structurally different in ways that matter for attention:
- Information arrives in small, self-contained chunks
- Social framing (someone asked, someone answered) creates narrative pull
- Visual hierarchy (upvotes, nesting, flairs) signals what matters without front-loading
- Comment threads are scannable — you can drop in anywhere, get value, and re-engage
- Disagreement and personality make content feel alive

The hypothesis: the same psychological concepts are learnable in both formats. The Reddit format
activates a different attentional mode — one that works with ADHD rather than against it.

RedditStudy converts university psychology readings into Reddit threads that preserve academic
precision while using Reddit's structural affordances to make content accessible.

---

## Subreddit Taxonomy

Each subreddit is not just a format — it's a cognitive activation mode.

### r/explainlikeimfive
**When:** Dense theory, abstract constructs, unfamiliar terminology
**Cognitive mode:** "Do I actually understand this or am I just pattern-matching words?"
**Key features:**
- Top comment must be genuinely simple — no jargon without immediate gloss
- Nested replies progressively add complexity
- "Okay but what about..." follow-ups naturally extend the topic
- The ELI5 constraint forces the generator to locate the core intuition in a concept

**Example use:** Explaining factor analysis, the unconscious, Bayesian inference

### r/AmItheAsshole
**When:** Ethics cases, clinical dilemmas, research ethics, dual-role situations
**Cognitive mode:** Moral reasoning, judgment, high emotional engagement
**Key features:**
- OP describes a situation with ethical ambiguity
- Commenters argue for different verdicts (YTA / NTA / ESH / NAH)
- "INFO" requests simulate asking clarifying questions
- Flair voting creates a visible consensus or split
- Works best when there's genuine tension, not a clear right answer

**Example use:** Research ethics (Milgram-style designs), clinical dual-roles,
diagnostic labeling dilemmas, therapeutic neutrality vs. advocacy

### r/changemyview
**When:** Competing theories, contested claims, paradigm disputes
**Cognitive mode:** Evaluation, argument analysis, "what would it take to convince me?"
**Key features:**
- OP states a view (often a theory or framework) as a position to defend
- Challengers present counterarguments with evidence
- Delta system: OP awards deltas when they're actually convinced
- Forces engagement with the strongest version of opposing views
- Models good epistemic practices (updating on evidence)

**Example use:** Trait theory vs. situationism, validity of projective tests,
nature vs. nurture in personality, categorical vs. dimensional diagnosis

### r/AskScience
**When:** Mechanism questions, methodology, measurement, empirical precision
**Cognitive mode:** Expertise and precision — this is where citations live
**Key features:**
- Answered by "verified" experts (flairs mark credentials)
- Peer-reviewed citations expected in top answers
- Corrections and qualifications are valued, not pedantic
- Good for "how exactly does X work" questions
- Distinguished from pop-science by insisting on specificity

**Example use:** How does HPA axis reactivity work in stress? What's the actual
evidence for Big Five cross-cultural validity? How is intelligence operationalized?

### r/todayilearned
**When:** Surprising findings, counterintuitive results, historical facts, notable studies
**Cognitive mode:** Curiosity, quick memorability, "wait, really?"
**Key features:**
- Single-sentence TIL statement as the post title
- Comments add context, related facts, or personal reactions
- Upvotes indicate how surprising/interesting something is
- Best for discrete, shareable facts rather than complex arguments

**Example use:** TIL that the five-factor model emerged from lexical analysis of dictionaries,
TIL Milgram's original obedience study had a 65% full-compliance rate

### r/AcademicPsychology
**When:** Advanced content that shouldn't be simplified, precise theoretical distinctions
**Cognitive mode:** Full academic register — graduate student mode
**Key features:**
- No ELI5 — assumes undergrad or above
- Citations in APA or similar
- Technical vocabulary used without apology
- Debate is substantive and precise
- Used when simplification would lose something important

**Example use:** Measurement invariance in cross-cultural studies, meta-analytic
methodology, construct validity arguments, specific statistical techniques

### r/OutOfTheLoop
**When:** Contextualizing debates, historical background, "why does this matter" framing
**Cognitive mode:** Historical/contextual — why is this a thing?
**Key features:**
- OP is genuinely confused about why something is happening
- Top answer explains the full context and stakes
- Useful for giving readings their intellectual context
- "What's the deal with X?" framing lowers the barrier to engagement

**Example use:** What's the deal with the replication crisis in psychology?
Why do therapists keep fighting about CBT vs. psychodynamic approaches?

### r/AskPsychology
**When:** Clinical application, therapy questions, bridging theory and practice
**Cognitive mode:** Applied and curious — "how does this actually work in real life?"
**Key features:**
- Questions from someone wanting to understand or apply psychology
- Answers bridge academic knowledge and practical reality
- Personal experience welcome but tempered with research
- Not therapy advice — theoretical/educational framing

**Example use:** How do therapists actually use attachment theory? What does
"good enough" parenting mean in practice? How do psychologists assess personality?

---

## Comment Thread Patterns

These patterns recur across subreddits and serve specific pedagogical functions.
Layer 4 selects and implements these based on the `week_plan.json` assignments.

### Correction Chain
```
Top comment: [Simple or incomplete claim]
  └─ Reply: "Actually, it's more nuanced — [adds depth or corrects]"
       └─ Reply: "And the exception to that is [edge case or counterexample]"
            └─ Reply: [Further nuance, or concedes the point]
```
**Purpose:** Progressive depth — draws readers deeper through the correction impulse

### Analogy Thread
```
Top comment: [Analogy to explain concept]
  └─ Reply: "That's a good analogy but it breaks down when [limitation]"
       └─ Reply: "Better analogy: [alternative mental model]"
            └─ Reply: "These together cover it well"
```
**Purpose:** Multiple mental models for the same concept — different analogies illuminate different facets

### Source Battle
```
Top comment: [Claim about research]
  └─ Reply: "Source?"
       └─ Reply: "[Citation, with brief summary of finding]"
            └─ Reply: "[Critique of methodology, or confirming meta-analysis]"
```
**Purpose:** Models evidence-evaluation practices — not all sources are equal

### Personal Experience
```
Top comment: [Research explanation]
  └─ Reply: "This matches my experience as [X] — [anecdote]"
       └─ Reply: "Research on this actually shows [connects anecdote to theory]"
```
**Purpose:** Concrete grounding for abstract concepts

### Debate Fork
```
Top comment: [Position A with reasoning]
Top comment 2: [Position B with reasoning]
  └─ Reply to both: "The synthesis here is [bridges A and B]"
```
**Purpose:** Multi-perspective exposure — both sides at depth before synthesis

### ELI5-Within-Thread
```
Top comment: [Dense technical answer]
  └─ Reply: "ELI5?"
       └─ Reply: "[Same information, genuinely simplified]"
            └─ Reply: "Perfect, thanks"
```
**Purpose:** Dual-level understanding — expert and novice registers for the same content

---

## Post Type System

Beyond subreddits, posts have types that determine their narrative structure:

| Post Type | Narrative Frame | Best For |
|---|---|---|
| Question | "Can someone explain X?" | Introductions to concepts |
| Confession | "I never understood X until..." | Relatable learning moments |
| Debate | "Controversial take: X is wrong" | Contested claims |
| Discovery | "TIL that X" | Memorable facts |
| Story | "This happened and I think it illustrates X" | Case studies, ethics |
| Meta | "Why does everyone always argue about X?" | Paradigm wars |
| Help | "Working on X, stuck on Y" | Applied problems |

---

## Authenticity Markers

What makes a Reddit thread feel real vs. "textbook in costume":

**Voice:**
- Contractions: "it's" not "it is", "doesn't" not "does not"
- Self-corrections mid-comment: "Wait — actually that's not quite right..."
- Hedging: "I might be misremembering but...", "someone correct me if wrong"
- Enthusiasm spills: "This is one of my favorite findings in the whole field"
- Personal positioning: "As someone who studied this..." or "Layperson here but..."

**Structure:**
- Short paragraphs — 2-4 sentences max before a line break
- Lists used naturally for multiple items, not for everything
- Bold used sparingly for one key term per comment, not headers
- Links appear as [study name] or [wiki] not as formal citations

**Social dynamics:**
- Someone always asks a dumb question, and someone always answers kindly
- There's usually at least one comment that slightly misses the point
- Top comments often get gilded/awarded for being genuinely excellent
- Late comments add information the top comments missed
- Someone connects it to current events or pop culture

**Timing:**
- Mix of timestamps: "14 hours ago", "2 days ago", "just now"
- Recent comments feel responsive to earlier ones

---

## Meta-Features

### Key Terms Sidebar
Every thread has a sidebar showing 3-8 key terms defined in context.
Terms are drawn from the actual thread content — not generic definitions.
Format: `term → definition as used in this specific discussion`

### Cross-Thread References
Threads link to related threads in the same week's feed, and to earlier weeks:
- "Related thread" links within the same week
- "Prerequisite" links back to foundational concepts from prior weeks
- "Going deeper" links to r/AcademicPsychology versions of the same topic

### Pinned Curator Post
Week 1 of every week's feed is a pinned post from `u/psyk_studiedbot` that:
- Summarizes what the week covers
- Lists the threads in recommended reading order
- Notes which threads are linked to which learning objectives
- Flags any "don't skip this" threads

### Read Time Estimates
Each thread shows an estimated read time based on word count.
Calibrated to comfortable Reddit reading pace (~200 wpm).
The week's total read time is shown in the curator post.

### Difficulty Indicators
Optional visual cue on each thread:
- 🟢 Core concept — essential
- 🟡 Builds on prior weeks
- 🔴 Advanced — read last, or after seeing the lecture

---

## Technical Notes (Early Design)

### Feed Format
The final output per week is a `weekly_feed.json` — an ordered array of threads.
The React renderer (`reddit-study.jsx`) consumes this format.
Each thread in the feed is a `thread.json` object (see Layer 4 schema).

### Subreddit Icons and Colors
Each subreddit has a consistent visual identity in the renderer:
- r/explainlikeimfive: 🧒 `#0079d3`
- r/AmItheAsshole: ⚖️ `#ff4500`
- r/changemyview: 🔄 `#46d160`
- r/AskScience: 🔬 `#5f99cf`
- r/todayilearned: 💡 `#ff6314`
- r/AcademicPsychology: 📚 `#7193ff`
- r/OutOfTheLoop: 🌀 `#ff585b`
- r/AskPsychology: 🧠 `#ea0027`

### Scoring and Completeness
Threads are scored at generation time (Layer 4 self-check) and at curation time (Layer 5 audit).
Dimensions: key term coverage, learning objective coverage, Bloom level distribution,
comment pattern diversity, estimated engagement quality.

The system is not perfect — human review of generated threads is part of the workflow.
The quality checks are guardrails, not guarantees.
