---
name: kg-constructor
description: Build a plant-biology knowledge graph from a directory of paper JSONs by fanning extraction out across parallel subagents. Use this whenever the user wants to extract a KG from plant-science papers WITHOUT using the Anthropic Batch API or the project's anthropic_batch.py — for example "construct a KG from /path/to/papers", "build a KG from these papers inline", "run kg-constructor on this directory", "extract relationships from these plant papers without the batch API", or any request that mentions extracting / constructing / building a knowledge graph from a folder of journal-paper JSONs. This skill is the right choice for ad-hoc runs over 10–5000 papers from any onboarded publisher (OUP, Elsevier, Wiley, Springer, Nature, Cell-press, PNAS, Science/SciAdv, PMC-fulltext). Strongly prefer using this skill over re-implementing extraction by hand when the user wants per-section JSON + per-paper CSV + a merged CSV; Claude tends to undertrigger here.
---

# kg-constructor

Construct a plant-biology knowledge graph from a directory of paper JSONs by fanning extraction out across **parallel subagents** — one subagent per section — and consolidating their output into per-section JSON, per-paper JSON, per-paper CSVs, and a single merged CSV. Faithful to the 26-column schema defined in the parent project's `validate_kg.py` (see `PLANT_KG_PROJECT_DIR` below).

**The bundled prompt is a short generic template**, not a research extraction protocol. Every subagent reads the resolved prompt verbatim. To use private extraction rules, set `PLANT_KG_PROJECT_DIR` to a local project directory outside this repository containing `prompt_v12_iter9.txt`. Keep that private file outside the installed skill directory and out of published archives.

## Configuration

The skill is fully self-contained, but two **optional** integrations with a parent `plant_kg_construction` project are controlled by one environment variable:

- `PLANT_KG_PROJECT_DIR` — absolute path to a local checkout of `plant_kg_construction`. When set, the skill will:
  1. Prefer `$PLANT_KG_PROJECT_DIR/prompt_v12_iter9.txt` over the bundled copy (to use private extraction rules without publishing them).
  2. Run `$PLANT_KG_PROJECT_DIR/validate_kg.py` against the merged CSV in step 8.
  3. Use `$PLANT_KG_PROJECT_DIR/runs/inline_kg/...` as the default output-dir suggestion.

When unset (or pointing at a non-existent path), the skill falls back to the generic template at `references/prompt_v12_iter9.txt`, skips the project validator (the portable checks in step 8 still run), and suggests `$HOME/kg-constructor-runs/...` as the output dir. The generic template is illustrative; project-specific extraction quality requires your own private prompt.

Resolve the env var **once at the start of every run** and reuse the resolved values for the rest of the workflow:

```bash
PROJECT_DIR="${PLANT_KG_PROJECT_DIR:-}"
if [ -n "$PROJECT_DIR" ] && [ -f "$PROJECT_DIR/prompt_v12_iter9.txt" ]; then
  PROMPT_PATH="$PROJECT_DIR/prompt_v12_iter9.txt"
else
  PROMPT_PATH="$HOME/.claude/skills/kg-constructor/references/prompt_v12_iter9.txt"
fi
```

## Hard constraints

- **No Anthropic SDK. No API calls. No API keys.** This skill does not import the `anthropic` package, does not invoke `anthropic_batch.py`, does not read `.env`, and does not make outbound network calls. Extraction happens via subagents inside the user's Claude Code session.
- **Output directory is user-supplied.** Always ask before running.
- **Three output layers must be produced.** Raw per-section JSON, per-paper JSON, per-paper CSV, and a merged 26-column CSV identical to the project's schema.

## Workflow

When the skill triggers, follow these steps in order. Mark progress with `TodoWrite` so the user can see where the run is.

### 1. Confirm input and output paths

- Confirm the **input directory** with the user (recursively walked). It may be a top-level publisher tree like `/path/to/papers` or any deeper subfolder.
- **Ask the user for an output directory.** Do not pick a default. Suggestion to offer: if `$PLANT_KG_PROJECT_DIR` is set, `$PLANT_KG_PROJECT_DIR/runs/inline_kg/<YYYYMMDD_HHMMSS>/`; otherwise `$HOME/kg-constructor-runs/<YYYYMMDD_HHMMSS>/`. Do not proceed without confirmation.
- If the chosen output dir exists and is non-empty, confirm with the user before overwriting.

### 2. Prepare sections

Run the bundled Python script:

```bash
python3 ~/.claude/skills/kg-constructor/scripts/prepare_sections.py <INPUT_DIR> <OUTPUT_DIR>
```

