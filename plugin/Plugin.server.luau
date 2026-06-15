--[[
	Plugin.server.luau  (plugin entry point)
	----------------------------------------
	Toolbar button -> dock widget with the AttributeToolGui. The two buttons walk
	the DataModel (Dumpers) and POST the dump to the local mailbox server, which
	writes the .luau, runs the generators, and opens the browser.

	Requires: Studio "Allow HTTP Requests" enabled, and the mailbox running
	(see ../mailbox/). All traffic is localhost-only.
--]]

local HttpService = game:GetService("HttpService")

local Gui = require(script.AttributeToolGui)
local Dumpers = require(script.Dumpers)

-- where the local mailbox listens
local MAILBOX = "http://localhost:8787"

-- The open place's name (same value the GUI titles itself with). Sent with each
-- dump so the generated HTML pages are titled with the real place name.
local function getPlaceName(): string
	local ok, info = pcall(function()
		return game:GetService("MarketplaceService"):GetProductInfo(game.PlaceId)
	end)
	if ok and typeof(info) == "table" and info.Name and #info.Name > 0 then
		return info.Name
	end
	return game.Name
end
local PROJECT = getPlaceName()

local toolbar = plugin:CreateToolbar("Treehouse")
local button = toolbar:CreateButton(
	"Attribute Explorer",
	"Treehouse: Attribute Explorer (Search Manager)",
	"rbxassetid://126503186724852" -- shared across both tiers
)
button.ClickableWhenViewportHidden = true

local widgetInfo = DockWidgetPluginGuiInfo.new(
	Enum.InitialDockState.Float,
	false, -- start disabled (closed)
	true,  -- OVERRIDE the restored state so it never auto-opens on launch
	460, 560, -- default size
	380, 420  -- min size
)
local widget = plugin:CreateDockWidgetPluginGui("TreehouseAttributeExplorer", widgetInfo)
widget.Name = "Treehouse"
widget.Title = "Treehouse - Attribute Explorer"

local HTTP_WARNING =
	"HTTP requests are disabled. Turn on File → Experience Settings → "
	.. "Security → Allow HTTP Requests, then click again."

-- Whether the "Include Runtime in Treehouse" toggle is on (driven by the GUI).
local includeRuntime = false
local hasPython = true   -- GUI "I have Python installed" toggle; if false, use uv
local mailboxUp = false  -- set true when an open-time ping reaches the mailbox
local srcConnected = false -- "project src connected" toggle (auto from /health, or manual)
local srcPath = ""        -- the TREE_SRC the mailbox reported, if any
local srcRelevant = true  -- attribute / value* use src; geometry / ownership don't (GUI sets this)
local ui                 -- GUI handle (assigned after Gui.build below)

-- The all-in-one terminal command shown in the GUI boxes: cd into the Treehouse
-- folder and run the mailbox. Switches python <-> uv (the hasPython toggle), and
-- when runtime is included it also sets TREE_SRC up front (edit the placeholder
-- path) so the whole thing is one copy-paste.
local function commandsFor(): (string, string)
	local runner = hasPython and "python3" or "uv run"
	local winRunner = hasPython and "python" or "uv run"
	local macSrc = (includeRuntime and srcRelevant) and 'TREE_SRC="/path/to/YourProject/src" ' or ""
	local winSrc = (includeRuntime and srcRelevant) and 'set "TREE_SRC=C:\\path\\YourProject\\src" && ' or ""
	local mac = "cd ~/Treehouse && " .. macSrc .. runner .. " mailbox/server.py"
	local win = 'cd /d "%USERPROFILE%\\Treehouse" && ' .. winSrc .. winRunner .. " mailbox\\server.py"
	return mac, win
end

