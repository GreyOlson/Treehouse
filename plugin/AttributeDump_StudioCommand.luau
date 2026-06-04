--[[
	ATTRIBUTE DUMP - Studio Command Bar script
	-------------------------------------------
	WHAT IT DOES:
	  Walks the entire live DataModel and finds every Instance that ALREADY has
	  one or more attributes set (i.e. design-time / Studio-authored attributes,
	  plus anything present at edit time). It prints an ASCII tree containing
	  ONLY the branches that lead to an attributed instance, and lists each
	  attribute as:  Name = value (type)

	HOW TO RUN:
	  1. Open your place in Roblox Studio.
	  2. View > Command Bar.
	  3. Paste this ENTIRE block and press Enter.
	  4. A Script named "ATTRIBUTE_DUMP_RESULT" appears under ServerStorage.
	     Open it, Select All, Copy, and paste the contents back to me.
	     (Writing to a Script.Source avoids the Output window truncating big dumps.)

	NOTES:
	  - Rojo tooling attributes "RojoSyncMode" and "PreserveParts" are dumped too
	    but flagged with [rojo] so we can ignore them.
	  - Run this on the INITIAL build (before play) so positions reflect the
	    authored studio layout.
--]]

local SERVICES = {
	"Workspace", "ReplicatedStorage", "ReplicatedFirst", "ServerStorage",
	"ServerScriptService", "StarterGui", "StarterPack", "StarterPlayer",
	"Lighting", "SoundService", "Players", "Teams", "Chat", "MaterialService",
}

local ROJO_ATTRS = { RojoSyncMode = true, PreserveParts = true }

-- format an attribute value + its type
local function fmt(v)
	local t = typeof(v)
	local ok, s = pcall(function() return tostring(v) end)
	if not ok then s = "<?>" end
	if t == "string" then s = '"' .. s .. '"' end
	return s, t
end

-- collect every instance that has attributes
local hits = {}            -- list of instances with >=1 attribute
local included = {}        -- set: instance -> true (hits + all their ancestors)

for _, svcName in ipairs(SERVICES) do
	local svc = game:FindFirstChild(svcName) or (pcall(function() return game:GetService(svcName) end) and game:GetService(svcName))
	if svc then
		local stack = { svc }
		while #stack > 0 do
			local inst = table.remove(stack)
			local ok, attrs = pcall(function() return inst:GetAttributes() end)
			if ok and attrs and next(attrs) ~= nil then
				table.insert(hits, inst)
				-- mark this node + every ancestor as included
				local node = inst
				while node and node ~= game do
					included[node] = true
					node = node.Parent
				end
			end
			local okc, children = pcall(function() return inst:GetChildren() end)
			if okc then
				for _, c in ipairs(children) do
					table.insert(stack, c)
				end
			end
		end
	end
end

-- build output tree
local lines = {}
local function emit(s) table.insert(lines, s) end

local function dumpAttributes(inst, indent)
	local attrs = inst:GetAttributes()
	-- stable alphabetical order
	local keys = {}
	for k in pairs(attrs) do table.insert(keys, k) end
	table.sort(keys)
	for _, k in ipairs(keys) do
		local valStr, valType = fmt(attrs[k])
		local flag = ROJO_ATTRS[k] and "  [rojo]" or ""
		emit(string.format("%s- %s = %s (%s)%s", indent, k, valStr, valType, flag))
	end
end

local function walk(inst, depth)
	local indent = string.rep("  ", depth)
	emit(string.format("%s%s [%s]", indent, inst.Name, inst.ClassName))
	-- attributes on this node
	local ok, attrs = pcall(function() return inst:GetAttributes() end)
	if ok and attrs and next(attrs) ~= nil then
		dumpAttributes(inst, indent .. "  ")
	end
	-- recurse only into included children, name-sorted for stable output
	local kids = {}
	for _, c in ipairs(inst:GetChildren()) do
		if included[c] then table.insert(kids, c) end
	end
	table.sort(kids, function(a, b)
		if a.Name == b.Name then return a.ClassName < b.ClassName end
		return a.Name < b.Name
	end)
	for _, c in ipairs(kids) do
		walk(c, depth + 1)
	end
end

emit("==== ATTRIBUTE DUMP (instances with attributes set at edit time) ====")
emit(string.format("Total attributed instances found: %d", #hits))
emit("Tree shows only branches leading to an attributed instance.")
emit("Format:  Name [ClassName]  then  - AttrName = value (type)")
emit("======================================================================")
emit("")

for _, svcName in ipairs(SERVICES) do
	local svc = game:FindFirstChild(svcName)
	if svc and included[svc] then
		walk(svc, 0)
		emit("")
	end
end

local out = table.concat(lines, "\n")

-- write to a Script.Source so it can be copied without Output truncation
local existing = game:GetService("ServerStorage"):FindFirstChild("ATTRIBUTE_DUMP_RESULT")
if existing then existing:Destroy() end
local s = Instance.new("Script")
s.Name = "ATTRIBUTE_DUMP_RESULT"
s.Source = out
s.Parent = game:GetService("ServerStorage")

print(string.format("[ATTRIBUTE_DUMP] Done. %d attributed instances. Open ServerStorage.ATTRIBUTE_DUMP_RESULT, copy its source, and send it back.", #hits))
