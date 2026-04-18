# Judge Prompt

Use this prompt when both transcripts are ready.

## Goal

Compare two matched transcripts for the same episode target.
Transcript A is the baseline. Transcript B is the candidate.
Do not assume B is better. Judge from the sources.

## Inputs

- episode type
- source material or trusted source excerpts
- transcript A
- transcript B
- optional resolved prompts

## Evaluation criteria

Score each criterion as:

- `A wins`
- `B wins`
- `Tie`

Criteria:

1. Conceptual distinctions
2. Argument structure or lecture logic
3. Source grounding and fidelity
4. Exam relevance
5. Non-generic explanation quality
6. Misunderstanding prevention

Additional episode-type criteria:

- `single_slide`: reconstruction of lecture sequence and where slides simplify
- `weekly_readings_only`: synthesis across sources and identification of tensions
- `short`: compression quality without becoming vague

## Output format

```md
# <sample_id>

## Verdict
- Overall winner: A | B | Tie
- Confidence: low | medium | high

## Criterion Scores
- Conceptual distinctions: ...
- Argument structure or lecture logic: ...
- Source grounding and fidelity: ...
- Exam relevance: ...
- Non-generic explanation quality: ...
- Misunderstanding prevention: ...

## Episode-Type Criteria
- ...

## Evidence
- Quote short transcript excerpts and tie them to concrete source points.

## Risks / Errors
- Note hallucinations, flattening, missed distinctions, or misleading framing.

## Recommendation
- Keep baseline
- Ship candidate
- Revise candidate and retest
```

## Important constraints

- Prefer precision over fluency.
- Penalize generic “podcast voice” if it reduces analytical usefulness.
- A shorter answer can still win if it preserves the key distinctions.
- If both are weak, say so explicitly.