This walks the input directory recursively, identifies paper JSONs (skipping `*_ids.json`, `*_metadata.json`, `batch_ids.json`, `*.jsonl`, and tiny files), splits each paper into its non-boilerplate sections via the bundled `extract_sections` port, appends DIVE terms and abbreviations, and writes:

- `<OUTPUT_DIR>/sections/<custom_id>.txt` (one per section)
- `<OUTPUT_DIR>/metadata.json` (custom_id → paper metadata)

The script handles all publisher families (OUP, Elsevier, Wiley, Springer, Nature, Cell-press, PNAS, Science/SciAdv, PMC-fulltext) via the canonical fallback chain (`sections[]` → `full_text[]` → `structure[]` → `content`). It prints a JSON summary on completion — show the user `papers_found`, `papers_processed`, and `sections_written` before continuing.

If `papers_processed == 0`, abort and ask the user to double-check the path.

### 3. Render the run banner

Build the banner state and render it so the user sees what the run will do:

```bash
echo '{"kind":"banner", ...}' | python3 ~/.claude/skills/kg-constructor/scripts/render_progress.py
```

State fields for the banner: `input`, `output_dir`, `model` (the model powering the current session), `max_concurrent` (default `10`, max `20`), `papers_total`, `sections_total`, `waves_total = ceil(sections_total / max_concurrent)`.

Print the rendered banner inside a fenced code block so monospace alignment is preserved.

### 4. Dispatch extraction in waves

Build the queue of section .txt files in `<OUTPUT_DIR>/sections/`. **Resume**: if `<OUTPUT_DIR>/json/per_section/<custom_id>.json` already exists and parses as JSON, skip that custom_id.

For each wave of up to `max_concurrent` sections, dispatch one `Agent` call per section **in the same orchestrator message** (parallel tool use). Use `subagent_type: general-purpose` (needs Read and Write). Each agent's prompt is the contract below. Substitute `<PROMPT_PATH>`, `<SECTION_TXT_PATH>`, `<OUTPUT_JSON_PATH>`, `<CUSTOM_ID>` per task.

```
Goal: Extract a knowledge graph from one section of a plant-science paper.

Task ID: <CUSTOM_ID>
Inputs:
  - Extraction rules:  <PROMPT_PATH>
  - Section text:      <SECTION_TXT_PATH>
Output:
  - JSON array file:   <OUTPUT_JSON_PATH>

Steps (do exactly these, nothing more):
1. Read the file at <PROMPT_PATH>. It contains a prompt with a {TEXT} placeholder.
   If using the bundled generic template, also read its sibling schema_quick_reference.md.
2. Read the file at <SECTION_TXT_PATH>.
3. Mentally substitute the section text into the {TEXT} placeholder.
4. Apply the prompt's rules and produce a JSON array of relationship objects in
   the schema the prompt defines. Follow every rule in the prompt exactly
   using the JSON field names supported by the CSV exporter.
5. First write to <OUTPUT_JSON_PATH>.tmp using the Write tool, then use the Bash
   tool to `mv <OUTPUT_JSON_PATH>.tmp <OUTPUT_JSON_PATH>`. The file MUST be
   valid JSON. No markdown fences. No prose. Write [] if empty.
6. After the rename succeeds, reply with EXACTLY this single-line JSON object:
   {"task_id":"<CUSTOM_ID>","status":"DONE","triples":<N>,"output":"<OUTPUT_JSON_PATH>"}
   On any failure in steps 1-5, instead reply with:
   {"task_id":"<CUSTOM_ID>","status":"FAIL","reason":"<short reason>"}

No explanations. No markdown. No questions. One line of JSON only.
```

`<PROMPT_PATH>` is the value resolved in the *Configuration* section: `$PLANT_KG_PROJECT_DIR/prompt_v12_iter9.txt` when that env var is set and the file exists, else `~/.claude/skills/kg-constructor/references/prompt_v12_iter9.txt`. `<OUTPUT_JSON_PATH>` is `<OUTPUT_DIR>/json/per_section/<custom_id>.json` — make sure `<OUTPUT_DIR>/json/per_section/` exists before dispatching.

When each wave's subagents all reply:

1. Parse every reply with `json.loads`. Replies that don't parse are FAILs.
2. For each output file, verify it exists and parses as JSON. Files that don't parse: run the partial-recovery flow (re-dispatch the section with prepended note: *"Your previous output was invalid JSON. The first 200 chars were: <snippet>. Re-extract and write valid JSON only."*). Retry budget is 2 per section.
3. Render a `wave` progress block via `render_progress.py` and print it as a fenced code block.
4. Update `<OUTPUT_DIR>/run.log` with the timestamped summary.

