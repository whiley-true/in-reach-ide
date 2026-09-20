# Rule: new functionality needs a command palette entry, and a shortcut where one makes sense

Any new key/obvious piece of user-facing functionality in the IDE -- a new top-bar menu action, a
new side-panel button, a new dialog's primary action, a new sidebar view -- must be added to the
command palette (`MainWindow.build_command_palette_commands()`) as part of the same change that
adds it, not as a follow-up. "Obvious" means: if a user would reasonably expect to find it by
hitting Ctrl+Shift+P and typing its name, it belongs there. A context-menu action that only makes
sense against a specific, already-selected target (e.g. "Discard Changes" on one particular file,
"Close Others" relative to one particular tab) doesn't need a palette entry of its own -- there's no
"active" one to act on globally, same reasoning VSCode itself uses for not exposing those globally
either.

Give it a real keyboard shortcut too, whenever a sensible one exists:

- If the feature has a genuine VSCode equivalent, use VSCode's own real default keybinding for it
  (not a guess -- look it up). Rebinding an *existing, already-shipped* in-reach shortcut to match
  VSCode instead is a separate, deliberate call to make with the user, not something to do silently
  as a side effect of adding something new.
- If there's no clean VSCode equivalent, either leave it palette-only (perfectly fine -- most of
  this app's own VCS actions are palette-only, same as VSCode's own SCM actions mostly are) or pick
  a free binding that doesn't collide with anything.
- Before picking *any* shortcut, cross-check it against every other window-level
  `QShortcut`/`QAction` shortcut already in the app. Two bindings sharing one key sequence at the
  same `Qt.ShortcutContext.WindowShortcut`/`ApplicationShortcut` scope doesn't win-the-last-one or
  raise an error -- Qt treats every press as *ambiguous* and silently fires **neither**. This was a
  real, live bug: a second `QShortcut` for Ctrl+Shift+P quietly killed the Command Palette's own
  already-working menu shortcut for an entire session before anyone noticed, because both bindings
  looked correct in isolation and neither ever raised. `tests/test_quick_access.py::
  test_no_window_level_shortcut_or_menu_action_collides_with_another` catches this automatically --
  keep it passing, don't work around it.

Keep the top-bar menu (if the feature has one), the shortcut, and the palette entry's own `detail=`
string in sync with each other -- `_add_action()` in `main_window.py` is what wires a menu action's
shortcut so it can never drift from what's actually bound; the palette entry's `detail` should
always be the literal shortcut string passed there, never hand-typed separately.
