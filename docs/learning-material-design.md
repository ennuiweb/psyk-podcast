# Learning Material Design

This document captures repo-level design principles for learner-facing study
materials.

Use it for:

- learner-fit assumptions that should influence podcasts, printouts, and other
  future study materials
- reward-loop design principles for attention-limited learners
- a shared language for problem-first learning material design

This document is intentionally broader than any one show-specific scaffold
contract. It does not define source-of-truth paths or publication mechanics.

## Core Distinction

Learner-facing output quality is not the same as:

- preprocessing quality
- prompt assembly quality
- queue/publication correctness
- feed/runtime correctness

Those layers matter, but they should not be confused with whether a learner can
actually start, stay with, and benefit from the material.

## Problem-First Hypothesis

Some learners do not engage reliably with material that asks them to first
absorb information and only later receive a payoff.

For those learners, the material should not mainly ask them to:

- read first
- remember first
- summarize later

It should ask them to:

- solve something
- find something
- decide something
- prove something
- get visible closure quickly

This is not fake gamification. The point is to turn the material into a series
of real intellectual problems with short feedback loops.

## Reward Loops

The design target is immediate and repeated cognitive reward:

- `entry hook`: a task or tension the learner can start within 10 seconds
- `micro-reward loop`: a closure event every 1-3 minutes
- `resolution payoff`: a stronger "now I get it" or "I nailed it" moment

A useful default sequence is:

1. `search`
2. `model`
3. `challenge`

In practice:

- first the learner finds a distinction, quote, example, or contradiction
- then the learner builds the model that makes the finding make sense
- then the learner uses that model to answer a harder question correctly

## Design Principles

Prioritize:

- question tension over passive exposition
- visible progress over diffuse coverage
- short proof tasks over long open-ended prompts
- decisions under uncertainty over broad descriptive reading
- source-grounded wins over vague motivation language

Avoid:

- long warm-up before the first concrete task
- passive "here is the theory" framing when a conflict can start the section
- giant reading blocks without stop points
- broad prompts that require the learner to hold too much in working memory
- decorative gamification without real cognitive payoff

## Common Task Shapes

High-fit task patterns include:

- find the pivot
- choose between two models
- catch the author's main attack
- locate the sentence that proves the claim
- identify the trap or likely misunderstanding
- explain why one explanation fails and another survives
- solve one decisive "boss-fight" question after several smaller wins

Low-fit task patterns include:

- read this whole section and reflect
- summarize the author's argument in your own words before any smaller closure
- discuss the text broadly without a decision target

## Format Guidance

### Printouts

Printouts should feel like mission sheets, not static summaries.

Good shape:

- mission brief
- evidence hunt
- decision points
- model reconstruction
- one harder final challenge

### Podcasts

Podcasts should not rely only on strong explanation quality. For some learners,
they work better when each episode behaves like a guided investigation.

Good shape:

- open with a sharp problem or conflict
- present competing interpretations
- resolve the conflict with source-grounded reasoning
- repeat in short loops
- end with one decisive conceptual takeaway

### Quizzes And Future Formats

Future study materials should inherit the same principle:

- do not ask for delayed payoff when a near-term closure can be designed

## Evaluation Questions

When testing a learner-facing output, ask:

- does the learner know what problem they are solving almost immediately?
- is there a visible reward within the first minute or two?
- do the tasks reduce working-memory load or increase it?
- does the material create real closure events, or only more input?
- does the learner leave with a model they can use, not only facts they heard?

Useful practical metrics:

- start speed
- time to first completion signal
- sustained engagement
- immediate recall after use
- whether the learner reports intrinsic reward rather than mere duty

## Related Docs

- [notebooklm-automation.md](/Users/oskar/repo/podcasts/docs/notebooklm-automation.md)
- [learning-material-outputs.md](/Users/oskar/repo/podcasts/shows/personlighedspsykologi-en/docs/learning-material-outputs.md)
- [problem-driven-scaffolding.md](/Users/oskar/repo/podcasts/shows/personlighedspsykologi-en/docs/problem-driven-scaffolding.md)
