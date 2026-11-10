# Mutwil Lab — Claude Code Skills

A collection of [Claude Code skills](https://docs.claude.com/en/docs/claude-code/skills)
maintained by the Mutwil Lab for plant-science research workflows.

## Skills in this repository

| Skill | What it does |
|-------|--------------|
| [kg-constructor](./kg-constructor) | Build a plant-biology knowledge graph from a directory of paper JSONs by fanning section-level extraction across parallel Claude subagents. No Anthropic SDK / API key / network required. Output matches the project's 26-column CSV schema. |

Only a short generic extraction template is included. Keep research prompts
outside this repository and outside the installed skill directory.

## Installing skills

Claude Code auto-discovers skills under `~/.claude/skills/`. Pick one of:

### Option A — install a single skill

```bash
git clone https://github.com/manojitharaju016/mutwil_lab_cc_skills.git /tmp/mutwil_skills
mv /tmp/mutwil_skills/kg-constructor ~/.claude/skills/
rm -rf /tmp/mutwil_skills
```

### Option B — install the whole collection (recommended)

```bash
cd ~/.claude/skills
git clone https://github.com/manojitharaju016/mutwil_lab_cc_skills.git
# Then symlink each skill so Claude Code finds it:
ln -s mutwil_lab_cc_skills/kg-constructor kg-constructor
```

Updating later is just `git pull` inside `~/.claude/skills/mutwil_lab_cc_skills/`.

### Option C — install from a release tarball

If a release is published, grab the per-skill tarball from the
[Releases page](https://github.com/manojitharaju016/mutwil_lab_cc_skills/releases)
and extract directly into `~/.claude/skills/`:

```bash
tar xzf kg-constructor.tar.gz -C ~/.claude/skills/
```

## Requirements

- Claude Code (recent version with skill + parallel `Agent` tool-use support)
- Python 3.8+ on `PATH` (skills here use only the standard library — no `pip install` needed)

Individual skills may have their own requirements; see each skill's `README.md`.

## Optional environment variables

These are read by the skills when set; everything works without them.

| Variable | Used by | Effect |
|----------|---------|--------|
| `PLANT_KG_PROJECT_DIR` | `kg-constructor` | Path to a local checkout of `plant_kg_construction`. Enables (a) reading a private local `prompt_v12_iter9.txt` kept outside this repository, (b) running its `validate_kg.py` on the output, (c) suggesting `$PLANT_KG_PROJECT_DIR/runs/inline_kg/...` as the default output dir. |

Example (`~/.bashrc` or `~/.zshrc`):

```bash
export PLANT_KG_PROJECT_DIR="$HOME/plant_kg_construction"
```

## Contributing

Each skill lives in its own directory at the repo root with the canonical layout:

```
<skill-name>/
├── SKILL.md          # frontmatter + skill body (required, what Claude Code loads)
├── README.md         # human-facing docs
├── scripts/          # any Python / shell helpers the skill runs
└── references/       # prompt files, schema cheat-sheets, etc.
```

When adding a new skill: drop the directory at the repo root, add a row to the
table above, and open a PR.

## License

TBD — see individual skill directories for now.
