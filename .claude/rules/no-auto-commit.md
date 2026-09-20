# Rule: never commit without being explicitly asked

Do not run `git commit` (or `git add` followed by a commit) at the end of a task just because the
change is finished and verified. Finishing and verifying a change is not the same as being asked to
commit it.

Only stage/commit when the user's own message contains an explicit instruction to do so (e.g.
"commit this", "make a commit", "commit and push"). Reporting that a change is ready and working is
the correct stopping point otherwise -- let the user decide when it becomes a commit.
