#!/bin/bash
# Convenience wrapper: creates the orchestrator's isolated venv at how_to/.venv/
# Delegates to the maistro launcher.
exec "$(dirname "${BASH_SOURCE[0]}")/maistro" --setup-env
