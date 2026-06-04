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
local ui                 -- GUI handle (assigned after Gui.build below)

-- The terminal commands shown in the GUI boxes, switching between the user's
-- own Python and uv (which provisions Python) based on the hasPython toggle.
local function commandsFor(): (string, string)
	if hasPython then
		return "cd ~/Treehouse && python3 mailbox/server.py",
			'cd /d "%USERPROFILE%\\Treehouse" && python mailbox\\server.py'
	end
	return "cd ~/Treehouse && uv run mailbox/server.py",
		'cd /d "%USERPROFILE%\\Treehouse" && uv run mailbox\\server.py'
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
local function runtimeBlock(): string
	if includeRuntime then
		return "✅ Runtime in Treehouse - INCLUDED\n"
			.. "Connect your project src so the * / ** runtime markers fill in.\n"
			.. "Set ATTRTREE_SRC to your project's Rojo src/ before starting the mailbox:\n"
			.. "      Windows:  set ATTRTREE_SRC=C:\\path\\YourProject\\src\n"
			.. "      macOS:    ATTRTREE_SRC=/path/YourProject/src python3 mailbox/server.py"
	end
	return "❌ Runtime in Treehouse - not included\n"
		.. 'Tick "Include Runtime in Treehouse" above to also capture runtime\n'
		.. "attribute / value states (adds the src-connection step above)."
end

-- Ping the mailbox's health endpoint. Returns true if it answered, which means
-- Python + the mailbox are up. False on connect-fail or if HTTP is disabled.
local function pingMailbox(): boolean
	local ok = pcall(function()
		HttpService:GetAsync(MAILBOX .. "/health", true) -- nocache: always a fresh check
	end)
	return ok
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
-- the OS command boxes.
local function refresh()
	mailboxUp = pingMailbox()
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

-- POST a dump to the mailbox, reporting each stage in the status line.
local function post(endpoint: string, label: string, body: string, setStatus)
	local url = MAILBOX .. endpoint .. "?project=" .. HttpService:UrlEncode(PROJECT)
	local _, lines = body:gsub("\n", "")
	setStatus(("Dumped %d %s lines (%d KB).\nPOSTing to %s …"):format(lines, label, kb(#body), url))
	task.wait() -- paint before the (blocking) request

	local t0 = os.clock()
	local ok, resp = pcall(function()
		return HttpService:PostAsync(url, body, Enum.HttpContentType.TextPlain)
	end)
	local secs = os.clock() - t0
	local msg = tostring(resp)
	local low = msg:lower()

	if ok then
		mailboxUp = true
		-- the mailbox echoes e.g. "wrote N bytes -> X.luau, opened A.html, B.html"
		setStatus(("Done in %.1fs. Treehouse replied:\n%s\nCheck your browser for the refreshed pages.")
			:format(secs, msg))
	elseif low:find("not enabled") then
		-- HttpEnabled read stale / toggled off mid-session.
		setStatus(HTTP_WARNING, true)
	elseif low:find("connectfail") or low:find("connect") or low:find("refused") then
		mailboxUp = false
		setStatus(
			("Couldn't reach Treehouse at %s - the mailbox isn't running yet.\n\n"):format(url)
			.. currentGuide(),
			true)
	elseif low:find("timedout") or low:find("timeout") then
		setStatus(("Treehouse at %s timed out after %.0fs.\nIt may still be running the generators - wait, then retry.")
			:format(url, secs), true)
	else
		-- e.g. a 500 from a generator that failed server-side.
		setStatus(("Treehouse error from %s:\n%s"):format(url, msg), true)
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
	-- "Include Runtime in Treehouse" toggle: update the runtime note (✅/❌).
	onToggleRuntime = function(checked)
		includeRuntime = checked
		ui.setRuntimeText(runtimeBlock())
		ui.scrollStatusToBottom() -- reveal the runtime note at the bottom
	end,
	-- "I have Python installed" toggle: re-render the guide and swap the command
	-- boxes between python and `uv run`.
	onTogglePython = function(checked)
		hasPython = checked
		ui.setStatus(currentGuide())
		ui.setCommands(commandsFor())
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
