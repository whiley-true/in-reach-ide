# Rule: keep CLAUDE.md's project context current after making changes

`CLAUDE.md`'s "This repo's actual scope right now" section (and any other factual, "here's what
exists today" description in it) is read as ground truth for this repo's current state -- not
aspirational or historical. Letting it drift out of sync with the actual code is actively
misleading for the next session that trusts it.

After making a change that adds, removes, renames, or materially changes the behavior of something
CLAUDE.md describes -- a new top-level module/package, a command that stops being a stub, a config
key that starts (or stops) being consumed, a described workflow that no longer matches -- update the
relevant part of CLAUDE.md as part of that same piece of work, not as a separate follow-up.

Do not rewrite unrelated sections, and do not pad CLAUDE.md with implementation detail that
belongs in code comments/docstrings instead (per this project's own "no comments explaining WHAT"
convention) -- keep edits scoped to what actually changed, matching the existing section's level of
detail.

If a change is small enough that CLAUDE.md's existing description still holds true, no edit is
needed -- don't touch it just to touch it.
