# RedditStudy: Design Reference

This document captures the reasoning behind the design decisions in `content-pipeline.md`.
It is not required to run the pipeline — it is here to explain the "why" behind choices
so future iterations can adapt intelligently rather than just following rules blindly.

---

## The Core Insight

Oskar (and many others with ADHD) can consume Reddit threads at high speed and high
retention — the same material that would take 45 minutes to read as an academic text
takes 10 minutes to read as a Reddit thread, with comparable or better comprehension.

This is not a dumbing-down. It is a format match. Reddit's structure maps well to how
ADHD attention actually works:

- **Short chunks** with visible endpoints eliminate the "how much is left?" anxiety
- **Social framing** (who said this, how many people agreed) engages the social cognition
  system rather than demanding pure abstract processing
- **Nested hierarchy** lets you skip depth you don't need without losing the thread
- **Argumentative tone** activates engagement circuitry — you read to agree or disagree,
  not just to receive
- **Variable reward** — some comments are throwaway, some are gold — keeps the feed active

The constraint: Reddit's format is also easy to get wrong. "Psychology facts but with
usernames" is not the goal. The goal is content that feels like a real community of people
who are fascinated by this topic.

---

## Subreddit Type Design Decisions

### Why r/AmItheAsshole for ethics content?

AITA has the highest "I can't stop reading" coefficient of any subreddit format. The format
forces the content to be human-centred: someone made a choice, there are stakes, we are
asked to judge. For research ethics (e.g. Milgram, Tuskegee), clinical dilemmas, or
contested therapeutic practices, this framing forces the reader to *take a position before
they know the theory* — which turns subsequent learning into "was I right?"

The AITA format also naturally generates the Correction Chain and Debate Fork patterns
because commenters genuinely disagree, not just academically.

### Why r/changemyview for competing frameworks?

CMV requires the poster to have a position and defend it. This makes the content structure
naturally adversarial in a productive way. For psychology — where every theory has a rival
(trait vs. situationist, psychodynamic vs. cognitive, nomothetic vs. idiographic) — CMV
threads let the debate happen without either side being artificially presented as "correct".

The delta system (OP granting a delta when their view changes) is pedagogically important:
it models intellectual humility and shows what it looks like to update beliefs on evidence.

### Why r/OutOfTheLoop for paradigm shifts?

"What's the deal with X?" is the best framing for intellectual history. It positions the
reader as an intelligent outsider catching up, rather than a student being lectured. The
question "why are people arguing about X?" is more engaging than "here is the history of X"
because it implies there are currently two sides, and that catching up is worth something.

---

## Comment Thread Pattern Design

The six patterns are designed to map to different kinds of learning difficulty:

| Pattern | The learning problem it solves |
|---|---|
| Correction Chain | "I thought I understood but I had it slightly wrong" |
| Analogy Thread | "I understand the words but not the concept" |
| Source Battle | "How do we actually know this?" |
| Personal Experience | "Why does this matter in real life?" |
| Debate Fork | "Which theory is right?" (answer: it depends) |
| ELI5-Within-Thread | "The top comment lost me at word 3" |

Every thread should contain at least two patterns. Using all six in one thread is too
crowded — it will feel like a worksheet.

---

## What Makes a Thread Feel Authentic

The hardest problem in this pipeline is authenticity. Here are the failure modes and fixes:

### Failure mode 1: The Expert Monologue
All comments are long, accurate, and impersonal. Nobody is wrong. Nobody is surprised.
The thread reads like a textbook with `u/` prefixes.

Fix: Add at least one commenter who is confidently wrong about something minor and gets
corrected. Add at least one "wait, seriously?" or "TIL" moment even in a long thread.
Add at least one person who relates it to their life or job.

### Failure mode 2: The Terminology Dump
The thread uses all the right terms but never makes you feel like you *get* it. Every
comment assumes the reader already understands the concept.

Fix: Use the Analogy Thread and ELI5-Within-Thread patterns. At least one comment should
restate the core concept in a single accessible sentence, even if the surrounding
discussion is technical.

### Failure mode 3: Perfect Agreement
Every comment is a variation of "great point, I'd add..." No one disagrees, challenges,
or offers a competing interpretation.

Fix: The Debate Fork and Source Battle patterns exist for this. Also: in real Reddit,
people sometimes just say "I don't buy this" and the thread responds. It's fine to have
a dissenting comment that doesn't get resolved.

### Failure mode 4: Implausible Upvotes
The most technical, jargon-dense comment has the most upvotes. The funny comment has 3.

Fix: The most-upvoted comment should be the most accessible accurate one. High-quality
analogies and "wait, I think I finally understand this" moments get Reddit gold in real
life. Technical precision with no accessibility gets appreciation from experts but
doesn't dominate.

---

## Subreddit Variety Strategy

A week's feed should feel like a diverse browsing session, not a single subreddit. Aim for:
- No more than 2 threads in the same subreddit per week
- At least one "high engagement" format (AITA or CMV) per week
- At least one "clarity" format (ELI5 or OutOfTheLoop) per week
- At least one "precision" format (AskScience or AcademicPsychology) if the week has
  methodological or empirical content

This variety ensures the student cycles through different cognitive modes across the week's
threads, rather than staying in one register.

---

## Key Terms Sidebar Design

The sidebar key terms panel (in the renderer) serves as a portable glossary for each
thread. Design rules:

1. Terms should appear in order of first use in the thread — not alphabetically
2. Definitions should be in plain English, not the textbook definition
3. Maximum 8 terms per thread — more is overwhelming
4. A term that appears in multiple threads should have a consistent definition

---

## On Accuracy vs. Engagement Trade-offs

The pipeline must not sacrifice accuracy for engagement. If a concept is genuinely hard
to explain simply, the thread should be genuinely hard. The ELI5-Within-Thread pattern
exists for this: give readers the simple version *and* the accurate version, in the same
comment chain. They can read to their level.

What the pipeline must not do:
- Simplify a contested finding into a settled one
- Attribute a specific claim to a specific study when the source material only says
  "research suggests"
- Omit effect sizes or sample sizes because they make the writing less punchy
- Resolve a theoretical debate that is genuinely unresolved

The self-check in Layer 4 and the coverage audit in Layer 5 are the enforcement mechanisms.
If either flags an issue, the thread must be regenerated or manually corrected before
being served through the portal.

---

## Integration with Existing Pipeline

This system sits alongside the existing NotebookLM podcast pipeline, not instead of it.
The two modalities serve different needs:

| Podcast (NotebookLM) | Reddit threads (this pipeline) |
|---|---|
| Passive consumption (commute, workout) | Active engagement (study session) |
| Linear narrative | Non-linear, skimmable |
| Audio learners | Visual/text learners |
| ~20-30 min per episode | ~5-15 min per thread feed |
| Pre-generated, download to device | Served via freudd portal |

The content manifest for each lecture week will gain a `reddit_threads` asset entry
alongside existing `quizzes`, `podcasts`, and `slides` entries.
