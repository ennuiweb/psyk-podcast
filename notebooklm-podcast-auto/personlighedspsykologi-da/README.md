# Personlighedspsykologi (Danish Runtime Layer)

This folder is the Danish runtime wrapper for the shared
`personlighedspsykologi` generation pipeline.

It owns:

- Danish prompt/runtime overrides
- the Danish output root contract used by the queue

It does not fork the generation scripts. The queue still uses the shared
wrappers under `notebooklm-podcast-auto/personlighedspsykologi/scripts/`.
