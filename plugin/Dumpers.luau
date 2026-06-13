--[[
	Dumpers.luau  (ModuleScript)
	---------------------------
	Read-only DataModel walkers that return the exact text formats the Python
	generators parse:
	  • Dumpers.AttributeDump()  -> attribute dump string
	  • Dumpers.ValueBaseDump()  -> ValueBase dump string
	No instances are modified. Used by the plugin; can also be called from the
	Command Bar: print(require(path).AttributeDump())
--]]

local Dumpers = {}

local SERVICES = {
	"Workspace", "ReplicatedStorage", "ReplicatedFirst", "ServerStorage",
	"ServerScriptService", "StarterGui", "StarterPack", "StarterPlayer",
	"Lighting", "SoundService", "Players", "Teams", "Chat", "MaterialService",
}

-- value + its type label, matching the dumps: `value (type)`
local function fmt(v): (string, string)
	if v == nil then
		return "nil", "nil"
	end
	local t = typeof(v)
	if t == "string" then
		return '"' .. v .. '"', "string"
	elseif t == "Instance" then
		return v:GetFullName(), "Instance"
	end
	local ok, s = pcall(tostring, v)
	return (ok and s or "<?>"), t
end

local function services(): { Instance }
	local out = {}
	for _, name in ipairs(SERVICES) do
		local svc = game:FindFirstChild(name)
		if not svc then
			local ok, s = pcall(function() return game:GetService(name) end)
			if ok then svc = s end
		end
		if svc then
			table.insert(out, svc)
		end
	end
	return out
end

local function sortKids(a: Instance, b: Instance): boolean
	if a.Name == b.Name then
		return a.ClassName < b.ClassName
	end
	return a.Name < b.Name
end

-- mark `inst` and all ancestors (up to, not including, game) as included
local function include(set: { [Instance]: boolean }, inst: Instance)
	local node = inst
	while node and node ~= game do
		set[node] = true
		node = node.Parent
	end
end

