#!/usr/bin/env bash
# Verify each GrokTeam patch: its test fails on clean src and passes with the patch alone; then all patches together.
# Usage (from the repo root): PY=/path/to/python GrokTeam/patches/verify.sh [/tmp/gt-builder-verify]
# Works in a throwaway git worktree; never touches the real src/.
set -u
PY=${PY:-python}
REPO=$(git rev-parse --show-toplevel)
WT=${1:-/tmp/gt-builder-verify}
case "$WT" in /tmp/?*) ;; *) echo "refusing: the worktree must be under /tmp (got $WT)"; exit 1;; esac
# always a fresh tree at HEAD: a worktree left from an earlier run (stale src, old patches) is removed first
if [ -e "$WT" ]; then git -C "$REPO" worktree remove --force "$WT" 2>/dev/null || rm -rf "$WT"; fi
git -C "$REPO" worktree prune
git -C "$REPO" worktree add --detach "$WT" HEAD >/dev/null || { echo "cannot create worktree $WT"; exit 1; }
mkdir -p "$WT/GrokTeam" && rm -rf "$WT/GrokTeam/tests" && cp -r "$REPO/GrokTeam/tests" "$WT/GrokTeam/tests"
cd "$WT"
declare -A T=([01]=test_01_validate_no_bms [02]=test_02_plan_front_end_unresolved [03]=test_03_ai_evidence_budget
              [04]=test_04_count_overshoot [05]=test_05_omitted_systems_as_exceptions
              [06]=test_06_schedule_only_template_lines [07]=test_07_standing_rulings
              [08]=test_08_schedule_reader)
# patches that land together: 04's schedule cap reads 08's schedule_qty facts, so 04's "after" has 08 applied too
declare -A DEP=([04]=08)
for p in "$REPO"/GrokTeam/patches/0*.patch; do
  n=$(basename "$p" | cut -c1-2); t="GrokTeam/tests/${T[$n]}.py"
  git checkout -q -- src && git clean -fdq -- src   # a patch's new file (07: bms/rulings.py) goes too
  before=$($PY -m pytest -q -p no:cacheprovider "$t" 2>&1 | tail -1)
  if [ -n "${DEP[$n]:-}" ]; then
    for d in "$REPO"/GrokTeam/patches/${DEP[$n]}-*.patch; do git apply "$d" || echo "$n: its dependency $(basename "$d") does not apply"; done
  fi
  git apply "$p" || { echo "$n: patch does not apply"; continue; }
  after=$($PY -m pytest -q -p no:cacheprovider "$t" 2>&1 | tail -1)
  echo "$n  before: $before  |  after: $after${DEP[$n]:+  (with ${DEP[$n]})}"
done
git checkout -q -- src && git clean -fdq -- src   # a patch's new file (07: bms/rulings.py) goes too
for p in "$REPO"/GrokTeam/patches/0*.patch; do git apply "$p" || echo "combined: $(basename "$p") does not apply"; done
echo "combined GrokTeam tests: $($PY -m pytest -q -p no:cacheprovider GrokTeam/tests 2>&1 | tail -1)"
echo "(src left patched in $WT for the full suite: PYTHONPATH=src $PY -m pytest -q -m 'not slow')"
