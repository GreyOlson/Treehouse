# ValueBase → Attribute Converter

A working plan for retiring legacy `*Value` objects in favor of attributes.
Every command below is a **Studio Command Bar** Luau one-off (View → Command Bar,
paste, Enter). Each prints a count and is undoable with Ctrl+Z. Run them on the
initial build, not in Play mode. Findings here were confirmed by searching `src/`.

## Conversion rules (what can and can't move)

Roblox attributes support: string, boolean, number, Vector3, CFrame, Color3,
BrickColor, Vector2, UDim/UDim2, NumberRange, NumberSequence, ColorSequence, Rect,
Font. So `IntValue / NumberValue / StringValue / BoolValue / Vector3Value /
CFrameValue / Color3Value / BrickColorValue` all convert cleanly.

**Attributes CANNOT store an `Instance` reference.** That makes **`ObjectValue`
NON-CONVERTIBLE** (see item 4). These must stay as objects, or be re-modeled (e.g.
store the target's name/UserId in a string/number attribute instead of the
instance itself).

General convert pattern: `inst:SetAttribute(Name, valueObject.Value)` then
`valueObject:Destroy()` — but only after any code that reads the object is updated
to `GetAttribute`.

---

## 1) Remove `OriginalPosition` / `OriginalSize` spam — SAFE TO DELETE ✅

