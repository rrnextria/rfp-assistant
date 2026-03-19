#!/bin/bash
# Convenience wrapper: runs orchestrator environment diagnostics.
# Delegates to the maistro launcher. Falls back to basic shell checks
# if the launcher fails (e.g. no Python 3.10+ available).
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Try the maistro launcher first
if "$SCRIPT_DIR/maistro" doctor 2>/dev/null; then
    exit 0
fi

# Fallback: basic shell diagnostics
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}Orchestrator V3 — Environment Check (shell fallback)${NC}"
echo ""

errors=0

# Python
if command -v python3 &>/dev/null; then
    echo -e "  ${GREEN}PASS${NC} python3 found"
else
    echo -e "  ${RED}FAIL${NC} python3 not found"
    echo -e "       Fix: Install Python 3.10+ via your system package manager"
    ((errors++))
fi

# Claude CLI
if command -v claude &>/dev/null; then
    echo -e "  ${GREEN}PASS${NC} claude CLI found"
else
    echo -e "  ${YELLOW}WARN${NC} claude CLI not found"
    echo -e "       Fix: npm install -g @anthropic-ai/claude-code"
fi

# Codex CLI
if command -v codex &>/dev/null; then
    echo -e "  ${GREEN}PASS${NC} codex CLI found"
else
    echo -e "  ${YELLOW}WARN${NC} codex CLI not found"
    echo -e "       Fix: npm install -g @openai/codex"
fi

# Directories
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
echo ""
for dir in active_plans reviews research; do
    if [ -d "$REPO_ROOT/$dir" ]; then
        echo -e "  ${GREEN}PASS${NC} $dir/ exists"
    else
        echo -e "  ${YELLOW}WARN${NC} $dir/ not found — mkdir -p $REPO_ROOT/$dir"
    fi
done

echo ""
if [ "$errors" -eq 0 ]; then
    echo -e "${GREEN}Basic checks passed.${NC} Run './how_to/maistro doctor' for full diagnostics."
else
    echo -e "${RED}$errors error(s) found. Fix them before proceeding.${NC}"
    exit 1
fi
