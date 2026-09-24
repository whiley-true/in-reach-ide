# in-reach-ide

## What this is

`in-reach-ide` is the desktop IDE for Halo: Reach Megalo game variants. It is a PyQt6 application built on the
[`in-reach`](../in-reach) library and CLI (a separate repo and PyPI package, `in-reach`), which owns everything that isn't
a widget: the project model, linker, compiler, native `_reachvarianttool` module, shadow VCS, launchers and the command
line. This package depends on it (`in-reach>=0.4.0,<0.5`, API_VERSION 2) and calls `in_reach.api` plus the framework-agnostic
`in_reach.app.*` modules; it never reimplements them.

The layering is one-way: **`in_reach` never imports `in_reach_ide`** (its CLI reaches it by name, through
`importlib`, only for `in-reach run`). Start-up is `in_reach_ide.cli` (`in-reach-ide`, or `in-reach run`), which checks
Windows and the supported `in_reach.api.API_VERSION` range (`SUPPORTED_API_VERSIONS`) before opening a window. Raise
that range only after checking the IDE against the new API.

Sister package: `within-reach` (system detection, hot reload / screen grabber), depended on (`within-reach>=0.2.0,<0.3`): the
IDE's "Verify System Settings" -- Tesseract on `PATH`, the Steam / Halo: MCC / gametype / map folders -- is
`within_reach.system_verify` (`welcome`, `verify_dialog`, `maps_panel`, `explorer` and `main_window` import it as
`from within_reach import system_verify`; `tests/test_within_reach_dependency.py` keeps that true). `in-reach` no longer has a copy of it (dropped in 0.4.0).

## Development

