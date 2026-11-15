# theme.py and fonts/ — where they come from

`theme.py` is **Hookshot's builder theme**, carried over to ReLink. It draws the window's controls itself: the Slate
palette, the Inter type scale, and `Card`, `Button`, `Tick`, `Bar`, `Chip`, `Choice`, `PathEdit` and `Ring` with the
sizes, radii, colours, glows and hover states of Hookshot's own template.

- Source: <https://git.notrexed.dev/Hookshot/Hookshot>, `builder/py/hookshot_builder/theme.py`
- Author: the Hookshot contributors
- License: **GPL-3.0-or-later**, the same as ProjectReLink

The changes from that file are mechanical and marked in it: the module docstring names this project, and the two
`paths.ASSETS` uses became a `FONTS` constant pointing at `fonts/` beside it (`paths` only ever carried that one path).
Nothing else is touched.

`fonts/` holds **Inter** (Regular, Medium, SemiBold, Bold), which the theme loads at start:

- Source: Inter 4.1, <https://github.com/rsms/inter>
- License: **SIL Open Font License 1.1**, in `fonts/Inter-LICENSE.txt`

ReLink and Hookshot are both GPL-3.0-or-later, so this reuse keeps each project's terms. If you redistribute an
AppImage built from this tree, keep this notice, the Inter OFL text and the theme's GPL reference with it.
