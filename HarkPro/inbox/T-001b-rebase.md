# T-001b: rebase onto lead/wave2 and re-push (lead, 2026-10-11)

- Branch hark/T-001b (54b4d51) does not merge into lead/wave2 (28a966c): conflicts in src/bms/coverage.py and
  tests/bms/test_coverage.py. Your report lists 7 failed tests.
- Rebase or merge hark/T-001b onto origin/lead/wave2 at 28a966c. Resolve the conflicts. Run
  `PYTHONPATH=src .venv/Scripts/python.exe -m pytest tests/bms/test_coverage.py -q` and then the full suite
  `-m pytest tests -q -n 10`. Push hark/T-001b again. Update HarkPro/outbox/T-001b-report.md with the real test
  output. Zero failures before you push.
