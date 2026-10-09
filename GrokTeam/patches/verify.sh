#!/usr/bin/env bash
# Verify each GrokTeam patch: its test fails on clean src and passes with the patch alone; then all patches together.
# Usage (from the repo root): PY=/path/to/python GrokTeam/patches/verify.sh [/tmp/gt-verify]
# Works in a throwaway git worktree; never touches the real src/.
set -u
PY=${PY:-python}
REPO=$(git rev-parse --show-toplevel)
WT=${1:-/tmp/gt-verify}
case "$WT" in /tmp/?*) ;; *) echo "refusing: the worktree must be under /tmp (got $WT)"; exit 1;; esac
# always a fresh tree at HEAD: a worktree left from an earlier run (stale src, old patches) is removed first
if [ -e "$WT" ]; then git -C "$REPO" worktree remove --force "$WT" 2>/dev/null || rm -rf "$WT"; fi
git -C "$REPO" worktree prune
git -C "$REPO" worktree add --detach "$WT" HEAD >/dev/null || { echo "cannot create worktree $WT"; exit 1; }
mkdir -p "$WT/GrokTeam" && rm -rf "$WT/GrokTeam/tests" && cp -r "$REPO/GrokTeam/tests" "$WT/GrokTeam/tests"
cd "$WT"
declare -A T=([01]=test_01_validate_no_bms [02]=test_02_plan_front_end_unresolved [03]=test_03_ai_evidence_budget
              [04]=test_04_count_overshoot [05]=test_05_omitted_systems_as_exceptions
              [06]=test_06_schedule_only_template_lines)
for p in "$REPO"/GrokTeam/patches/0*.patch; do
  n=$(basename "$p" | cut -c1-2); t="GrokTeam/tests/${T[$n]}.py"
  git checkout -q -- src
  before=$($PY -m pytest -q -p no:cacheprovider "$t" 2>&1 | tail -1)
  git apply "$p" || { echo "$n: patch does not apply"; continue; }
  after=$($PY -m pytest -q -p no:cacheprovider "$t" 2>&1 | tail -1)
  echo "$n  before: $before  |  after: $after"
done
git checkout -q -- src
for p in "$REPO"/GrokTeam/patches/0*.patch; do git apply "$p" || echo "combined: $(basename "$p") does not apply"; done
echo "combined GrokTeam tests: $($PY -m pytest -q -p no:cacheprovider GrokTeam/tests 2>&1 | tail -1)"
echo "(src left patched in $WT for the full suite: PYTHONPATH=src $PY -m pytest -q -m 'not slow')"
