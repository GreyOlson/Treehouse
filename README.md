# AttributeTreePlugin

A game-agnostic developer tool for mapping every Roblox **attribute** and
**ValueBase object** in a place, rendering them as interactive HTML, and planning
a Value→attribute migration. Extracted from the TsunamiGame `Trees/` tooling into
a standalone project so it can be reused across games and eventually shipped as a
Studio plugin.

## Layout

```
AttributeTreePlugin/
  generators/   game-agnostic Python — turns a Studio dump + a game's src/ into HTML
  plugin/       Roblox Studio plugin source (GUI + DataModel dump command)
  mailbox/    local HTTP bridge that writes files / runs generators / opens browser (spec only)
  docs/         feasibility + prompt + conversion-playbook markdown
  working/      per-project I/O: dumps in, generated HTML out (sample TsunamiGame dumps included)
```

> Note: the loose files in the repo root (`AttributeTree.html`, `build_*.py`,
> etc.) are earlier flat copies that predate this structure. The canonical
> versions live in the folders above; the root copies are safe to delete.

## Generators

Four Python scripts (standard library only), all run from `generators/`:

- `build_attribute_tree.py` → `working/AttributeTree.html` (collapsible attribute tree)
- `build_valuebase_tree.py` → `working/ValueBaseTree.html` (collapsible Value tree)
- `build_network_diagram.py` → `working/NetworkDiagram.html` (per-service node-link)
- `build_value_network_diagram.py` → `working/ValueNetworkDiagram.html`

The valuebase + network generators import `build_attribute_tree.py` for shared
config and the render engine, so **keep all four in `generators/` together.**

## Configure & run

1. Put your Studio dumps in `working/` as `AttributeTree.luau` /
   `ValueBaseTree.luau` (the plugin/mailbox will automate this later).
2. Set `PROJECT_NAME` at the top of `generators/build_attribute_tree.py` (drives
   every page title; defaults to `"PROJECT_NAME"` and prints a reminder).
3. Point the runtime-marker scan at the analyzed game's Rojo source via the
   `ATTRTREE_SRC` env var:

   ```
   ATTRTREE_SRC=/path/to/YourGame/src python3 generators/build_attribute_tree.py
   ATTRTREE_SRC=/path/to/YourGame/src python3 generators/build_valuebase_tree.py
   ATTRTREE_SRC=/path/to/YourGame/src python3 generators/build_network_diagram.py
   ATTRTREE_SRC=/path/to/YourGame/src python3 generators/build_value_network_diagram.py
   ```

   (Defaults to `../../TsunamiGame/src` relative to the plugin if unset.)
4. Open the HTML in `working/`.

## Markers

Derived from the analyzed game's code on every run (never hand-mapped):
no mark = static/edit-time only; `*` = written in code; `**` = set to `nil` in
code. In the **value** HTMLs only, `***` flags an `ObjectValue` (holds an Instance
reference — cannot become an attribute).

## Docs (the handoff reading)

- `docs/PluginAutomation_Feasibility.md` — can this be one button? (yes, plugin +
  localhost mailbox) and exactly what each piece must do.
- `docs/NetworkDiagram_Prompt.md` — spec for regenerating a network diagram from scratch.
- `docs/ValueBaseAttributeConverter.md` — worked example of safely retiring
  Value objects (from TsunamiGame; use as a template).

## Roadmap

`plugin/` and `mailbox/` are stubs today. The intended end state (see the
feasibility doc): one button in Studio → dump → POST to localhost → mailbox
writes `working/*.luau`, runs the generators, opens the browser to the fresh
pages. The generators are already there and game-agnostic; what's left is the
plugin entry point and the small mailbox server.
