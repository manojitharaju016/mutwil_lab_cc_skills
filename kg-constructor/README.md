# kg-constructor

A Claude Code **skill** that extracts a plant-biology knowledge graph from a
directory of paper JSONs by fanning section-level extraction out across many
parallel Claude subagents — entirely **inside the Claude Code session**, with
no Anthropic SDK, no API keys, and no outbound HTTP.

Output is faithful to the [`plant_kg_construction`](https://github.com/) project's
26-column CSV schema (the same one enforced by `validate_kg.py`), so KGs produced
by this skill drop into the existing downstream tooling without translation.

---

## Why this skill exists

The reference pipeline in `plant_kg_construction` is built around the **Anthropic
Batch API** (`anthropic_batch.py --prepare / --submit / --resume`). The batch API
is the right tool for tens of thousands of papers: it is cheap, asynchronous, and
designed for that scale.

But the batch API is the wrong tool for:

- **Ad-hoc runs of 10–5,000 papers** where you want results in the current
  session, not in 24h.
- **Interactive iteration** on prompt changes, schema tweaks, or new
  publishers — where waiting for a batch round-trip kills the feedback loop.
- **Environments without an API key** or without the ability to make outbound
  calls (sandboxed Claude Code sessions, air-gapped review, etc.).

`kg-constructor` fills exactly that gap. Each section of each paper is dispatched
as a **subagent task inside the user's Claude Code session**, in waves of N
parallel agents. The orchestrator collects their outputs, retries failures,
aggregates per paper, and emits the same three output layers the batch pipeline
does.

---

## What it produces

Three coordinated output layers in a single user-supplied output directory:

```
<OUTPUT_DIR>/
├── sections/                       # one .txt per section, fed to subagents
│   └── <custom_id>.txt
├── metadata.json                   # custom_id → {journal, year, month, title, filename, section}
├── json/
│   ├── per_section/                # Layer 0 — raw subagent JSON output
│   │   └── <custom_id>.json
│   └── per_paper/                  # Layer 1 — aggregated per paper
│       └── <paper_id>.json
├── csv/                            # Layer 2 — per-paper CSV
│   └── <paper_id>.csv
├── merged_kg.csv                   # Layer 3 — single 26-column CSV (final artifact)
├── run.log                         # timestamped per-wave summary
├── validation_report.txt           # output of validate_kg.py (if available)
├── pilot_timing.md
└── pilot_timing.json
```

The final `merged_kg.csv` has these 26 columns, in this order:

```
custom_id, journal, year, month, title, section, filename,
source, source_identifier, source_type, source_category,
source_extracted_definition, source_generated_definition,
relationship, relationship_category,
target, target_identifier, target_type, target_category,
target_extracted_definition, target_generated_definition,
species, basis,
extracted_associated_process_or_pathway, generated_associated_process_or_pathway,
relevant_citations
```

See [references/schema_quick_reference.md](references/schema_quick_reference.md)
for the CSV field names and citation serialization. Extraction rules belong in
your private prompt.

---

## Supported publishers / paper formats

The bundled `extract_sections.py` module handles every onboarded publisher in
the parent project, via a canonical fallback chain
(`sections[]` → `full_text[]` → `structure[]` → `content`):

| Family       | Journals                                                           | Notes |
|--------------|--------------------------------------------------------------------|-------|
| OUP          | jxb, pcp, plcell, plphys                                           | `sections[]` with `section_name` + `sub_sections`, DIVE terms attached |
| Elsevier     | copb, molecular_plant, plant_comm, plphys_biochem, tips            | Abstract in top-level `abstract`; numeric month dirs (01–12) |
| Wiley        | 5 journals                                                          | Standard `sections[]`; numbered prefixes stripped |
| Springer     | nat_plants                                                          | `json/` subdir layout |
| Nature (PMC) | nature_comm, nature_genetics, nature_cell_bio                      | PMC-sourced, `json_articles/PMC/` structure |
| Cell-press   | cell, dev_cell, mol_cell, current_biology, etc.                    | Standard with citation handling |
| Science      | science, sciadv                                                     | Body in `content` field with `## Header` markdown |
| PNAS         | pnas                                                                | `--journal json` flag layout |
| PMC fulltext | mixed                                                               | 29+ journals via PMC OAI |

Boilerplate sections (acknowledgements, references, supplementary, author
contributions, ~80 patterns) are filtered out automatically.

---

## How it works

```
┌────────────────────────────────────────────────────────────────────────────┐
│ 1. prepare_sections.py                                                     │
│    Walk INPUT_DIR → discover paper JSONs → split into sections             │
│    → write sections/<custom_id>.txt + metadata.json                        │
└────────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ 2. Orchestrator (Claude Code main loop)                                    │
│    For each wave of up to max_concurrent sections, dispatch one Agent call │
│    per section in parallel. Each subagent:                                 │
│      - Reads the resolved private prompt or generic template              │
│      - Reads its section .txt                                              │
│      - Extracts a JSON array of triples                                    │
│      - Writes json/per_section/<custom_id>.json (atomic via tmp+mv)        │
│      - Replies with one-line JSON status                                   │
│    Failed sections are retried (budget: 2/section).                        │
└────────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ 3. aggregate_per_paper.py                                                  │
│    Group json/per_section/ → json/per_paper/<paper_id>.json                │
└────────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ 4. merge_to_csv.py (two passes)                                            │
│    Pass A: per-paper JSON → csv/<paper_id>.csv                             │
│    Pass B: csv/ → merged_kg.csv (single 26-column file)                    │
└────────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ 5. validate_kg.py (project) + lightweight portable checks                  │
└────────────────────────────────────────────────────────────────────────────┘
```

The orchestrator persists progress to `<OUTPUT_DIR>/run.log` and is **resumable**:
on re-run, any section whose `json/per_section/<custom_id>.json` already exists
and parses as valid JSON is skipped.

---

## Installation

The skill is a self-contained directory. Drop it into your `~/.claude/skills/`:

```bash
# Option A — extract a tarball you received
tar xzf kg-constructor.tar.gz -C ~/.claude/skills/

# Option B — clone from a git repo
git clone https://github.com/<you>/kg-constructor ~/.claude/skills/kg-constructor

# Option C — symlink from a working copy you maintain elsewhere
ln -s /path/to/your/kg-constructor ~/.claude/skills/kg-constructor
```

Claude Code auto-discovers skills under `~/.claude/skills/`. No registration step.

### Requirements

- Python 3.8+ on `PATH` (the helper scripts use only the standard library — no
  pip installs required).
- Claude Code (any recent version that supports skills and `Agent` parallel
  tool use).
- Read/write permission on the output directory you choose.

There is **no** dependency on:

- The `anthropic` Python SDK
- An `ANTHROPIC_API_KEY` or `.env` file
- Outbound network access
- The parent `plant_kg_construction` repo (opt-in via `PLANT_KG_PROJECT_DIR` —
  see *Prompt source* below)

---

## Usage

You don't invoke this skill directly — you ask Claude Code to do KG extraction
and the skill triggers from its description. Typical phrasings:

- *"Construct a KG from `/path/to/papers`."*
- *"Build a KG from these papers inline, without the batch API."*
- *"Run kg-constructor on `/path/to/papers`."*
- *"Extract relationships from this folder of plant journal JSONs."*

The skill will:

1. **Confirm** the input directory and **ask** for an output directory (no default).
2. **Prepare sections** via `prepare_sections.py` and show a summary.
3. **Render a run banner** with paper count, section count, wave count, and the
   model powering the session.
4. **Dispatch waves** of parallel subagents. Default `max_concurrent = 10`,
   hard ceiling `20`. After each wave the orchestrator prints a styled progress
   block with throughput and ETA.
5. **Aggregate, CSV-ify, validate**, and produce a final report.

A 100-paper run with ~5 sections each → ~500 sections → ~50 waves at concurrency
10. Long but reliable; rate-limit pressure is handled automatically (halve
concurrency and back off).

### Concurrency

- `max_concurrent` default: **10**
- Hard ceiling: **20**
- Each subagent is a full Claude instance. Pushing concurrency higher than
  20 will hit rate limits and waste cache.

### Resuming a run

Re-run the skill with the same `<OUTPUT_DIR>`. Any section with a valid
`json/per_section/<custom_id>.json` is skipped. The run picks up at the first
incomplete or failed section.

---

## Prompt source

The repository includes only a short generic template. It does not include a
research extraction protocol or worked research examples.

Every subagent reads one prompt file verbatim, resolved in this order:

1. `$PLANT_KG_PROJECT_DIR/prompt_v12_iter9.txt`, when that variable is set and
   the file exists in a local project directory outside this repository.
2. `references/prompt_v12_iter9.txt`, the bundled generic template.

To use private extraction rules, keep the prompt outside this repository and
outside the installed skill directory, then set:

```bash
export PLANT_KG_PROJECT_DIR="/path/to/private/project"
```

Do not copy private prompts into the skill or include them in public archives.
The generic template illustrates the workflow; it does not reproduce any
project-specific extraction quality or validation rules.

---

## Files in this skill

```
kg-constructor/
├── SKILL.md                          # the skill specification Claude Code loads
├── README.md                         # this file
├── references/
│   ├── prompt_v12_iter9.txt          # short generic extraction template
│   └── schema_quick_reference.md     # CSV field names and citation serialization
└── scripts/
    ├── extract_sections.py           # port of anthropic_batch.py's section logic
    ├── prepare_sections.py           # walk papers → section .txt files + metadata.json
    ├── aggregate_per_paper.py        # per-section JSON → per-paper JSON
    ├── merge_to_csv.py               # per-paper JSON → per-paper CSV → merged CSV
    └── render_progress.py            # styled banner / wave / final blocks
```

All scripts are standalone CLIs — you can run them by hand to debug a stage in
isolation. See each script's docstring for usage.

---

## Output schema

The bundled exporter writes the 26 CSV columns listed above. Category choices,
identifier policies, definitions, and other extraction rules come from the
resolved prompt. See [references/schema_quick_reference.md](references/schema_quick_reference.md)
for CSV compatibility details.

---

## When *not* to use this skill

- **You have 10,000+ papers.** Use `anthropic_batch.py --prepare/--submit/--resume`.
  The Batch API is ~50% cheaper and orders of magnitude more efficient for that
  scale.
- **You want to retry a previous batch run's failures.** Use
  `anthropic_batch.py --retry` with the original batch JSONL + failed-ids file —
  it preserves provenance.
- **You need provenance of token usage / billing per request.** Batch API output
  has those fields; inline subagent dispatch does not surface them per task.
- **You want to change the model used for extraction.** This skill uses whichever
  model is powering the current Claude Code session (i.e., whatever you have
  selected). To pin to Haiku 4.5 specifically, run the batch pipeline.

---

## Limitations

- Subagent output is trusted JSON — the skill validates structure but cannot
  catch subtle rule violations (e.g., a gene mistakenly classified as
  `Treatment`). Run `validate_kg.py` and spot-check.
- Long single sections (e.g., a 30k-token "Results") still go to one subagent.
  If a section is being truncated, split the source JSON's section before
  preparation.
- No per-task token telemetry. Use the batch pipeline if you need to audit
  spend.
- The skill's bundled `extract_sections.py` is a **port** of the parent project's
  canonical version. If `anthropic_batch.py:extract_sections` changes upstream,
  this port can drift. The skill's self-test (in SKILL.md §"Self-test") covers
  API-key/SDK leak detection but not section-fidelity drift — re-port
  periodically.

---

## Sharing this skill

The whole directory is self-contained. To ship it:

- **Tarball:** `tar czf kg-constructor.tar.gz -C ~/.claude/skills kg-constructor`
  — drop in any `~/.claude/skills/` and it works.
- **Git repo:** publish as a standalone repo; recipients `git clone` into their
  skills directory.
- **Claude Code plugin / marketplace:** wrap in a plugin (add
  `.claude-plugin/plugin.json` and move this directory under `skills/` of the
  plugin tree) and serve via a `.claude-plugin/marketplace.json` repo.

All paths into the parent project are parameterized via the
`PLANT_KG_PROJECT_DIR` environment variable (see *Prompt source* above and the
*Configuration* section of `SKILL.md`). The skill is standalone by default;
setting the env var is purely opt-in.

---

## License

Inherit the parent project's license. Specify before public release.
