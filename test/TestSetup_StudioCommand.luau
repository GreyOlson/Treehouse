--[[
	TestSetup_StudioCommand.luau  - Studio Command Bar
	--------------------------------------------------
	Builds a tiny known dataset on an empty Baseplate so you can exercise the
	AttributeTreePlugin in isolation:

	  Workspace
	    TestPart [Part]
	      • attributes covering every attribute-supported type
	      • child ValueBase objects covering each Value class
	      • an ObjectValue (Target) to exercise the non-convertible *** flag
	      Nested [Folder]
	        DeepValue [IntValue]   -> tests ancestor path / compression

	Re-runnable (replaces an existing TestPart). Read-only-safe aside from the
	TestPart it owns. Undo with Ctrl+Z.

	Usage: File → New → Baseplate, then View → Command Bar, paste, Enter.
--]]

local Workspace = game:GetService("Workspace")

local old = Workspace:FindFirstChild("TestPart")
if old then old:Destroy() end

local part = Instance.new("Part")
part.Name = "TestPart"
part.Anchored = true
part.Size = Vector3.new(4, 4, 4)
part.Position = Vector3.new(0, 5, 0)
part.BrickColor = BrickColor.new("Bright blue")
part.Parent = Workspace

-- attributes (one of each attribute-supported type)
part:SetAttribute("TestString", "hello")
part:SetAttribute("TestNumber", 42)
part:SetAttribute("TestBool", true)
part:SetAttribute("TestVector3", Vector3.new(1, 2, 3))
part:SetAttribute("TestCFrame", CFrame.new(0, 5, 0))
part:SetAttribute("TestColor3", Color3.fromRGB(255, 128, 0))
part:SetAttribute("TestBrickColor", BrickColor.new("Bright red"))
part:SetAttribute("TestNumberRange", NumberRange.new(1, 5))

-- child ValueBase objects (one of each class the dumps care about)
local function val(class: string, name: string, value: any)
	local v = Instance.new(class)
	v.Name = name
	if value ~= nil then
		(v :: any).Value = value
	end
	v.Parent = part
	return v
end

val("IntValue", "Health", 100)
val("NumberValue", "Speed", 16.5)
val("StringValue", "Label", "TestLabel")
val("BoolValue", "Active", true)
val("Vector3Value", "Origin", Vector3.new(0, 10, 0))
val("CFrameValue", "Preset", CFrame.new(1, 2, 3))
val("Color3Value", "Tint", Color3.fromRGB(10, 20, 30))
val("ObjectValue", "Target", nil) -- stays nil -> should render *** (non-convertible)

-- nested folder + value (tests ancestor path / network path-compression)
local nested = Instance.new("Folder")
nested.Name = "Nested"
nested.Parent = part
local deep = Instance.new("IntValue")
deep.Name = "DeepValue"
deep.Value = 7
deep.Parent = nested

print("[TestSetup] Built Workspace.TestPart with 8 attributes, 8 child Values, and Nested.DeepValue.")
