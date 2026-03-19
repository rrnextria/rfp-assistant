# Environment Setup

## Prerequisites

| Tool | Role | Install |
|------|------|---------|
| Python 3.10+ | Runtime | System package manager |
| Claude Code CLI | Orchestrator / Planner / Coder | `npm install -g @anthropic-ai/claude-code` |
| Codex CLI | Reviewer | `npm install -g @openai/codex` |

Python dependencies (`pydantic`, `typer`) are managed automatically by the
orchestrator's isolated venv — you do not need to install them manually.

## Deployment

The `how_to/` directory is self-contained and deploys into any git repository.

### Step 1: Copy the folder

```bash
rsync -av --exclude='.venv/' how_to/ /path/to/your/repo/how_to/
```

The `--exclude='.venv/'` flag prevents copying a local venv into the target repo.
The orchestrator will create a fresh venv on first run in the destination.

### Step 2: Run your first command

```bash
cd /path/to/your/repo
./how_to/maistro doctor
```

On first run the orchestrator automatically creates an isolated venv at
`how_to/.venv/`, installs dependencies, and re-execs itself. No manual
activation or pip install required.

### Step 3: Create the directory structure

```bash
mkdir -p active_plans reviews research
```

The `maistro/sessions/` directory is auto-created at repo root when any
orchestrator command runs. It stores runtime session data and is
automatically added to `.gitignore`. You do not need to create it manually.

### Step 4: Enable in CLAUDE.md

Add this to the repo's `CLAUDE.md`:

```markdown
## Orchestrator System
When asked to implement a plan, review a plan, or research a question,
first read `how_to/guides/orchestrator.md` and follow its instructions.
```

## Environment Management

```bash
# Check environment health (CLI tools, directories, venv, Python version)
./how_to/maistro doctor

# Create or verify the isolated venv
./how_to/maistro --setup-env

# Reset a broken venv (deletes and recreates how_to/.venv/)
./how_to/maistro --reset-env
```

Shell convenience wrappers are also available:

```bash
./how_to/create_env.sh   # Same as --setup-env
./how_to/check_env.sh    # Same as doctor
```

## Deploying to Remote Servers

```bash
# Sync to a remote server (exclude local venv)
rsync -av --delete --exclude='.venv/' how_to/ remote-host:/path/to/repo/how_to/

# Verify on the remote
ssh remote-host "cd /path/to/repo && ./how_to/maistro doctor"
```

The orchestrator bootstraps its own venv on the remote server automatically.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `ModuleNotFoundError: No module named 'orchestrator_v3'` | Use the launcher: `./how_to/maistro <command>` from the repo root |
| `codex: command not found` | Install: `npm install -g @openai/codex` |
| `claude: command not found` | Install: `npm install -g @anthropic-ai/claude-code` |
| Venv is broken or corrupted | Run: `./how_to/maistro --reset-env` |
| Python version too old | Install Python 3.10+ and ensure `python3` points to it |
| `ENVIRONMENT CHECK FAILED` | Run `doctor` for details; use `--skip-preflight` as a temporary workaround |

## Next Steps

See [orchestrator.md](orchestrator.md) for the Claude-facing system reference,
or the [User Guide](workflow.md) for the full end-to-end pipeline.
