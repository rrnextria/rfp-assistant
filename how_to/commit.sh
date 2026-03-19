#!/bin/bash
#
# Commit and push helper script
#
# This script automates the commit workflow: updates project tree with file statistics,
# stages all changes, commits with your message, and pushes to remote.
#
# Works on any branch (main, feature branches, etc.) and automatically sets up
# upstream tracking on first push of new branches.
#
# How to provide multi-line commit messages (zsh-compatible)
#
# This script forwards all arguments directly to `git commit`.
# Use any of the following zsh-safe forms:
#
# 1) Multiple -m flags (recommended):
#    ./commit.sh -m 'Subject' -m '' -m 'Body line 1' -m 'Body line 2'
#
# 2) ANSI-C quoting with explicit newlines (zsh supports $'...'):
#    ./commit.sh -m $'Subject line\n\nBody line 1\nBody line 2'
#
# 3) From a file:
#    printf 'Subject\n\nBody line 1\nBody line 2\n' > commit-msg.txt
#    ./commit.sh -F commit-msg.txt
#
# zsh note: If your message contains '!' and you use double quotes, escape as \!
# or prefer single quotes or $'...'.
#
# 4) Bypass pre-commit hooks for an emergency commit:
#    ./commit.sh --no-verify -m 'WIP: save work'

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# ============================================================================
# ERROR HANDLING - Trap errors and display debug information
# ============================================================================
SCRIPT_NAME="$(basename "$0")"
LAST_COMMAND=""
CURRENT_STEP=""

# Track commands as they execute
trap 'LAST_COMMAND=$BASH_COMMAND' DEBUG

# Error handler - called when any command fails
error_handler() {
  local exit_code=$?
  local line_number=$1
  echo ""
  echo -e "${RED}╔══════════════════════════════════════════════════════════════════════════════╗${NC}"
  echo -e "${RED}║                           COMMIT.SH ERROR REPORT                             ║${NC}"
  echo -e "${RED}╠══════════════════════════════════════════════════════════════════════════════╣${NC}"
  echo -e "${RED}║${NC} Exit Code:    ${CYAN}${exit_code}${NC}"
  echo -e "${RED}║${NC} Line Number:  ${CYAN}${line_number}${NC}"
  echo -e "${RED}║${NC} Current Step: ${CYAN}${CURRENT_STEP:-unknown}${NC}"
  echo -e "${RED}║${NC} Last Command: ${CYAN}${LAST_COMMAND:0:70}${NC}"
  if [ ${#LAST_COMMAND} -gt 70 ]; then
    echo -e "${RED}║${NC}               ${CYAN}${LAST_COMMAND:70:70}${NC}"
  fi
  echo -e "${RED}╠══════════════════════════════════════════════════════════════════════════════╣${NC}"
  echo -e "${RED}║${NC} Common causes:"
  echo -e "${RED}║${NC}   - Exit 123: xargs failed (often due to spaces in filenames)"
  echo -e "${RED}║${NC}   - Exit 128: Git command failed"
  echo -e "${RED}║${NC}   - Exit 1:   General command failure"
  echo -e "${RED}╚══════════════════════════════════════════════════════════════════════════════╝${NC}"
  echo ""
  echo -e "${YELLOW}To debug further, run: bash -x ./commit.sh -m \"your message\"${NC}"
  exit $exit_code
}

# Set the error trap
trap 'error_handler $LINENO' ERR

echo -e "${YELLOW}[commit.sh] Starting commit process...${NC}"
CURRENT_STEP="Initialization"
# Parse script flags and forward the rest to git commit
SCRIPT_NO_VERIFY=0
USER_ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --no-verify|--nv|-nv)
      SCRIPT_NO_VERIFY=1
      shift
      ;;
    --)
      shift
      while [ $# -gt 0 ]; do USER_ARGS+=("$1"); shift; done
      break
      ;;
    *)
      USER_ARGS+=("$1")
      shift
      ;;
  esac
done


# Check for required commands
for cmd in git tree; do
  if ! command -v $cmd &> /dev/null; then
    echo -e "${RED}[commit.sh] Error: '$cmd' command not found. Please install it.${NC}"
    exit 1
  fi
done

# Determine repository root
CURRENT_STEP="Determining repository root"
REPO_ROOT=$(git rev-parse --show-toplevel) || { echo -e "${RED}[commit.sh] Error: Not inside a Git repository${NC}"; exit 1; }
echo -e "${YELLOW}[commit.sh] Repository root resolved to: ${REPO_ROOT}${NC}"