**Finding.** 902 `OriginalPosition` + 339 `OriginalSize` = **1,241 Vector3Values**
(that's every Vector3Value in the game, ~39% of all 3,207 values). They sit on
character-rig Attachments/MeshParts inside dummy/NPC/easter-egg models — the
standard scale-cache left behind by avatar resizing.

**Safety — confirmed.** Nothing in `src/` reads them as Value objects: zero
`.Value`, `FindFirstChild("OriginalPosition")`, or `WaitForChild` hits. The only
`OriginalSize` in code is an unrelated Lua table field in
`ServerToolDefinitions/ChessArmoredGear` that reads `Handle.Size` directly. For
static NPCs that never scale or move, these objects do nothing. **Deleting them
cannot error anything.**

**Command (ready):**
```lua
-- SAFE: no code reads OriginalPosition/OriginalSize as Value objects.
local removed = 0
for _, svcName in ipairs({"Workspace","ServerStorage","ReplicatedStorage","StarterPlayer","StarterGui"}) do
	local svc = game:FindFirstChild(svcName)
	if svc then
		for _, v in ipairs(svc:GetDescendants()) do
			if v:IsA("Vector3Value") and (v.Name == "OriginalPosition" or v.Name == "OriginalSize") then
				v:Destroy(); removed += 1
			end
		end
	end
end
print(("[Cleanup] Removed %d OriginalPosition/OriginalSize Vector3Values"):format(removed))
```

**Optional extra caution** — if you'd rather only remove ones inside a Humanoid
model, gate the destroy on `v:FindFirstAncestorWhichIsA("Model")` having a
`Humanoid`. Not necessary (nothing reads them), but available.

---

## 2) `GoldBar.Tag` (IntValue) — renumber, then convert to attribute

**Finding.** 68 `GoldBar` collectibles each carry a `Tag` IntValue. The Tag is a
**unique per-bar id**: the client keys the collect-cooldown on `Gold {tag}` and
fires `GoldCollectClaim:FireServer(tag)`; the region loader finds a bar by
`Tag.Value == tonumber(tag)`. Map1's are uniquely numbered; **Map2's are all 22**,
which means collecting one Map2 bar marks every Map2 bar collected (shared
cooldown key). The cooldown folder is created per session on the Player and is
Debris-cleared — **tags are not persisted to any DataStore**, so renumbering is
safe.

### 2a) Re-iterate the tags so every bar is unique (fixes the all-22 bug)
```lua
-- Tags must be globally unique; cooldown keys on `Gold{tag}`. Not persisted, safe to renumber.
local n = 0
for _, v in ipairs(workspace:GetDescendants()) do
	if v.Name == "GoldBar" and v:IsA("BasePart") then
		local tag = v:FindFirstChild("Tag")
		if not tag then tag = Instance.new("IntValue"); tag.Name = "Tag"; tag.Parent = v end
		n += 1
		tag.Value = n
	end
end
print(("[GoldBar] Renumbered %d tags 1..%d (all unique)"):format(n, n))
```

### 2b) Convert `Tag` → attribute (run after 2a)
```lua
local n = 0
for _, v in ipairs(workspace:GetDescendants()) do
	if v.Name == "GoldBar" and v:IsA("BasePart") then
		local tag = v:FindFirstChild("Tag")
		if tag and tag:IsA("IntValue") then
			v:SetAttribute("Tag", tag.Value); tag:Destroy(); n += 1
		end
	end
end
print(("[GoldBar] Converted %d Tag IntValues -> attribute"):format(n))
```

### 2b-2) Rename the attribute `Tag` -> `GoldDebounce` (the final name in code)
```lua
local n = 0
for _, v in ipairs(workspace:GetDescendants()) do
	if v.Name == "GoldBar" and v:IsA("BasePart") then
		local val = v:GetAttribute("Tag")
		if val ~= nil then
			v:SetAttribute("GoldDebounce", val); v:SetAttribute("Tag", nil); n += 1
		end
	end
end
print(("[GoldBar] Renamed Tag -> GoldDebounce on %d bars"):format(n))
```

### 2c) Required code changes (DONE in source — attribute read as `GoldDebounce`)
- `StarterPlayer/StarterCharacterScripts/LocalTouchManager/AnythingTouchLocal.luau`
  (~line 235): replace
  ```lua
  local tag = hit:FindFirstChild("Tag")
  if tag then
      if GoldCoolDownFolder:FindFirstChild(`Gold {tag.Value}`) == nil then
          ...
          RemoteEvents.Economy.GoldCollectClaim:FireServer(tag.Value)
  ```
  with `local tag = hit:GetAttribute("GoldDebounce")`, then use `tag` directly
  (drop `.Value`): `Gold {tag}` and `FireServer(tag)`.
- `StarterPlayer/StarterPlayerScripts/MapRegionsLoadingLocal.client.luau`
  (lines 84 and 97): replace
  `gc[i]:FindFirstChild("Tag") and gc[i].Tag.Value == tonumber(tag)` with
  `gc[i]:GetAttribute("Tag") == tonumber(tag)`.
- `ServerStorage/Gear_Storage/UFO2/UFOMinerLocal.client.luau` (~line 46): the UFO
  miner also collects GoldBars — replace `local tag = v:FindFirstChild("Tag")` with
  `local tag = v:GetAttribute("Tag")` and drop the two `.Value` / `..tag.Value`
  usages below it (use `tag` directly).
- Server `Map1/BlackMarketScript/init.server.luau` (~line 980): the handler
  already receives `tag` as a plain number — **no change needed**.

> All four edits above are DONE in the source.

---

## 3) `RedPart` — `PresetCFrame` (CFrameValue) & `Rock` (BoolValue) → attributes

**Finding.**
- **`PresetCFrame` is already an attribute at runtime.**
  `Game/Minigames/MinigameUtil.luau` does
  `RedPart:SetAttribute("PresetCFrame", RedPart.CFrame)` in `InitRedParts()` and
  reads it back via `GetAttribute("PresetCFrame")`. The 72 `PresetCFrame`
  CFrameValue objects are **redundant/dead** — no code reads the object. Just
  delete them (do not seed a design-time attribute; the minigame overwrites it
  from `.CFrame` on init).
- **`Rock` (BoolValue, 49 of them) is read by no code** (the `"Rock"` in code is a
  CollectionService *tag*, unrelated). Convert to a boolean attribute.

**Command (ready, scoped to the RedPart family by name):**
```lua
local pc, rk = 0, 0
for _, v in ipairs(workspace:GetDescendants()) do
	if v:IsA("BasePart") and string.find(v.Name, "RedPart") then
		local preset = v:FindFirstChild("PresetCFrame")
		if preset and preset:IsA("CFrameValue") then preset:Destroy(); pc += 1 end
		local rock = v:FindFirstChild("Rock")
		if rock and rock:IsA("BoolValue") then v:SetAttribute("Rock", rock.Value); rock:Destroy(); rk += 1 end
	end
end
print(("[RedPart] Removed %d redundant PresetCFrame, converted %d Rock -> attribute"):format(pc, rk))
```
No code changes needed (PresetCFrame already uses the attribute; nothing reads
`Rock`). If you also want the PresetCFrame CFrameValues that live outside
RedPart-named parts gone, widen the scope — they're all redundant for the same
reason.

---

## 4) ⚠️ `ObjectValue` — CANNOT be converted to an attribute

**This is a hard constraint, called out here and surfaced in the Value HTMLs
only.** 27 `ObjectValue`s exist (e.g. `Occupant` on seats, all `nil`). An
`ObjectValue` holds an **Instance reference**, and attributes cannot store
Instances — so there is no direct conversion. Options if you want them gone:
- Leave them as `ObjectValue` (they're a small count).
- Re-model: store the referenced instance's **name** (string) or owner **UserId**
  (number) in an attribute instead of the instance pointer, and update the code
  that reads `.Value` accordingly.

In `ValueBaseTree.html` and `ValueNetworkDiagram.html`, non-convertible value
types are flagged with a red **`***`** after the type and an entry in the legend
key: *“`***` = stores an Instance ref — cannot become an attribute.”* This marker
appears **only** in the value-object HTMLs, never in the attribute maps.

---

## 5) `Rotation` (IntValue) → attribute

**Finding.** 40 `Rotation` IntValues (all `0`), on the `*RedPart` obstacle
variants. No code reads `Rotation` as a Value object (`.Value` /
`FindFirstChild("Rotation")` / `WaitForChild` → none; the `Rotation` references in
code are GUI `.Rotation` properties, unrelated). Safe to convert.

**Command (ready):**
```lua
local n = 0
for _, v in ipairs(workspace:GetDescendants()) do
	local rot = v:FindFirstChild("Rotation")
	if rot and rot:IsA("IntValue") then
		v:SetAttribute("Rotation", rot.Value); rot:Destroy(); n += 1
	end
end
print(("[Rotation] Converted %d Rotation IntValues -> attribute"):format(n))
```

---

## Expected impact after items 1–5

| Item | Values handled | Action |
|------|----------------|--------|
| 1 OriginalPosition/OriginalSize | 1,241 | deleted |
| 2 GoldBar Tag | 68 | renumbered + → attribute |
| 3 PresetCFrame / Rock | 72 + 49 | deleted / → attribute |
| 5 Rotation | 40 | → attribute |
| 4 ObjectValue | 27 | **stay (non-convertible)** |

That clears roughly **1,470 of 3,207** Value objects (~46%). Re-run the dump and
`build_valuebase_tree.py` afterward to see the updated map.

> Order of operations: do item 1 first (biggest, zero-risk). For item 2, run 2a →
> 2b → 2c together. Re-dump and regenerate the HTMLs when done.
