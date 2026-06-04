# Rendering the data inside Roblox (instead of HTML + mailbox)

## The concept

Today the plugin is only a *collector*: it walks the DataModel, POSTs the dump to
the local mailbox, and the mailbox runs the Python generators to produce
HTML that opens in your browser. The "view" lives entirely outside Roblox.

The alternative discussed here is to **render the tree inside Studio itself** —
the plugin's dock widget builds the browsable, searchable tree in Luau from the
same dump it already has in memory, with no file written, no Python, no browser,
and no HTTP. The plugin becomes both the collector *and* the viewer.

This is attractive mainly because it removes the single biggest source of
friction for anyone who installs the plugin: having to clone the repo, install
Python, run `mailbox/server.py` in a terminal, and enable Allow HTTP Requests.
An in-Studio viewer is genuinely one-click and fully self-contained — it can ship
as a single `.rbxmx` on the Marketplace and "just work."

## Strengths

The decisive win is **self-containment**. No mailbox, no Python, no terminal,
no localhost, no HTTP toggle. The thing a person downloads is the thing that
runs. That directly answers the "will it be easy to understand?" problem.

It is also **always live and never stale**. The HTML is a snapshot from the last
time you clicked a button; an in-Studio view reads the DataModel on demand, so
what you see is the place as it is right now.

It unlocks **two-way interaction that static HTML simply cannot do**. A row in
the tree can be wired to `Selection:Set({instance})` so clicking it selects the
real object in Explorer, frames the camera on it, or even lets you edit the
attribute/Value inline and write it back. The HTML can only ever *describe* the
data; an in-Studio panel can *act on* it.

Finally it is **trivially distributable** — one model file, installable from the
Marketplace or the Plugins folder, with nothing else to set up.

## Drawbacks

The honest cost is that **you rebuild the UI you already have**. The HTML/CSS/JS
viewer — collapsible nodes, live search with match highlighting, the filter
toggles, expand/collapse-all — all has to be re-implemented in Luau against
Roblox's GUI primitives. None of it is exotic, but it is real work and a second
codebase to maintain alongside the generators.

**Large trees need care.** The dumps run to thousands of nodes. The browser
shrugs at thousands of collapsed DOM elements; a Roblox `ScrollingFrame` with
thousands of `Frame`s at once will stutter and chew memory. A serious in-Studio
viewer almost certainly needs *virtualization* — only build GUI rows for what's
actually on screen and recycle them as you scroll. That is the single hardest
engineering piece, and it is the difference between "feels instant" and "feels
laggy."

**Styling is less expressive.** CSS gives you monospace columns, gradients,
hover states, and precise typography almost for free. Roblox UI can approximate
all of it, but aligned columns, rich text runs, and dense information design take
more fiddling and look a little less polished out of the box.

**The network diagram is the real holdout.** The collapsible *tree* pages port
over cleanly (see below). The node-link **NetworkDiagram** / **ValueNetworkDiagram**
pages do not — there is no Roblox equivalent of an SVG graph with computed
layout. Reproducing them means hand-drawing nodes and edges (rotated frames as
lines, or an `EditableImage` canvas) plus your own layout pass. That is a
substantial sub-project on its own, and the place where "just render it in
Studio" stops being cheap.

**You lose the shareable artifact.** An HTML file can be saved, sent to a
teammate, opened months later, or diffed — all without Studio. An in-Studio view
is ephemeral and only exists while the plugin is open in your session.

## Would it still feel like the HTML — dropdowns, hiding, searching, sorting?

For the **tree pages, yes — near-parity is very achievable**, because every one
of those interactions maps directly onto a Roblox UI primitive:

- **Dropdowns / collapsing.** A node is a row plus a child container; the ▶/▼
  twisty toggles the children's `Visible` (or parents them in/out) and the
  scroll canvas resizes. This is the same collapse behavior the HTML has.
- **Hiding / filters.** The "only `*`/`**`" and "hide [rojo]" checkboxes become
  `TextButton` toggles that set rows' `Visible` — identical effect.
- **Searching.** A `TextBox` driving a filter on each keystroke
  (`GetPropertyChangedSignal("Text")`), hiding non-matches and highlighting hits,
  reproduces the live search box one-to-one.
- **Sorting.** `UIListLayout` with `SortOrder = LayoutOrder` lets you reorder
  rows by name, type, or marker just by reassigning `LayoutOrder` — arguably
  *cleaner* than the HTML, which doesn't currently expose column sorting.

So a person used to the HTML tree would feel at home: same twisties, same search,
same toggles, plus the bonus of click-to-select-in-Explorer. The one thing that
would *not* feel the same is the network diagram, which has no low-effort
in-Studio equivalent.

## Recommendation: a hybrid, not a replacement

The cleanest path is to treat the two views as complementary rather than picking
one:

1. **Add an in-Studio tree viewer** for the everyday case — browse, search,
   collapse, jump to instances. This is the high-value, high-parity, one-click
   experience, and it's what most downloaders will actually use.
2. **Keep the generators/mailbox** as an *optional* "Export HTML" path for the
   network diagrams and for the shareable, archivable, teammate-friendly
   artifact. Power users who want the graphs (and who already have the repo) keep
   them; everyone else never needs to touch a terminal.

That gives newcomers a self-contained plugin that feels like the HTML tree, while
preserving the diagrams and the exportable file for those who want them — without
forcing the mailbox on people just to look at their attributes.