# ROBUST PADDING FUNCTION - The key to reliable formatting!
# This manually ensures exactly 76 characters by counting and padding with spaces
# instead of relying on printf's quirky padding behavior
pad_to_76() {
  local str="$1"
  local len=${#str}

  # If too long, truncate to 76
  if [ $len -gt 76 ]; then
    echo "${str:0:76}"
    return
  fi

  # If too short, manually add spaces
  if [ $len -lt 76 ]; then
    local spaces_needed=$((76 - len))
    local padding=$(printf '%*s' $spaces_needed '')
    echo "${str}${padding}"
    return
  fi

  # Exactly 76, perfect!
  echo "$str"
}

# Function to center text in 76 chars
center_text_76() {
  local text="$1"
  local width=76
  local text_len=${#text}

  # If text is too long, truncate
  if [ $text_len -gt $width ]; then
    text="${text:0:$width}"
    echo "$text"
    return
  fi

  # Calculate padding
  local total_padding=$((width - text_len))
  local left_padding=$((total_padding / 2))
  local right_padding=$((total_padding - left_padding))

  # Build the string manually
  local left_spaces=$(printf '%*s' $left_padding '')
  local right_spaces=$(printf '%*s' $right_padding '')
  echo "${left_spaces}${text}${right_spaces}"
}

# Function to format two-column line (left-aligned columns with fixed spacing)
# Total output: exactly 76 chars
format_two_columns() {
  local left="$1"
  local right="$2"
  local left_width=38
  local right_width=38

  # Truncate if needed
  if [ ${#left} -gt $left_width ]; then
    left="${left:0:$((left_width-3))}..."
  fi
  if [ ${#right} -gt $right_width ]; then
    right="${right:0:$((right_width-3))}..."
  fi

  # Pad left column to exactly 38 chars
  local left_len=${#left}
  local left_spaces_needed=$((left_width - left_len))
  local left_padding=$(printf '%*s' $left_spaces_needed '')
  local left_padded="${left}${left_padding}"

  # Pad right column to exactly 38 chars
  local right_len=${#right}
  local right_spaces_needed=$((right_width - right_len))
  local right_padding=$(printf '%*s' $right_spaces_needed '')
  local right_padded="${right}${right_padding}"

  # Combine: should be exactly 76 chars
  echo "${left_padded}${right_padded}"
}

# Function to format single-column line with bullet (ASCII only)
# Total output: exactly 76 chars
format_bullet_line() {
  local text="$1"
  local line="- ${text}"
  pad_to_76 "$line"
}

# Function to format file stat line (ASCII only)
# Total output: exactly 76 chars
format_file_stat() {
  local label="$1"
  local count="$2"
  local lines="$3"
  # Build: "- Label:              NNN files    (MMM lines)"
  # Using -- to prevent printf from interpreting - as an option
  local line
  line=$(printf -- "- %-23s%3d files    (%s lines)" "$label" "$count" "$lines")
  pad_to_76 "$line"
}

# Exclusion patterns for this repository
FIND_EXCLUSIONS=(
  "! -path */.git/*" "! -path */.venv/*" "! -path */__pycache__/*"
  "! -path */.pytest_cache/*" "! -path */.mypy_cache/*" "! -path */.ruff_cache/*"
  "! -path */dist/*" "! -path */build/*"
  "! -path */.idea/*" "! -path */.vscode/*"
  "! -path */reviews/*" "! -path */active_plans/*"
)

# Update project tree structure before commit
CURRENT_STEP="Updating project tree structure"
echo -e "${YELLOW}[commit.sh] Updating project tree structure...${NC}"

# Generate banner with statistics
TIMESTAMP=$(date '+%a, %b %d, %Y - %H:%M:%S')
BRANCH=$(git rev-parse --abbrev-ref HEAD)
LAST_COMMIT=$(git rev-parse --short HEAD)
TOTAL_COMMITS=$(git rev-list --count HEAD)
FIRST_COMMIT_DATE=$(git log --reverse --format=%ct --max-count=1)
CURRENT_DATE=$(date +%s)
REPO_AGE_DAYS=$(( (CURRENT_DATE - FIRST_COMMIT_DATE) / 86400 ))

# Count directories (excluding patterns from .gitignore)
TOTAL_DIRS=$(find "$REPO_ROOT" -type d \
  ! -path "*/.git/*" ! -path "*/.venv/*" ! -path "*/__pycache__/*" \
  ! -path "*/.pytest_cache/*" ! -path "*/.mypy_cache/*" ! -path "*/.ruff_cache/*" \
  ! -path "*/dist/*" ! -path "*/build/*" \
  ! -path "*/.idea/*" ! -path "*/.vscode/*" \
  ! -path "*/reviews/*" ! -path "*/active_plans/*" \
  ! -name ".git" ! -name ".venv" ! -name "__pycache__" \
  ! -name ".pytest_cache" ! -name ".mypy_cache" ! -name ".ruff_cache" \
  ! -name "dist" ! -name "build" \
  ! -name ".idea" ! -name ".vscode" \
  ! -name "reviews" ! -name "active_plans" | wc -l)

# Function to count files and lines for a given extension
# NOTE: Uses xargs -d '\n' to handle filenames with spaces
count_files_and_lines() {
  local ext="$1"
  local files=$(find "$REPO_ROOT" -type f -name "*.$ext" \
    ! -path "*/.git/*" ! -path "*/.venv/*" ! -path "*/__pycache__/*" \
    ! -path "*/.pytest_cache/*" ! -path "*/.mypy_cache/*" ! -path "*/.ruff_cache/*" \
    ! -path "*/dist/*" ! -path "*/build/*" \
    ! -path "*/.idea/*" ! -path "*/.vscode/*" \
    ! -path "*/reviews/*" ! -path "*/active_plans/*" 2>/dev/null)

  local count=$(echo "$files" | grep -c "^" 2>/dev/null || echo "0")
  if [ "$count" = "0" ] || [ -z "$files" ]; then
    echo "0 0"
    return
  fi

  # Use -d '\n' to handle filenames with spaces correctly
  local lines=$(echo "$files" | xargs -d '\n' wc -l 2>/dev/null | tail -1 | awk '{print $1}' || echo "0")
  echo "$count $lines"
}

# Collect statistics for each file type
read PY_COUNT PY_LINES <<< $(count_files_and_lines "py")
read TS_COUNT TS_LINES <<< $(count_files_and_lines "ts")
read TSX_COUNT TSX_LINES <<< $(count_files_and_lines "tsx")
read JS_COUNT JS_LINES <<< $(count_files_and_lines "js")
read HTML_COUNT HTML_LINES <<< $(count_files_and_lines "html")
read CSS_COUNT CSS_LINES <<< $(count_files_and_lines "css")
read SH_COUNT SH_LINES <<< $(count_files_and_lines "sh")
read MD_COUNT MD_LINES <<< $(count_files_and_lines "md")
read JSON_COUNT JSON_LINES <<< $(count_files_and_lines "json")
read YAML_COUNT YAML_LINES <<< $(count_files_and_lines "yaml")
read YML_COUNT YML_LINES <<< $(count_files_and_lines "yml")

# Combine YAML counts
YAML_TOTAL_COUNT=$((YAML_COUNT + YML_COUNT))
YAML_TOTAL_LINES=$((YAML_LINES + YML_LINES))

# Calculate total source lines (excluding JSON/config)
TOTAL_SOURCE_LINES=$((PY_LINES + TS_LINES + TSX_LINES + JS_LINES + HTML_LINES + CSS_LINES + SH_LINES + MD_LINES))

# Format numbers with commas
format_number() {
  printf "%'d" "$1" 2>/dev/null || printf "%d" "$1"
}

# Generate the banner
{
  echo "╔══════════════════════════════════════════════════════════════════════════════╗"
  printf "║ %s ║\n" "$(center_text_76 "PROJECT TREE STRUCTURE (AUTO-GENERATED)")"
  printf "║ %s ║\n" "$(center_text_76 "$TIMESTAMP")"
  echo "╠══════════════════════════════════════════════════════════════════════════════╣"
  printf "║ %s ║\n" "$(pad_to_76 " This file is automatically generated on each commit to reflect the current")"
  printf "║ %s ║\n" "$(pad_to_76 " state of the repository.")"
  printf "║ %s ║\n" "$(pad_to_76 "")"
  printf "║ %s ║\n" "$(pad_to_76 " If you are an LLM, never edit this file as it is auto-generated on each")"
  printf "║ %s ║\n" "$(pad_to_76 " commit.")"
  printf "║ %s ║\n" "$(pad_to_76 "")"
  printf "║ %s ║\n" "$(format_two_columns "Branch: $BRANCH" "Last Commit: $LAST_COMMIT")"
  printf "║ %s ║\n" "$(format_two_columns "Repository Age: $REPO_AGE_DAYS days" "Total Commits: $TOTAL_COMMITS")"
  printf "║ %s ║\n" "$(pad_to_76 "")"
  printf "║ %s ║\n" "$(pad_to_76 " Directory Structure:")"
  printf "║ %s ║\n" "$(format_bullet_line "Total Directories:  $TOTAL_DIRS")"
  printf "║ %s ║\n" "$(format_bullet_line "Total Source Lines: $(format_number $TOTAL_SOURCE_LINES) lines (excluding JSON/config)")"
  printf "║ %s ║\n" "$(pad_to_76 "")"
  printf "║ %s ║\n" "$(pad_to_76 " File Statistics:")"
  [ "$PY_COUNT" -gt 0 ] && printf "║ %s ║\n" "$(format_file_stat "Python (.py):" "$PY_COUNT" "$(format_number $PY_LINES)")"
  [ "$TS_COUNT" -gt 0 ] && printf "║ %s ║\n" "$(format_file_stat "TypeScript (.ts):" "$TS_COUNT" "$(format_number $TS_LINES)")"
  [ "$TSX_COUNT" -gt 0 ] && printf "║ %s ║\n" "$(format_file_stat "TSX (.tsx):" "$TSX_COUNT" "$(format_number $TSX_LINES)")"
  [ "$JS_COUNT" -gt 0 ] && printf "║ %s ║\n" "$(format_file_stat "JavaScript (.js):" "$JS_COUNT" "$(format_number $JS_LINES)")"
  [ "$HTML_COUNT" -gt 0 ] && printf "║ %s ║\n" "$(format_file_stat "HTML (.html):" "$HTML_COUNT" "$(format_number $HTML_LINES)")"
  [ "$CSS_COUNT" -gt 0 ] && printf "║ %s ║\n" "$(format_file_stat "CSS (.css):" "$CSS_COUNT" "$(format_number $CSS_LINES)")"
  [ "$SH_COUNT" -gt 0 ] && printf "║ %s ║\n" "$(format_file_stat "Shell (.sh):" "$SH_COUNT" "$(format_number $SH_LINES)")"
  [ "$MD_COUNT" -gt 0 ] && printf "║ %s ║\n" "$(format_file_stat "Markdown (.md):" "$MD_COUNT" "$(format_number $MD_LINES)")"
  [ "$JSON_COUNT" -gt 0 ] && printf "║ %s ║\n" "$(format_file_stat "JSON (.json):" "$JSON_COUNT" "$(format_number $JSON_LINES)")"
  [ "$YAML_TOTAL_COUNT" -gt 0 ] && printf "║ %s ║\n" "$(format_file_stat "YAML (.yaml/.yml):" "$YAML_TOTAL_COUNT" "$(format_number $YAML_TOTAL_LINES)")"
  echo "╚══════════════════════════════════════════════════════════════════════════════╝"
  echo ""
} > "$REPO_ROOT/project_tree_structure.md"

# Generate per-file line counts section (markdown format)
{
  echo "## Files by Line Count (Auto-Generated)"
  echo ""

  # Function to list files sorted by line count as markdown table
  # NOTE: Uses xargs -d '\n' to handle filenames with spaces
  list_files_md() {
    local ext="$1"
    local label="$2"
    local limit="${3:-25}"

    local files=$(find "$REPO_ROOT" -type f -name "*.$ext" \
      ! -path "*/.git/*" ! -path "*/.venv/*" ! -path "*/__pycache__/*" \
      ! -path "*/.pytest_cache/*" ! -path "*/.mypy_cache/*" ! -path "*/.ruff_cache/*" \
      ! -path "*/dist/*" ! -path "*/build/*" \
      ! -path "*/.idea/*" ! -path "*/.vscode/*" \
      ! -path "*/reviews/*" ! -path "*/active_plans/*" 2>/dev/null)

    local count=$(echo "$files" | grep -c "^" 2>/dev/null || echo "0")
    [ "$count" = "0" ] || [ -z "$files" ] && return

    echo "### $label - $count files"
    echo ""
    echo "| Lines | File"
    printf "|------:|%s\n" "$(printf '%80s' | tr ' ' '-')"

    # Use -d '\n' to handle filenames with spaces correctly
    # Note: { ... || true; } prevents SIGPIPE from head causing script failure with pipefail
    { echo "$files" | xargs -d '\n' wc -l 2>/dev/null | sort -rn | head -n "$limit" || true; } | \
    while read lines filepath; do
      [ "$filepath" = "total" ] && continue
      relpath="${filepath#$REPO_ROOT/}"
      printf "| %5d | \`%s\`\n" "$lines" "$relpath"
    done
    echo ""
  }

  list_files_md "py" "Python (.py)"
  list_files_md "ts" "TypeScript (.ts)"
  list_files_md "tsx" "TSX (.tsx)"
  list_files_md "js" "JavaScript (.js)"
  list_files_md "css" "CSS (.css)"
  list_files_md "sh" "Shell (.sh)"
  list_files_md "md" "Markdown (.md)"

  echo "---"
  echo ""
} >> "$REPO_ROOT/project_tree_structure.md"

# Append the tree structure
TREE_EXCLUSIONS="__pycache__|dist|build|*.egg-info|.venv|.mypy_cache|.ruff_cache|.pytest_cache|*.pyc|*.sw?|*.DS_Store|.idea|.vscode|reviews|active_plans"
tree -I "$TREE_EXCLUSIONS" "$REPO_ROOT" >> "$REPO_ROOT/project_tree_structure.md"

# If .gitignore has changed since last commit, untrack files now ignored
CURRENT_STEP="Checking .gitignore changes"
if git diff --name-only HEAD | grep -q '^\.gitignore$'; then
  echo -e "${YELLOW}[commit.sh] .gitignore has changed. Untracking files now ignored...${NC}"
  IGNORED=$(git ls-files --ignored --exclude-standard --cached)
  if [ -n "$IGNORED" ]; then
    # Use -d '\n' to handle filenames with spaces correctly
    echo "$IGNORED" | xargs -d '\n' git rm --cached
    echo -e "${GREEN}[commit.sh] Untracked files now ignored by .gitignore.${NC}"
  else
    echo -e "${YELLOW}[commit.sh] No tracked files are now ignored.${NC}"
  fi
fi

# Stage all changes (including updated tree)
CURRENT_STEP="Staging changes"
echo -e "${YELLOW}[commit.sh] Staging all changes with 'git add -A'...${NC}"
git add -A || { echo -e "${RED}[commit.sh] Error: Failed to stage changes${NC}"; exit 1; }

# Check for commit message (require at least one commit arg like -m/-F)
if [ ${#USER_ARGS[@]} -eq 0 ]; then
  echo -e "${RED}[commit.sh] Error: No commit message provided. Usage: ./commit.sh -m \"message\" [options]${NC}"
  exit 1
fi

# Validate commit message does not contain self-references
# Collect all arguments into a single string for validation
CURRENT_STEP="Validating commit message"
COMMIT_MSG_ALL="${USER_ARGS[*]}"

# Enable case-insensitive matching
shopt -s nocasematch

# Check for prohibited strings
if [[ "$COMMIT_MSG_ALL" =~ anthropic ]] || [[ "$COMMIT_MSG_ALL" =~ claude ]] || [[ "$COMMIT_MSG_ALL" =~ https://claude.com ]]; then
  echo -e "${RED}[commit.sh] Error: Commit message contains self-references${NC}"
  echo -e "${RED}[commit.sh] You are not allowed to mention yourself in the commit message.${NC}"
  echo -e "${RED}[commit.sh] Prohibited strings: 'anthropic', 'claude', 'https://claude.com' (case-insensitive)${NC}"
  shopt -u nocasematch
  exit 1
fi

# Disable case-insensitive matching
shopt -u nocasematch

# Build final commit args
COMMIT_ARGS=("${USER_ARGS[@]}")
if [ "$SCRIPT_NO_VERIFY" -eq 1 ]; then
  echo -e "${YELLOW}[commit.sh] --no-verify set → pre-commit hooks will be skipped for this commit.${NC}"
  COMMIT_ARGS+=("--no-verify")
fi

# Commit with provided arguments
CURRENT_STEP="Committing changes"
echo -e "${YELLOW}[commit.sh] Committing with arguments: ${COMMIT_ARGS[*]}${NC}"
git commit "${COMMIT_ARGS[@]}" || { echo -e "${RED}[commit.sh] Error: Commit failed${NC}"; exit 1; }

# Push to remote (automatically sets upstream for new branches)
CURRENT_STEP="Pushing to remote"
echo -e "${YELLOW}[commit.sh] Pushing to remote repository...${NC}"
git push -u origin HEAD || { echo -e "${RED}[commit.sh] Error: Push failed${NC}"; exit 1; }

echo -e "${GREEN}[commit.sh] Commit and push completed successfully!${NC}"
