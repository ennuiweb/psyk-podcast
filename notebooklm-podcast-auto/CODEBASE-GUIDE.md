# NotebookLM Podcast Auto Codebase Guide
This guide is for coding LLMs working in `notebooklm-podcast-auto/`.
This branch is the NotebookLM-facing generation layer of the repo.
It contains both generic wrapper logic and highly course-specific automation.

## 1. Business purpose
The repo needs to turn curated reading bundles and prompt definitions into generated course audio and related artifacts.
`notebooklm-podcast-auto/` is the layer that actually talks to NotebookLM and drives those content-generation workflows.

It is not a clean SDK package.
It is a hybrid of:
- a vendored upstream client
- wrapper scripts
- course-specific generation forests

## 2. Directory structure
Important branches:
- `generate_podcast.py`
- `notebooklm-py/`
- `personlighedspsykologi/`
- `bioneuro/`
- `profiles/`
- `README.md`

What they do:
- `generate_podcast.py`: generic-ish CLI wrapper around `notebooklm-py`
- `notebooklm-py/`: vendored low-level NotebookLM client
- `personlighedspsykologi/`: course-specific scripts, prompts, outputs, evaluation lanes
- `bioneuro/`: another subject-specific branch
- `profiles/`: auth/profile material used by the wrapper layer

## 3. Read this subsystem in this order
1. `README.md`
2. `generate_podcast.py`
3. `personlighedspsykologi/scripts/generate_week.py`
4. `personlighedspsykologi/scripts/rollout_week.py`
5. only then dive into `notebooklm-py/` internals if needed

## 4. Generic wrapper entrypoint
Source: `notebooklm-podcast-auto/generate_podcast.py`

This file is the main generic operator wrapper.
It bootstraps the vendored NotebookLM client and manages profile selection, sources, retries, and artifact requests.

Snippet:
```python
# notebooklm-podcast-auto/generate_podcast.py
NOTEBOOKLM_SRC = Path(__file__).resolve().parent / "notebooklm-py" / "src"
if NOTEBOOKLM_SRC.is_dir() and str(NOTEBOOKLM_SRC) not in sys.path:
    sys.path.insert(0, str(NOTEBOOKLM_SRC))

from notebooklm import NotebookLMClient, RPCError
```

This is a strong signal:
- the wrapper is not packaged cleanly
- `sys.path` mutation is part of the runtime contract

Any refactor here must preserve importability for operator scripts.

## 5. Source parsing contract
`generate_podcast.py` accepts heterogeneous source references:
- `url:...`
- `file:...`
- `text:Title|Content`
- plain path if it exists
- otherwise plain URL

Snippet:
```python
# notebooklm-podcast-auto/generate_podcast.py
if text.startswith("url:"):
    return {"kind": "url", "value": text[4:].strip()}
if text.startswith("file:"):
    return {"kind": "file", "value": text[5:].strip()}
if text.startswith("text:"):
    ...
```

This matters because upstream callers can be surprisingly loose in how they specify sources.

## 6. Profile and rate-limit handling
This file also owns:
- profile selection
- profile cooldowns
- auth failure cooldowns
- notebook capacity heuristics
- transient RPC heuristics

It is therefore both a content wrapper and a reliability shim.

That dual role makes it fragile.
Do not casually simplify this file by removing “defensive weirdness”.
Much of that weirdness exists because NotebookLM behavior is not perfectly stable.

## 7. Vendored client boundary
Directory: `notebooklm-podcast-auto/notebooklm-py/`

Treat this as vendored upstream unless the task clearly requires editing it.
The wrapper layer assumes its API shape.
If you change vendored client behavior, re-check every higher-level script that imports:
- `NotebookLMClient`
- `RPCError`
- `notebooklm.rpc.types.*`

## 8. Course-specific generation forest
Directory: `notebooklm-podcast-auto/personlighedspsykologi/`

This is not just “data”.
It contains the course-specific generation system, including:
- scripts
- prompts
- output trees
- evaluation lanes
- download/upload/rollout logic

The most important scripts are under `personlighedspsykologi/scripts/`.

## 9. Weekly generation script
Source: `personlighedspsykologi/scripts/generate_week.py`

This file is one of the highest-leverage pieces of course-specific logic in the repo.
It bridges:
- show config
- source catalogs
- prompt assembly
- NotebookLM invocation
- output routing

Important architectural point:
it imports queue-side context builders from `notebooklm_queue`.
That means the boundary between `notebooklm_queue` and `notebooklm-podcast-auto` is not clean.

This is a dependency seam to be aware of, not necessarily a bug.

## 10. Rollout orchestration
Source: `personlighedspsykologi/scripts/rollout_week.py`

This is the A→B rollout pipeline for generated variants.

Snippet:
```python
# notebooklm-podcast-auto/personlighedspsykologi/scripts/rollout_week.py
Pipeline phases:
  1. generate
  2. download
  3. upload
  4. register
  5. exclude
  6. publish
```

This script is explicitly designed to be:
- idempotent
- unattended
- restart-safe

That makes it operationally important.
If you change any artifact naming, registry logic, or feed exclusion rules, this script is part of the blast radius.

## 11. Hidden complexity in rollout
`rollout_week.py` is not just a thin shell.
It owns:
- drive service lookup
- registry mutation
- variant activation semantics
- config mutation
- git push retry logic
- sleep/retry behavior over long waits

This is a high-risk script because it mixes business state and infrastructure side effects.

## 12. Why this subsystem feels unstable
It has three different architecture styles in one tree:
- vendored library
- generic wrapper
- course-specific automation scripts

That is the core reason it can feel inconsistent.
The inconsistency is structural, not only stylistic.

## 13. Call chain: generic generation
Typical generic call chain:
1. operator invokes `generate_podcast.py`
2. wrapper resolves sources and profile
3. wrapper instantiates `NotebookLMClient`
4. wrapper submits artifact generation requests
5. artifacts are downloaded/written according to wrapper logic

This path is useful for low-level generation debugging.

## 14. Call chain: course weekly generation
Typical `personlighedspsykologi` chain:
1. weekly script discovers/filters week sources
2. prompt/context assembly from course data
3. NotebookLM request scheduling
4. local output routing into subject-specific output tree
5. later scripts consume those outputs for upload, publication, and portal linking

This path is useful for “the wrong content got generated” debugging.

## 15. Key quirks
- `sys.path` mutation is expected
- vendored client boundaries are porous
- profile state and rate-limit heuristics live in wrapper code
- subject scripts are not generic and should not be treated as templates
- generated outputs become inputs for later subsystems

## 16. Safe change strategy
When changing this subsystem:
1. decide whether the issue is generic NotebookLM client behavior or course-specific wrapper behavior
2. avoid changing `notebooklm-py` unless necessary
3. preserve filename and output-tree conventions unless all downstream consumers are updated
4. expect operator scripts to be the true API surface

If you are unsure where to start, start with `generate_podcast.py` for generic issues and `personlighedspsykologi/scripts/generate_week.py` for course issues.

