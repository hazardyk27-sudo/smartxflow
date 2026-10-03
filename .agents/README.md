# SmartXFlow Agent Layout

The agent system is intentionally small.

```text
AGENTS.md                         # short common bootstrap; read once
.agents/
  roles/
    PREDICTOR.md                  # Predictor role only
    DEVELOPMENT.md                # Development role only
  milestones/
    PREDICTOR.md                  # current Predictor objective
    DEVELOPMENT.md                # current Development objective
  predictor/
    PLAYBOOK.md                   # detailed prediction methodology; open only when needed
  contracts/
    LEARNING_ARCHIVE.md           # archive interface/integrity contract
    RELEASE_FLOW.md               # release/Replit/Hetzner rules; open only for release work
  memory/                         # historical engineering notes; never preload wholesale
```

## Loading rule

A session reads `AGENTS.md`, its own role and its own milestone once. Everything else is demand-loaded.

`memory/` is a searchable engineering notebook, not startup context. Open only a specific note relevant to the current technical task.

## Roles

- Predictor owns match research, prediction truth, settlement and archive content.
- Development owns implementation, archive tooling, validation, datasets, modeling and controlled improvements.
- No Collector conversational role.
- No Match Analyst conversational role; that former role was merged into Predictor.