If a wave returns rate-limit errors, halve `max_concurrent` for the next wave and wait 30 seconds. After 3 consecutive rate-limit waves, pause and ask the user.

### 5. Aggregate per-paper

Once all sections have either a valid `.json` output or a final FAIL, run:

```bash
python3 ~/.claude/skills/kg-constructor/scripts/aggregate_per_paper.py <OUTPUT_DIR>
```

This produces `<OUTPUT_DIR>/json/per_paper/<paper_id>.json` for every paper.

### 6. Per-paper CSV (Layer 2)

```bash
python3 ~/.claude/skills/kg-constructor/scripts/merge_to_csv.py \
  --per-paper <OUTPUT_DIR>/json/per_paper <OUTPUT_DIR>/metadata.json <OUTPUT_DIR>/csv
```

### 7. Merged CSV (Layer 3)

```bash
python3 ~/.claude/skills/kg-constructor/scripts/merge_to_csv.py \
  --merge <OUTPUT_DIR>/csv <OUTPUT_DIR>/merged_kg.csv
```

### 8. Schema validation

Run the parent project's validator against the merged CSV **only if `PLANT_KG_PROJECT_DIR` is set and `validate_kg.py` exists there**; save its output:

```bash
if [ -n "$PLANT_KG_PROJECT_DIR" ] && [ -f "$PLANT_KG_PROJECT_DIR/validate_kg.py" ]; then
  python3 "$PLANT_KG_PROJECT_DIR/validate_kg.py" > <OUTPUT_DIR>/validation_report.txt 2>&1 || true
fi
```

`validate_kg.py` reads a hardcoded `CSV_FILES` dict, so it may not pick up the merged CSV automatically — the portable checks below always run regardless of env-var state. Confirm: (a) the merged CSV exists and is non-empty; (b) its header is exactly the 26 EXPECTED_COLUMNS; (c) sample 5 rows against the rules in the user-supplied prompt. If any of these fails, note it in the final report.

### 9. Final report

Build the final state and render the closing block:

```bash
echo '{"kind":"final", ...}' | python3 ~/.claude/skills/kg-constructor/scripts/render_progress.py
```

Include the paths to all three output layers (`per_section/`, `per_paper/`, `csv/`, `merged_kg.csv`), validation status, and timing totals. Save the same as `<OUTPUT_DIR>/pilot_timing.md` and `<OUTPUT_DIR>/pilot_timing.json` for later comparison runs.

## Extraction rules

The resolved prompt defines extraction behavior. The bundled file is a generic template; keep project-specific rules and worked examples in a private prompt outside this repository. The schema reference documents CSV compatibility only.

## Concurrency policy

- `--max-concurrent` default 10, hard ceiling 20. Refuse higher.
- Each subagent is a full Claude instance — too many at once will hit rate limits.
- 5000-section runs = ~500 waves of 10. Long but reliable.

## Resources

- `references/prompt_v12_iter9.txt` — short generic extraction template. Subagents read the resolved prompt.
- `references/schema_quick_reference.md` — CSV field names and citation serialization for the bundled exporter.
- `scripts/extract_sections.py` — section-extraction port. Importable module used by `prepare_sections.py`.
- `scripts/prepare_sections.py` — discover + split papers into section .txt files.
- `scripts/aggregate_per_paper.py` — group per-section JSONs into per-paper JSONs (with truncation recovery).
- `scripts/merge_to_csv.py` — per-paper CSV and final merged CSV.
- `scripts/render_progress.py` — render styled progress blocks (banner, wave, heartbeat, fail, final).

## Self-test (before declaring the skill ready in a new environment)

Confirm there are no API-key or SDK leaks in the skill. Review all files and history before publishing, including prompts and archives. The following narrow check covers Python imports / credential reads / network calls only:

```bash
grep -rEn \
  -e "^[[:space:]]*(from|import)[[:space:]]+anthropic" \
  -e "ANTHROPIC_API_KEY|api\.anthropic\.com" \
  -e "^[[:space:]]*(from|import)[[:space:]]+(requests|httpx|aiohttp)\b" \
  -e "urllib\.request|urllib\.urlopen" \
  ~/.claude/skills/kg-constructor/scripts/
```

Expected output: empty. (The strings "anthropic_batch.py", a `requests` dict-variable name, and prose references in SKILL.md are unrelated and fine.)
