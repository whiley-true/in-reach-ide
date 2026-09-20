# Rule: work isn't done until it's tested and green

Do not report a change as finished, ready, or working until both of these hold:

1. The full test suite passes (e.g. `python -m pytest tests -q` for IDE work). Never leave a
   failing test behind, and never report success while a test is red -- fix the underlying issue or
   the test itself, don't skip/xfail it to get past the check.
2. Any new functionality added or changed during the task has test coverage for it, and those new
   tests also pass. "New functionality" includes new widgets/behaviors, bug fixes (add a regression
   test that would have caught the bug), and behavior changes to existing code -- not just brand-new
   files.

If a fix turns out to be UI/visual (spacing, icon size, color, a rendering artifact) and can't be
meaningfully asserted via `pytest-qt` widget state, verify it live (screenshot/manual check) and say
so explicitly in the report -- don't silently skip adding a test without calling that out.

Only skip this bar if the user explicitly says not to bother with tests for a given change.