- Install: `pip install -e ../in-reach` (or a released `in-reach`), then `pip install -e ".[dev]"`.
- Tests: `python -m pytest tests -q` (Windows; the real Qt platform, not `offscreen` -- that has no emoji font). New
  behaviour needs tests; see `.claude/rules/tests-required.md`. Test helpers shared with the core live in
  `tests/hill_project.py` (a copy of the core's design example -- keep them in step by hand).
- Never commit unless asked (`.claude/rules/no-auto-commit.md`).
- New IDE functionality needs a command palette entry and, where sensible, a shortcut
  (`.claude/rules/shortcuts-and-command-palette.md`).
- Releases use the same GitHub flow as `in-reach`: `development` -> `release/vX.Y.Z` (Cut Release workflow) -> PR into
  `main` (tests, bump label, branch source enforced) -> tag, GitHub Release, sync back, PyPI (trusted publishing).
  The version lives in `pyproject.toml` and `src/in_reach_ide/__init__.py`. This package is pure Python: one
  `py3-none-any` wheel and an sdist. Release `in-reach` first when the IDE needs a new API.

## This repo's actual scope right now

- `src/in_reach_ide/` -- a VSCode-shaped PyQt6 desktop IDE (`main_window.py` is the top-level
  window): a frameless custom top bar with real File/Edit/Selection/View/Launch dropdown menus
  (Selection is just Select All; View has Command Palette, an Appearance submenu, a click-through
  to each activity-bar panel, and View Logs; Launch has Launch Halo MCC/Launch RVT, each greyed out
  until actually available), a fixed, reorderable activity bar (`activity_bar.py`) with an overflow
  "..." popout once its icons don't fit, a split-capable tab panel (`tabs.py`, up to 3 side-by-side
  pane-groups x 2 stacked panes, plus any number of single-pane popout windows a tab can be dragged
  or right-click-moved out into, each with its own bottom status bar showing Ln/Col and Spaces for a
  text tab, wired through `MainPanelArea.on_cursor_info`) and OS file dialogs that always open on the IDE's own current
  screen (`file_dialogs.py`), a text/JSON/Markdown editor (`editor.py`, `markdown_preview.py`) with
  a VSCode-style Find/Replace bar (`find_replace.py`) -- spaces drawn wider than the font's own, no line
  wrapping by default (a long line scrolls under a horizontal scrollbar) and "Toggle Word Wrap" (Alt+Z,
  `word_wrap.py`: one switch for every editor, persisted to the `.env`) to opt in; VSCode-style indent guides (a faint
  line at each indentation level, the one around the cursor's block brighter; `indent_guides.py` works out the step, each
  line's depth and the active guide, `_PlainTextEditor.indent_guide_lines()` where they go); the bottom bar's Ln/Col/Spaces
  segments show for `.txt`/`.json`/`.mgl` tabs (`editor.shows_cursor_info`); a theme switch re-picks every open
  editor's and diff tab's syntax colours in place (`MainPanelArea.refresh_theme`) without saving or reloading
  anything -- primary-sidebar
  panels, each under one shared bold title strip naming whichever view is showing
  (`MainWindow.sidebar_header`), (Dashboard/Welcome `welcome.py`, Explorer `explorer.py` -- also
  owns the Quick Launch section (Export File and Launch RVT on one row, View Compiled Megalo across the next; the
  Welcome tab has Start, Help and Recent -- no verify section: `MainWindow.verify_on_first_run`, from `app.run`, opens
  Verify System Settings by itself while nothing is verified, and the palette's "Verify System Settings" runs it again;
  Halo: MCC via Steam only), a
  collapsible "Locations" section of buttons that open a `system_verify`-resolved install folder in the OS file
  explorer (the variant/map folders, "Open In-Reach Maps" -- `.in-reach/maps`, created on demand -- and "Open Hot
  Reload Folder"), an empty collapsible "Hot Reload Config" section, and, pinned to the bottom of the Dashboard, a
  "Notepad (gitignored)" section (`notepad.py`): a line-numbered, autosaving plain-text view of the active project's own
  `Notes.txt`, its "Open in Editor" button on the section's header line (`CollapsibleSection.add_header_widget`; the
  palette still has "Open Notepad in Window"). `Notes.txt` is personal: opening a project makes sure its `.gitignore`
  lists it (`in_reach.app.new_project.ensure_gitignore`) and the shadow VCS never versions it (`Notes.txt` is created
  empty for a new project, so the box's own placeholder text shows), Git `git_panel.py`
  -- a view over the Dulwich shadow VCS below, with a live "Changes" section split into staged/
  unstaged file lists (each with its own right-click menu: open changes/open file/open file (HEAD)/
  discard/stage or unstage/reveal in file explorer) plus an inline commit box, a "Stamp Release"
  action (opens `stamp_release_dialog.py`'s own popout for a release message plus major/minor/patch
  spin boxes seeded from the project's last stamped version; declining the "already stamped" warning
  reopens that same dialog, reseeded with the version just tried and the message already typed,
  rather than cancelling the whole attempt; disabled outright while `settings/` has changes Apply
  hasn't picked up yet), a "New Branch" dropdown (a plain "New Branch" off whatever's currently
  checked out, or "New Branch From..." to branch off a specific other branch/stamp instead, also
  reachable from the command palette) and Delete/Merge Branch controls, and a lane-painted commit
  graph across every branch (`git_graph.py`, including a merge commit's own second-parent lane; its
  own text column tracks the sidebar's actual width rather than a fixed size, and elides an overlong
  commit message/branch-tag list rather than letting it run into the sha column) sitting above a
  user-draggable vertical splitter down to the "Files Changed" list for a selected commit (in place
  of that list's old fixed height cap) -- selecting a commit lists its own changed files, each
  opening a single-pane unified diff tab (`unified_diff_view.py`); clicking an uncommitted changed
  file instead opens a side-by-side, VSCode-style diff tab (`diff_view.py`, opened via `tabs.py`'s
  own `open_diff()`) showing that file's `HEAD` version against its current on-disk content, each
  side with its own shrunk-text preview along its right edge (added/removed lines highlighted)
  mirroring the ordinary editor's own minimap,
  Scripts `scripts_panel.py` (the active project's script, either kind, every part under a collapsible section heading:
  Envs -- each `script/env/<name>.env` as one column of names (no "(no env)" row; the active one has a star to its
  left; each row's flags and constants are its tooltip), Use/Edit/Copy (a new env copying the selected)/New (an empty
  one)/Delete; Apply with more than one env first asks which to build with (`MainWindow._choose_build_env`, with "Don't
  ask again", back on in Settings) -- then Script (its problems, only when it has
  any, and Open Script) and Budget; a single file adds, under Script, "Use the button above to edit the Megalo Script. It
  has the same syntax as Reach Variant Tool (a link to its docs) with the following additional features:" and the
  in-reach annotations it can use, and "Convert to Project (experimental)" (no Check button: the script is checked as it
  is typed, saved, or
  changed on disk -- `MainWindow._script_watcher`), which asks first and offers
  "Back Up && Convert" (`api.backup_script()`); a script project adds modules, blocks (drag to reorder, "Move to"
  on a fragment), Check/Link/New Module and fusion. It does no checking itself: `MainWindow._refresh_script_views()`
  checks once per change and feeds it, the Problems tab, the Documentation view and the editor's hover text; every
  open editor underlines its file's Problems-tab entries -- red for an error, amber for a warning, the message on
  hover (`editor.set_problem_provider`, `TextEditorWidget.refresh_problem_marks`, redrawn on
  `ProblemsPanel.problems_changed`) -- and saving a file with errors asks first but saves if told to
  (`TabPane._confirm_save_with_errors`; a pending check runs before the question, `MainWindow._check_before_save`);
  building stays blocked, since the link fails. A Megalo file's editor also autocompletes as it is typed
  (`completion_popup.py`, a list that is the editor's child so the editor keeps the keys -- Up/Down, Enter/Tab, Escape;
  `editor.set_completion_provider`, `MainWindow._complete_script` over `in_reach.app.script_project.completion`, with the
  open project's declared names from its docs; after `alias NAME =` only alias targets). A Megalo file also folds its
  `do`/`if`/`function` ... `end` blocks (`code_folding.compute_megalo_fold_ranges`; the line-number gutter, a sibling
  of the text view, follows its `updateRequest` so it scrolls with the text), tints every copy of the selected
  text, and offers "Convert to Alias..." on right-click (one undo step, over `script_project.refactor`)),
  Documentation `documentation_panel.py` (the script's generated documentation, `in_reach.app.script_project.docs`, top
  to bottom: a collapsible Description (the documentation's own, plain text, `api.set_docs_description` ->
  `script/docs.json`; not the gametype's in-game one); "Open Overview.md" (writes `build/docs/`) and Refresh, then "Edit
  Readme.md" (creates `script/README.md` if missing) and "Preview Readme.md"; Docstrings (Docstring/Where; a docstring's
  longer text is its section of `script/DOCSTRINGS.md` -- activating one or Edit opens that file at the section,
  `api.docstring_section`; its `<!-- file:line -->` where-lines can't be edited there (protected spans, like a JSON
  `$schema` line) and follow each save of a `.mgl` file, an open tab of it reloading unless it has unsaved edits --
  `MainWindow._refresh_docstrings`; Locate goes to its line; Remove deletes it after asking, `api.remove_doc_entry` -- a file with
  unsaved edits is refused); Tags (the tag filter, which narrows the docstrings, over an info box saying what carries
  each tag). There is no rendered overview in the panel),
  Testing `testing_panel.py`, Playtest `playtest_panel.py` (a sprinting-man
  activity-bar icon directly under Testing, with its own View menu/palette entry), LLM `llm_panel.py` --
  Testing/Playtest/LLM are all still placeholder-only stubs -- Map Files `maps_panel.py`, which lists clickable,
  link-styled folder "slugs" for the Map Variants/Hopper Variants/User Maps folders that Verify
  System Settings resolved (each opens that folder in the OS file explorer) plus an "Open In-Reach
  Maps" button, Kanban `kanban_panel.py` -- the active project's boards (create/open/rename/delete,
  which is the default, and a background colour or a custom image copied into
  `.in-reach/kanban/backgrounds/`) -- with the board itself drawn as a Trello-style editor tab
  (`kanban_board.py`: columns you can add/rename/move/delete, drag-and-drop cards you can add/edit/
  mark done/delete, per-board labels; `kanban_dialogs.py`: the card, labels and label-colour
  dialogs); clicking the Kanban icon also opens the project's default board, and the shared SQLite
  store behind all of it is created lazily the first time the view is used -- Search
  `search_panel.py`, laid out after VSCode's own Search view: Match Case/Match Whole Word/Use
  Regular Expression toggles inside the query box, a chevron that reveals a replace row (Preserve
  Case, Replace All), and a "..." toggle that reveals "files to include" (with a "Search only in
  Open Editors" toggle) and "files to exclude" glob boxes),
  a "Select Env" palette submenu (one entry per `script/env` env of the open project, the active one
  marked, plus "No env") and "New Env", mirrored by a left-edge status-bar "Env: <name>" segment that
  opens the same pick (hidden with no project or no envs), checking the script as you type (any editor
  on a file under the project's `script/` -- `output.mgl`, `.mgl`, a manifest or an env file -- is checked
  unsaved with `api.check_text` 400 ms after typing stops, via `MainPanelArea(on_text_edited=...)`), hover
  text in Megalo editors for a declared name (its slot or table entry and its `@doc`,
  `editor.set_megalo_hover_provider()`), a bottom panel (`bottom_panel.py`)
  whose first tab is a live, read-only view (`logs_panel.py`) of every record the app's own logger
  emits, a Settings popout (`settings_dialog.py`) with a live theme picker (`theme.py`/
  `theme_picker.py`), and a VSCode-style command palette (`quick_access.py`).

- `src/in_reach_ide/kanban_db.py`, `project_search.py`, `quick_open.py`, `indent_settings.py`, `recent.py` -- the
  framework-agnostic helpers only the IDE uses (they used to live in `in_reach.app`): the SQLite Kanban store, project
  text search/replace, quick-open file listing, per-file indentation settings, the recent-projects list.
- `src/in_reach_ide/cli.py` -- `in-reach-ide` / `launch()`; `app.py` -- builds the `QApplication` and runs it.
- `src/in_reach_ide/problems_panel.py`, `scripts_panel.py`, `megalo_highlighter.py` -- the script-project views (Problems tab,
  Scripts view, Megalo syntax colouring); `main_window.py`'s `_refresh_script_views()` calls `in_reach.api.check()` once
  per change and feeds both panels.
- The Scripts view is also the **composition board**: a module's checkbox switches it on/off, blocks drag into a new build
  order, and a fragment's right-click "Move to" puts it in another block. Every one is a text edit through
  `in_reach.api` (`set_module_enabled`/`set_block_order`/`move_fragment` -> `project.toml` / a `-- @fragment` line), then a
  re-check; a refused edit is reported and the views snap back. The palette has "Enable/Disable Script Module".
- "Open Script" (the Scripts view's button + palette) opens the script to edit -- `script/output.mgl`, or a script project's
  first block file. "View Decompiled" (palette) opens `build/Decompiled.txt`, read-only -- the built `.bin`'s script as RVT
  shows it -- via `api.show(folder, "rvt")`; "View Compiled Megalo" (Dashboard) is the `rvt+` view. A project created from
  the Welcome tab is built once straight away (`WelcomeTab._initial_build` -> `api.initial_build`), so it always has one.
- `tests/` -- `pytest-qt` widget tests (`test_ide_smoke.py` is the largest and covers most of `main_window.py`/
  `activity_bar.py`/`tabs.py` end-to-end) plus tests of the moved helpers.
