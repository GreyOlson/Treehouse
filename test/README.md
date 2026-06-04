# test/ — exercising the plugin on a baseplate

Two Rojo project files exist, for two different jobs:

- `../default.project.json` (repo root) — **dev place**. `rojo serve` from the
  repo root syncs `Dumpers` + `AttributeToolGui` into
  `ServerScriptService.AttributeTreeTool` of an open place, so you can test the
  dump → generate pipeline from the Command Bar without installing a plugin.
- `../plugin/default.project.json` — **builds the installable plugin**
  (`rojo build plugin -o AttributeTreeTool.rbxmx`).

## Quick test loop (dev place)

1. Studio → File → New → **Baseplate**.
2. From the repo root: `rojo serve` → in Studio open the Rojo plugin → **Connect**.
   You'll see `ServerScriptService.AttributeTreeTool.Dumpers` appear.
3. View → Command Bar → paste `test/TestSetup_StudioCommand.luau` → Enter. This
   builds `Workspace.TestPart` with attributes of every type, a child of every
   ValueBase class, an `ObjectValue` (for the `***` flag), and `Nested.DeepValue`.
4. Still in the Command Bar, generate a dump string, e.g.:
   ```lua
   print(require(game.ServerScriptService.AttributeTreeTool.Dumpers).ValueBaseDump())
   ```
   or paste that output into `working/ValueBaseTree.luau` and run the generators.

## Full plugin loop (real toolbar button)

1. `rojo build plugin -o AttributeTreeTool.rbxmx`, then install it as a local
   plugin (drag into Studio → right-click → Save as Local Plugin, or drop the
   file in the Plugins folder).
2. On the baseplate, run `test/TestSetup_StudioCommand.luau` to create the part.
3. Start the mailbox (no game source needed for a baseplate — markers will all
   be "static"): `python3 mailbox/server.py`
4. Game Settings → Security → **Allow HTTP Requests** on.
5. Toolbar → Attribute Tool → click **Generate ValueBase Tree**. The browser
   opens `working/ValueBaseTree.html` + `working/ValueNetworkDiagram.html` showing
   just `TestPart`'s values — `Target [ObjectValue]` should carry the red `***`.

## What the test part proves

- Every attribute type round-trips through the dump + tree.
- Each ValueBase class renders with the right `(type)`.
- `ObjectValue` shows the non-convertible `***` flag (value HTMLs only).
- `Nested.DeepValue` confirms ancestor paths and network path-compression on a
  trivially small tree.