----------------------------------------------------------------------
function Dumpers.AttributeDump(): string
	local included: { [Instance]: boolean } = {}
	local count = 0
	for _, svc in ipairs(services()) do
		local stack = { svc }
		while #stack > 0 do
			local inst = table.remove(stack)
			local ok, attrs = pcall(function() return inst:GetAttributes() end)
			if ok and attrs and next(attrs) ~= nil then
				count += 1
				include(included, inst)
			end
			local okc, kids = pcall(function() return inst:GetChildren() end)
			if okc then
				for _, c in ipairs(kids) do
					stack[#stack + 1] = c
				end
			end
		end
	end

	local lines = {}
	local function emit(s) lines[#lines + 1] = s end
	emit("==== ATTRIBUTE DUMP ====")
	emit("Total attributed instances found: " .. count)
	emit(string.rep("=", 70))
	emit("")

	local function walk(inst: Instance, depth: number)
		local indent = string.rep("  ", depth)
		emit(indent .. inst.Name .. " [" .. inst.ClassName .. "]")
		local attrs = inst:GetAttributes()
		if next(attrs) ~= nil then
			local keys = {}
			for k in pairs(attrs) do keys[#keys + 1] = k end
			table.sort(keys)
			for _, k in ipairs(keys) do
				local vs, vt = fmt(attrs[k])
				emit(indent .. "  - " .. k .. " = " .. vs .. " (" .. vt .. ")")
			end
		end
		local kids = {}
		for _, c in ipairs(inst:GetChildren()) do
			if included[c] then kids[#kids + 1] = c end
		end
		table.sort(kids, sortKids)
		for _, c in ipairs(kids) do walk(c, depth + 1) end
	end

	for _, svc in ipairs(services()) do
		if included[svc] then walk(svc, 0); emit("") end
	end
	return table.concat(lines, "\n")
end

----------------------------------------------------------------------
function Dumpers.ValueBaseDump(): string
	local included: { [Instance]: boolean } = {}
	local count = 0
	for _, svc in ipairs(services()) do
		local stack = { svc }
		while #stack > 0 do
			local inst = table.remove(stack)
			if inst:IsA("ValueBase") then
				count += 1
				include(included, inst)
			end
			local okc, kids = pcall(function() return inst:GetChildren() end)
			if okc then
				for _, c in ipairs(kids) do
					stack[#stack + 1] = c
				end
			end
		end
	end

	local lines = {}
	local function emit(s) lines[#lines + 1] = s end
	emit("==== VALUEBASE DUMP (every IntValue/StringValue/ObjectValue/etc.) ====")
	emit("Total ValueBase objects found: " .. count)
	emit("Each Value is a node:  Name [ClassName] = value (type)")
	emit("The Name is your codebase-search token.")
	emit(string.rep("=", 70))
	emit("")

	local function walk(inst: Instance, depth: number)
		local indent = string.rep("  ", depth)
		local line = indent .. inst.Name .. " [" .. inst.ClassName .. "]"
		if inst:IsA("ValueBase") then
			local vs, vt = fmt((inst :: any).Value)
			line = line .. " = " .. vs .. " (" .. vt .. ")"
		end
		emit(line)
		local kids = {}
		for _, c in ipairs(inst:GetChildren()) do
			if included[c] then kids[#kids + 1] = c end
		end
		table.sort(kids, sortKids)
		for _, c in ipairs(kids) do walk(c, depth + 1) end
	end

	for _, svc in ipairs(services()) do
		if included[svc] then walk(svc, 0); emit("") end
	end
	return table.concat(lines, "\n")
end

----------------------------------------------------------------------
-- Collision: a part is "flagged" if any collision setting is non-default.
-- Returns the offending {name, value} pairs (in a stable order) or nil.
local function collisionFlags(inst: Instance): { { any } }?
	if not inst:IsA("BasePart") then
		return nil
	end
	local flags = {}
	-- CanCollide / CanTouch are always present on BasePart; the rest may not exist
	-- on every part type, so read them through pcall and skip if absent.
	if inst.CanCollide == false then flags[#flags + 1] = { "CanCollide", false } end
	if inst.CanTouch == false then flags[#flags + 1] = { "CanTouch", false } end
	if inst.CanQuery == false then flags[#flags + 1] = { "CanQuery", false } end
	local okA, audio = pcall(function() return (inst :: any).AudioCanCollide end)
	if okA and audio == false then flags[#flags + 1] = { "AudioCanCollide", false } end
	local okG, group = pcall(function() return inst.CollisionGroup end)
	if okG and group ~= "Default" then flags[#flags + 1] = { "CollisionGroup", group } end
	local okF, fidelity = pcall(function() return (inst :: any).CollisionFidelity end)
	if okF and fidelity ~= Enum.CollisionFidelity.Default then
		flags[#flags + 1] = { "CollisionFidelity", fidelity }
	end
	if #flags == 0 then
		return nil
	end
	return flags
end

function Dumpers.CollisionDump(): string
	local included: { [Instance]: boolean } = {}
	local flagsOf: { [Instance]: { { any } } } = {}
	local count = 0
	for _, svc in ipairs(services()) do
		local stack = { svc }
		while #stack > 0 do
			local inst = table.remove(stack)
			local flags = collisionFlags(inst)
			if flags then
				count += 1
				flagsOf[inst] = flags
				include(included, inst)
			end
			local okc, kids = pcall(function() return inst:GetChildren() end)
			if okc then
				for _, c in ipairs(kids) do
					stack[#stack + 1] = c
				end
			end
		end
	end

	local lines = {}
	local function emit(s) lines[#lines + 1] = s end
	emit("==== COLLISION DUMP (parts with non-default collision settings) ====")
	emit("Total flagged parts found: " .. count)
	emit("CanCollide/CanTouch/AudioCanCollide=false, CollisionGroup or CollisionFidelity != Default.")
	emit(string.rep("=", 70))
	emit("")

	local function walk(inst: Instance, depth: number)
		local indent = string.rep("  ", depth)
		emit(indent .. inst.Name .. " [" .. inst.ClassName .. "]")
		local flags = flagsOf[inst]
		if flags then
			for _, fl in ipairs(flags) do
				local vs, vt = fmt(fl[2])
				emit(indent .. "  - " .. fl[1] .. " = " .. vs .. " (" .. vt .. ")")
			end
		end
		local kids = {}
		for _, c in ipairs(inst:GetChildren()) do
			if included[c] then kids[#kids + 1] = c end
		end
		table.sort(kids, sortKids)
		for _, c in ipairs(kids) do walk(c, depth + 1) end
	end

	for _, svc in ipairs(services()) do
		if included[svc] then walk(svc, 0); emit("") end
	end
	return table.concat(lines, "\n")
end

return Dumpers