-- Build the setup text. Steps are numbered dynamically: if "Allow HTTP Requests"
-- is already enabled, step 1 is skipped and the rest shift down a number. The
-- optional runtime step is always LAST, shown with ✅ when the toggle is on and
-- ❌ (with a hint) when off.
local function buildSetup(): string
	local httpOn = false
	pcall(function() httpOn = HttpService.HttpEnabled end)

	local out = {}
	local function add(s: string) out[#out + 1] = s end
	local n = 0
	local function step(body: string)
		n += 1
		add(n .. ". " .. body)
		add("")
	end

	add("SETUP - Treehouse needs a mailbox running to build the HTML.")
	add("")
	add("The mailbox is a small program that picks up the 'mail' your Roblox place")
	add("sends - its attribute / value hierarchy - and turns it into the HTML. It")
	add("always runs at " .. MAILBOX .. ", and the plugin talks to it there - so you")
	add("never choose where to connect. You just start it once.")
	add("")

	if httpOn then
		add("✅ HTTP requests enabled.")
		add("")
	else
		step("In Studio, enable: File → Experience Settings → Security →\n"
			.. "   Allow HTTP Requests.  (the easy one)")
	end

	if not hasPython then
		step("No Python? Install uv once - it runs Treehouse and fetches Python\n"
			.. "   for you (nothing else to install). See https://astral.sh/uv :\n"
			.. "      macOS:    curl -LsSf https://astral.sh/uv/install.sh | sh\n"
			.. "      Windows:  (in PowerShell) irm https://astral.sh/uv/install.ps1 | iex")
	end
	step("Open the Treehouse folder you downloaded and double-click the launcher:\n"
		.. "      macOS:    Start Treehouse (Mac).command\n"
		.. "      Windows:  Start Treehouse (Windows).bat\n"
		.. "   (It finds itself, so the folder can live anywhere - no path needed.)\n"
		.. "   macOS may block it the first time: right-click the file -> Open -> Open.")
	step("A window opens and prints  Treehouse listening on " .. MAILBOX .. "  -\n"
		.. "   leave it open, then click a Generate button above. Nothing leaves\n"
		.. "   your machine.")

	add("Prefer the terminal, or the launcher won't run? Use the command for your")
	add("system in the boxes below (they assume the folder is in your home folder,")
	add("named Treehouse - or edit the path to wherever you put it).")

	return table.concat(out, "\n")
end

-- The "Include Runtime in Treehouse" section. Rendered LAST and ALWAYS (whether
-- the mailbox is up or not), so toggling the checkbox always changes what's on
-- screen. ✅ shows the full src-connection steps; ❌ shows a short hint.
-- Short runtime status, shown ABOVE the command boxes. The actual src-setting now
-- lives inside the copy-paste command (TREE_SRC=...), so this is just a status line.
local function runtimeBlock(): string
	if not includeRuntime then
		return "❌ Runtime in Treehouse - not included\n"
			.. 'Tick "Include Runtime in Treehouse" above to also capture runtime states.'
	end
	if srcConnected then
		return "✅ Runtime INCLUDED - project src connected"
			.. (srcPath ~= "" and ("  (" .. srcPath .. ")") or "") .. "\n"
			.. "The * (set in code) and ** markers will fill in from your code."
	end
	return "✅ Runtime INCLUDED - edit the src path in the command below, then run it.\n"
		.. "Point TREE_SRC at your game's synced source folder (a Rojo src/, etc.).\n"
		.. "No synced code? Skip it - everything still works, the * / ** markers just won't show."
end

-- Ping the mailbox's health endpoint. Returns (up, srcPath): up=true if it
-- answered (mailbox + Python are running); srcPath is the TREE_SRC it reported
-- (empty when none). False/"" on connect-fail or if HTTP is disabled.
local function pingMailbox(): (boolean, string)
	local ok, body = pcall(function()
		return HttpService:GetAsync(MAILBOX .. "/health", true) -- nocache: fresh check
	end)
	if not ok then
		return false, ""
	end
	local detected = tostring(body):match("src=([^\r\n]*)") or ""
	return true, detected
end

-- The idle status text: a short "already running" note when the mailbox
-- answered the ping, otherwise the full setup guide.
local function currentGuide(): string
	if mailboxUp then
		return "✅ Mailbox already running on " .. MAILBOX .. ".\n"
			.. "Click a Generate button above to build the HTML."
	end
	return buildSetup()
end

-- Re-check whether the mailbox is up, then refresh the guide, runtime note, and
-- the OS command boxes. If the mailbox reports a valid TREE_SRC, auto-tick the
-- "project src connected" toggle (a manual tick otherwise stays as the user set it).
local function refresh()
	local up, detected = pingMailbox()
	mailboxUp = up
	if detected ~= "" then
		srcConnected = true
		srcPath = detected
		ui.setSrcToggle(true, true, detected) -- auto-detected
	else
		ui.setSrcToggle(srcConnected, false, "") -- keep manual state, re-render label
	end
	ui.setStatus(currentGuide())
	ui.setRuntimeText(runtimeBlock())
	ui.setCommands(commandsFor())
end

-- True if Studio's "Allow HTTP Requests" is on. Otherwise warns and returns false
-- so we never walk the DataModel for a request that can't be sent.
local function httpReady(setStatus): boolean
	local ok, enabled = pcall(function()
		return HttpService.HttpEnabled
	end)
	if ok and not enabled then
		setStatus(HTTP_WARNING, true)
		return false
	end
	return true
end

local function kb(bytes: number): number
	return math.floor(bytes / 1024 + 0.5)
end

-- Roblox caps a single PostAsync body at 1024 KB; stay well under it and split
-- bigger dumps (e.g. a collision dump with thousands of parts) into ordered chunks
-- the mailbox reassembles. PostAsync is blocking, so chunks arrive in order.
-- NOTE: requires the UPDATED mailbox (server.py) running - restart it after updating.
local MAX_CHUNK = 512 * 1024

local function sendOnce(url: string, body: string): (boolean, string, number)
	local t0 = os.clock()
	local ok, resp
	-- Retry transient network failures (NetFail / Timeout). Heavy GetProductInfo use
	-- right before an Ownership upload can briefly throttle Roblox's HTTP, so the first
	-- PostAsync sometimes comes back NetFail - back off and try again before giving up.
	for attempt = 1, 4 do
		ok, resp = pcall(function()
			return HttpService:PostAsync(url, body, Enum.HttpContentType.TextPlain)
		end)
		if ok then break end
		local low = tostring(resp):lower()
		local transient = low:find("netfail") or low:find("timedout") or low:find("timeout") or low:find("throttle")
		if (not transient) or attempt == 4 then break end
		task.wait(2 * attempt) -- 2s, 4s, 6s back-off to let the throttle clear
	end
	return ok, tostring(resp), os.clock() - t0
end

-- Translate a PostAsync result into the status line (success echo or a friendly
-- error). Only called for the FINAL request (a single shot, or the last chunk).
local function report(ok: boolean, msg: string, secs: number, url: string, setStatus)
	local low = msg:lower()
	if ok then
		mailboxUp = true
		setStatus(("Done in %.1fs. Treehouse replied:\n%s\nCheck your browser for the refreshed pages.")
			:format(secs, msg))
	elseif low:find("not enabled") then
		setStatus(HTTP_WARNING, true)
	elseif low:find("connectfail") or low:find("connect") or low:find("refused") then
		mailboxUp = false
		setStatus(("Couldn't reach Treehouse at %s - the mailbox isn't running yet.\n\n"):format(url)
			.. currentGuide(), true)
	elseif low:find("timedout") or low:find("timeout") then
		setStatus(("Treehouse at %s timed out after %.0fs.\nIt may still be running the generators - wait, then retry.")
			:format(url, secs), true)
	else
		setStatus(("Treehouse error from %s:\n%s"):format(url, msg), true)
	end
end

-- POST a dump to the mailbox, reporting each stage in the status line.
local function post(endpoint: string, label: string, body: string, setStatus)
	local base = MAILBOX .. endpoint .. "?project=" .. HttpService:UrlEncode(PROJECT)
	local _, lines = body:gsub("\n", "")

	if #body <= MAX_CHUNK then
		setStatus(("Dumped %d %s lines (%d KB).\nPOSTing to %s …"):format(lines, label, kb(#body), base))
		task.wait() -- paint before the (blocking) request
		local ok, msg, secs = sendOnce(base, body)
		report(ok, msg, secs, base, setStatus)
		return
	end

	-- too big for one request: send ordered chunks under a shared id.
	local id = HttpService:GenerateGUID(false)
	local total = math.ceil(#body / MAX_CHUNK)
	for i = 1, total do
		local chunk = body:sub((i - 1) * MAX_CHUNK + 1, i * MAX_CHUNK)
		local url = ("%s&id=%s&chunk=%d&chunks=%d"):format(base, id, i, total)
		setStatus(("Dumped %d %s lines (%d KB). Sending chunk %d/%d…"):format(lines, label, kb(#body), i, total))
		task.wait()
		local ok, msg, secs = sendOnce(url, chunk)
		if (not ok) or i == total then
			-- a mid-chunk failure stops the run; the last chunk carries the generator reply
			report(ok, msg, secs, url, setStatus)
			if not ok then return end
		end
	end
end

ui = Gui.build(widget, {
	onGenerateAttribute = function(setStatus)
		if not httpReady(setStatus) then return end
		setStatus("Walking the DataModel for attributes…")
		task.wait() -- let the status paint before the synchronous walk
		local dump = Dumpers.AttributeDump()
		post("/refresh/attributes", "attribute", dump, setStatus)
	end,
	onGenerateValue = function(setStatus)
		if not httpReady(setStatus) then return end
		setStatus("Walking the DataModel for ValueBase objects…")
		task.wait()
		local dump = Dumpers.ValueBaseDump()
		post("/refresh/values", "value", dump, setStatus)
	end,
	onGenerateCollision = function(setStatus)
		if not httpReady(setStatus) then return end
		setStatus("Walking the DataModel for parts with non-default collision settings…")
		task.wait()
		local dump = Dumpers.CollisionDump()
		post("/refresh/collisions", "collision", dump, setStatus)
	end,
	onGenerateOwnership = function(setStatus, classes)
		if not httpReady(setStatus) then return end
		setStatus("Walking the DataModel for uploaded assets…")
		task.wait()
		local dump = Dumpers.OwnershipDump(function(done, total)
			setStatus(("Generating Ownership Treehouse… resolved %d / %d unique assets\n"
				.. "(one Roblox catalog lookup each — large places take a while)"):format(done, total))
		end, classes)
		post("/refresh/ownership", "ownership", dump, setStatus)
	end,
	-- "Include Runtime in Treehouse" toggle: update the runtime status AND the
	-- command boxes (they add/drop the TREE_SRC= prefix with the runtime toggle).
	onToggleRuntime = function(checked)
		includeRuntime = checked
		ui.setRuntimeText(runtimeBlock())
		ui.setCommands(commandsFor())
	end,
	-- "I have Python installed" toggle: re-render the guide and swap the command
	-- boxes between python and `uv run`.
	onTogglePython = function(checked)
		hasPython = checked
		ui.setStatus(currentGuide())
		ui.setCommands(commandsFor())
	end,
	-- "Connect your project src" toggle: user ticked it manually (auto-tick happens
	-- in refresh() from the mailbox's /health). Just refresh the runtime note.
	onToggleSrc = function(checked)
		srcConnected = checked
		ui.setRuntimeText(runtimeBlock())
	end,
	-- The active (hovered) Treehouse reports whether src matters. Geometry & Ownership
	-- don't use src, so the command boxes drop the TREE_SRC= prefix for them. (Guarded:
	-- this fires once during Gui.build before `ui` exists - skip the push that time.)
	onActiveTreehouse = function(relevant)
		srcRelevant = relevant
		if ui then
			ui.setRuntimeText(runtimeBlock())
			ui.setCommands(commandsFor())
		end
	end,
})

-- Greet with the setup explainer + runtime note + OS commands (mailboxUp is
-- false until the first ping on open).
ui.setStatus(currentGuide())
ui.setRuntimeText(runtimeBlock())
ui.setCommands(commandsFor())

-- Re-check the mailbox each time the widget is opened: if it answers, the
-- guide collapses to "✅ Mailbox already running."
widget:GetPropertyChangedSignal("Enabled"):Connect(function()
	if widget.Enabled then
		refresh()
	end
end)

button.Click:Connect(function()
	widget.Enabled = not widget.Enabled
end)
