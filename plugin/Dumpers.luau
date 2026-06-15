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

----------------------------------------------------------------------
-- Ownership: uploaded assets (MeshParts, Sounds, Animations, Decals/Textures, ...)
-- and who created them. MarketplaceService:GetProductInfo gives the asset's Creator
-- (a User or a Group); we cache it per asset id so each unique asset is fetched once.
local MarketplaceService = game:GetService("MarketplaceService")

-- The asset-bearing properties we read, per instance type. (Start set; easy to extend.)
local function assetRefs(inst: Instance, classes: { [string]: boolean }?): { { string } }
	-- classes: { mesh, sound, image } picks which asset categories to scan; nil = all.
	-- Animations ride on the "all" case (no dedicated checkbox).
	local function want(cat: string): boolean
		return classes == nil or classes[cat] == true
	end
	local refs = {}
	local function add(prop: string)
		local ok, v = pcall(function() return (inst :: any)[prop] end)
		if ok and type(v) == "string" and v ~= "" then refs[#refs + 1] = { prop, v } end
	end
	if inst:IsA("MeshPart") then
		if want("mesh") then add("MeshId") end
		if want("image") then add("TextureID") end
	elseif inst:IsA("SpecialMesh") then
		if want("mesh") then add("MeshId") end
		if want("image") then add("TextureId") end
	elseif inst:IsA("Sound") then
		if want("sound") then add("SoundId") end
	elseif inst:IsA("Animation") then
		if classes == nil then add("AnimationId") end
	elseif inst:IsA("Decal") then
		if want("image") then add("Texture") end   -- Texture is a subclass of Decal
	end
	return refs
end

-- Pull the numeric asset id out of a content string. rbxasset:// (built-in) has no
-- creator, so it's skipped.
local function assetIdFrom(content: string): number?
	if type(content) ~= "string" or content == "" then return nil end
	if string.find(content, "rbxasset://", 1, true) then return nil end
	local id = string.match(content, "id=(%d+)")
		or string.match(content, "rbxassetid://(%d+)")
		or string.match(content, "(%d+)")
	return id and tonumber(id) or nil
end

local creatorCache: { [number]: { name: string, typ: string } } = {}
local lookups = 0
local function creatorOf(assetId: number): { name: string, typ: string }
	local cached = creatorCache[assetId]
	if cached then return cached end
	lookups += 1
	if lookups % 25 == 0 then task.wait() end -- gentle throttle so GetProductInfo isn't spammed
	local res = { name = "unknown", typ = "Unknown" }
	local ok, info = pcall(function()
		return MarketplaceService:GetProductInfo(assetId, Enum.InfoType.Asset)
	end)
	if ok and info and info.Creator then
		res.name = tostring(info.Creator.Name or "unknown")
		local ct = info.Creator.CreatorType
		if typeof(ct) == "EnumItem" then ct = ct.Name end
		res.typ = tostring(ct or "Unknown") -- "User" or "Group"
	end
	-- keep the dump line parseable: name is the value, "(typ)" is the type token
	res.name = (res.name:gsub("[%(%)\r\n]", "")):gsub("%s+", " ")
	creatorCache[assetId] = res
	return res
end

function Dumpers.OwnershipDump(progress: ((number, number) -> ())?, classes: { [string]: boolean }?): string
	-- pass 1: collect asset-bearing instances + the set of unique asset ids (no API yet)
	local found: { { any } } = {} -- { inst, refs }
	local uniq: { [number]: boolean } = {}
	local uniqCount = 0
	for _, svc in ipairs(services()) do
		local stack = { svc }
		while #stack > 0 do
			local inst = table.remove(stack)
			local refs = assetRefs(inst, classes)
			if #refs > 0 then
				found[#found + 1] = { inst, refs }
				for _, r in ipairs(refs) do
					local id = assetIdFrom(r[2])
					if id and not uniq[id] then uniq[id] = true; uniqCount += 1 end
				end
			end
			local okc, kids = pcall(function() return inst:GetChildren() end)
			if okc then
				for _, c in ipairs(kids) do stack[#stack + 1] = c end
			end
		end
	end

	-- pass 2: resolve each unique creator (cached), reporting progress so the plugin can
	-- show a live "X / Y" counter (the catalog lookups are the slow part).
	local done = 0
	for id in pairs(uniq) do
		creatorOf(id)
		done += 1
		if progress and (done % 5 == 0 or done == uniqCount) then
			progress(done, uniqCount)
			task.wait() -- repaint the counter
		end
	end

	-- pass 3: stitch the cached creators onto each host instance
	local included: { [Instance]: boolean } = {}
	local ownOf: { [Instance]: { { string } } } = {} -- inst -> { {prop, creatorName, creatorType}, ... }
	local count = 0
	for _, entry in ipairs(found) do
		local inst, refs = entry[1], entry[2]
		local out = {}
		for _, r in ipairs(refs) do
			local id = assetIdFrom(r[2])
			local cr = id and creatorCache[id]
			if cr then out[#out + 1] = { r[1], cr.name, cr.typ } end
		end
		if #out > 0 then
			ownOf[inst] = out
			count += 1
			include(included, inst)
		end
	end

	local lines = {}
	local function emit(s) lines[#lines + 1] = s end
	emit("==== OWNERSHIP DUMP (uploaded assets + their creator) ====")
	emit("Total asset-bearing instances found: " .. count .. " | unique assets: " .. uniqCount)
	emit("Each row:  - <Property> = <CreatorName> (User|Group)")
	emit(string.rep("=", 70))
	emit("")

	local function walk(inst: Instance, depth: number)
		local indent = string.rep("  ", depth)
		emit(indent .. inst.Name .. " [" .. inst.ClassName .. "]")
		local own = ownOf[inst]
		if own then
			for _, o in ipairs(own) do
				emit(indent .. "  - " .. o[1] .. " = " .. o[2] .. " (" .. o[3] .. ")")
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
