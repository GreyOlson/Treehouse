--[[
	AttributeToolGui.luau
	---------------------
	Builds the "Attribute / ValueBase Tree" tool GUI entirely in code - no assets,
	fully memory-contained. Drop it in StarterGui as a LocalScript, or call
	M.build(parentGui) from a plugin's DockWidgetPluginGui.

	Layout is fully anchor-based so every element stays inside the widget and the
	output area grows/shrinks when the dock is resized:
	  • Title TextLabel      - place name (PROJECT_NAME), pinned at the top
	  • GenerateAttribute / GenerateValueBase TextButtons - side by side, below it
	  • Status ScrollingFrame - fills the space between the buttons and Clear Output
	  • ClearOutput TextButton - pinned to the bottom; clears the status message
	  • White backdrop with a 40,40,40 -> 60,60,80 gradient

	Wire the two buttons to your refresh pipeline via opts (see Plugin.server.luau).
--]]

local M = {}

-- The place name your Studio session is tied to (also used as PROJECT_NAME).
local function getPlaceName(): string
	local ok, info = pcall(function()
		return game:GetService("MarketplaceService"):GetProductInfo(game.PlaceId)
	end)
	if ok and typeof(info) == "table" and info.Name and #info.Name > 0 then
		return info.Name
	end
	return game.Name -- Studio fallback: game.Name is the open place's name
end

local function corner(parent: Instance, radius: number)
	local c = Instance.new("UICorner")
	c.CornerRadius = UDim.new(0, radius)
	c.Parent = parent
	return c
end

-- Builds the whole UI into `host` (a ScreenGui or a plugin widget).
-- opts (optional): { onGenerateAttribute = function()..., onGenerateValue = function()... }
-- Returns a handle: { root = Frame, setStatus = function(text, isError) }
function M.build(host: Instance, opts: { [string]: any }?)
	opts = opts or {}

	-- backdrop: white base + dark diagonal gradient
	local backdrop = Instance.new("Frame")
	backdrop.Name = "Backdrop"
	backdrop.Size = UDim2.fromScale(1, 1)
	backdrop.BackgroundColor3 = Color3.fromRGB(255, 255, 255)
	backdrop.BorderSizePixel = 0
	backdrop.ZIndex = 0
	backdrop.Parent = host

	local grad = Instance.new("UIGradient")
	grad.Color = ColorSequence.new(Color3.fromRGB(40, 40, 40), Color3.fromRGB(60, 60, 80))
	grad.Rotation = 90
	grad.Parent = backdrop

	-- Anchor metrics. The header (title + buttons) and footer (clear) are fixed
	-- pixel heights; the status scroll fills everything between them and so
	-- resizes automatically with the widget - no fixed sizes, nothing clips.
	local MARGIN = 12
	local HEADER_H = 288 -- title + generate row + runtime toggle + descriptions + disclaimer
	local FOOTER_H = 56  -- clear-output row

	-- shared button factory
	local function makeButton(name: string, text: string, bg: Color3,
		size: UDim2, position: UDim2, parent: Instance, maxText: number?, radius: number?)
		local b = Instance.new("TextButton")
		b.Name = name
		b.Text = text
		b.Font = Enum.Font.GothamMedium
		b.TextScaled = true
		b.TextWrapped = true
		b.TextColor3 = Color3.fromRGB(255, 255, 255)
		b.BackgroundColor3 = bg
		b.AutoButtonColor = true
		b.BorderSizePixel = 0
		b.Size = size
		b.Position = position
		b.ZIndex = 6
		b.Parent = parent
		corner(b, radius or 12)
		local con = Instance.new("UITextSizeConstraint")
		con.MaxTextSize = maxText or 18
		con.Parent = b
		return b
	end

	-- Title = place name, pinned at the top, left-aligned (matches the free tier)
	local title = Instance.new("TextLabel")
	title.Name = "Title"
	title.Text = getPlaceName()
	title.Font = Enum.Font.GothamBold
	title.TextScaled = true
	title.TextXAlignment = Enum.TextXAlignment.Left
	title.TextColor3 = Color3.fromRGB(255, 255, 255)
	title.BackgroundTransparency = 1
	title.ZIndex = 6
	title.Position = UDim2.fromOffset(MARGIN, 8)
	title.Size = UDim2.new(1, -2 * MARGIN, 0, 30)
	title.Parent = backdrop
	local titleConstraint = Instance.new("UITextSizeConstraint")
	titleConstraint.MaxTextSize = 24
	titleConstraint.Parent = title

	-- Generate buttons, side by side below the title (same sizing as the free tier)
	local genRow = Instance.new("Frame")
	genRow.Name = "GenerateRow"
	genRow.BackgroundTransparency = 1
	genRow.ZIndex = 5
	genRow.Position = UDim2.fromOffset(MARGIN, 44)
	genRow.Size = UDim2.new(1, -2 * MARGIN, 0, 46)
	genRow.Parent = backdrop

	-- four generate buttons, evenly split across the row (text scales to fit)
	local genAttr = makeButton("GenerateAttributeTree", "Generate Attribute Treehouse",
		Color3.fromRGB(120, 170, 235), -- medium-light blue
		UDim2.new(1 / 4, -3, 1, 0), UDim2.new(0, 0, 0, 0), genRow, 13, 8)
	local genValue = makeButton("GenerateValueBaseTree", "Generate Value* Treehouse",
		Color3.fromRGB(235, 120, 120), -- medium-light red
		UDim2.new(1 / 4, -3, 1, 0), UDim2.new(1 / 4, 1, 0, 0), genRow, 13, 8)
	local genCollision = makeButton("GenerateGeometryTree", "Generate Geometry Treehouse",
		Color3.fromRGB(120, 205, 165), -- medium-light teal
		UDim2.new(1 / 4, -3, 1, 0), UDim2.new(2 / 4, 2, 0, 0), genRow, 13, 8)
	local genOwnership = makeButton("GenerateOwnershipTree", "Generate Ownership Treehouse",
		Color3.fromRGB(200, 160, 235), -- medium-light purple
		UDim2.new(1 / 4, -3, 1, 0), UDim2.new(3 / 4, 3, 0, 0), genRow, 13, 8)

	-- Runtime toggle, between the generate buttons and the status area
	local includeRuntime = false
	local toggle = Instance.new("TextButton")
	toggle.Name = "ToggleRuntimeTrees"
	toggle.Text = "❌  Include Runtime in Treehouse"
	toggle.Font = Enum.Font.GothamMedium
	toggle.TextSize = 14
	toggle.TextXAlignment = Enum.TextXAlignment.Left
	toggle.TextColor3 = Color3.fromRGB(235, 235, 240)
	toggle.BackgroundColor3 = Color3.fromRGB(50, 50, 60)
	toggle.AutoButtonColor = true
	toggle.BorderSizePixel = 0
	toggle.Position = UDim2.fromOffset(MARGIN, 96)
	toggle.Size = UDim2.new(1, -2 * MARGIN, 0, 26)
	toggle.ZIndex = 6
	toggle.Parent = backdrop
	corner(toggle, 8)
	local togPad = Instance.new("UIPadding")
	togPad.PaddingLeft = UDim.new(0, 10)
	togPad.Parent = toggle

	-- Runtime-toggle description. The "connect your src" hint disappears once runtime
	-- is included; the disclaimer is always shown. (Single auto-sizing label so the
	-- two never leave a gap.)
	local toggleDesc = Instance.new("TextLabel")
	toggleDesc.Name = "ToggleRuntimeDescrition"
	toggleDesc.Font = Enum.Font.Gotham
	toggleDesc.TextSize = 11
	toggleDesc.TextWrapped = true
	toggleDesc.TextXAlignment = Enum.TextXAlignment.Left
	toggleDesc.TextYAlignment = Enum.TextYAlignment.Top
	toggleDesc.TextColor3 = Color3.fromRGB(165, 165, 175)
	toggleDesc.BackgroundTransparency = 1
	toggleDesc.Position = UDim2.fromOffset(MARGIN, 128)
	toggleDesc.Size = UDim2.new(1, -2 * MARGIN, 0, 0)
	toggleDesc.AutomaticSize = Enum.AutomaticSize.Y
	toggleDesc.ZIndex = 6
	toggleDesc.Parent = backdrop
	local CONNECT_HINT = "With an additional step to connect to your project src, you can get "
		.. "detected runtime states for attributes or values."
	local DISCLAIMER = "Plugin may not find every possible way to know or understand whether an "
		.. "attribute or value was created at runtime*.  Use of this plugin is at your own risk."
	local function renderToggleDesc()
		-- hide the connect hint once runtime is included; always keep the disclaimer
		toggleDesc.Text = includeRuntime and DISCLAIMER or (CONNECT_HINT .. "\n\n" .. DISCLAIMER)
	end
	renderToggleDesc()

	-- HTML feature blurb, beneath the runtime toggle description
	local htmlDesc = Instance.new("TextLabel")
	htmlDesc.Name = "HtmlFeatureDescription"
	htmlDesc.Text = "Generate for 2 pages to open.  One for a hierarchy map, the other "
		.. "for a hierarchy tree.  Categorize by search, service, host instance type.  "
		.. "Find the attribute you need and copy back text for code or hierarchy search."
	htmlDesc.Font = Enum.Font.Gotham
	htmlDesc.TextSize = 11
	htmlDesc.TextWrapped = true
	htmlDesc.TextXAlignment = Enum.TextXAlignment.Left
	htmlDesc.TextYAlignment = Enum.TextYAlignment.Top
	htmlDesc.TextColor3 = Color3.fromRGB(150, 180, 215)
	htmlDesc.BackgroundTransparency = 1
	htmlDesc.Position = UDim2.fromOffset(MARGIN, 222)
	htmlDesc.Size = UDim2.new(1, -2 * MARGIN, 0, 0)
	htmlDesc.AutomaticSize = Enum.AutomaticSize.Y
	htmlDesc.ZIndex = 6
	htmlDesc.Parent = backdrop

	-- Ownership asset-class checkboxes. Shown only while the Ownership button is the
	-- active (last-hovered) Treehouse, in the space the runtime row uses otherwise.
	-- Narrowing the classes makes the (slow) catalog scan faster. Default = All.
	local ownSel = { all = true, mesh = false, sound = false, image = false }
	local ownChecks: { [string]: TextButton } = {}
	local ownPanel = Instance.new("Frame")
	ownPanel.Name = "OwnershipClasses"
	ownPanel.BackgroundTransparency = 1
	ownPanel.Position = UDim2.fromOffset(MARGIN, 96)
	ownPanel.Size = UDim2.new(1, -2 * MARGIN, 0, 118)
	ownPanel.ZIndex = 6
	ownPanel.Visible = false
	ownPanel.Parent = backdrop
	local ownList = Instance.new("UIListLayout")
	ownList.FillDirection = Enum.FillDirection.Vertical
	ownList.SortOrder = Enum.SortOrder.LayoutOrder
	ownList.Padding = UDim.new(0, 3)
	ownList.Parent = ownPanel
	local ownHdr = Instance.new("TextLabel")
	ownHdr.Text = "Asset classes to scan (fewer = faster):"
	ownHdr.Font = Enum.Font.GothamMedium
	ownHdr.TextSize = 12
	ownHdr.TextXAlignment = Enum.TextXAlignment.Left
	ownHdr.TextColor3 = Color3.fromRGB(205, 185, 230)
	ownHdr.BackgroundTransparency = 1
	ownHdr.Size = UDim2.new(1, 0, 0, 18)
	ownHdr.LayoutOrder = 0
	ownHdr.ZIndex = 6
	ownHdr.Parent = ownPanel

	local function syncOwn()
		-- a specific pick clears "All"; with no specific picks, fall back to "All"
		if not (ownSel.mesh or ownSel.sound or ownSel.image) then ownSel.all = true end
		if ownSel.all then ownSel.mesh, ownSel.sound, ownSel.image = false, false, false end
		for key, b in pairs(ownChecks) do
			local on = if key == "all" then ownSel.all else ownSel[key]
			b.Text = (on and "✅  " or "❌  ") .. (b:GetAttribute("lbl") :: string)
		end
	end
	local function ownCheck(key: string, labelText: string, order: number)
		local b = Instance.new("TextButton")
		b.Name = "Class_" .. key
		b:SetAttribute("lbl", labelText)
		b.Text = "❌  " .. labelText
		b.Font = Enum.Font.Gotham
		b.TextSize = 13
		b.TextXAlignment = Enum.TextXAlignment.Left
		b.TextColor3 = Color3.fromRGB(225, 220, 235)
		b.BackgroundColor3 = Color3.fromRGB(48, 44, 58)
		b.AutoButtonColor = true
		b.BorderSizePixel = 0
		b.Size = UDim2.new(1, 0, 0, 22)
		b.LayoutOrder = order
		b.ZIndex = 6
		b.Parent = ownPanel
		corner(b, 6)
		local pad = Instance.new("UIPadding")
		pad.PaddingLeft = UDim.new(0, 8)
		pad.Parent = b
		b.Activated:Connect(function()
			if key == "all" then
				ownSel.all = true
			else
				ownSel[key] = not ownSel[key]
				ownSel.all = false
			end
			syncOwn()
		end)
		ownChecks[key] = b
	end
	ownCheck("all", "All", 1)
	ownCheck("mesh", "Meshes", 2)
	ownCheck("sound", "Sounds", 3)
	ownCheck("image", "Images (textures & decals)", 4)
	syncOwn()
	local function getOwnershipClasses(): { [string]: boolean }?
		if ownSel.all then return nil end -- nil = scan everything
		return { mesh = ownSel.mesh, sound = ownSel.sound, image = ownSel.image }
	end

	-- assigned once srcToggle exists (further down); shows/hides it with the runtime toggle
	local onRuntimeChanged: ((boolean) -> ())? = nil
	local function setRuntimeToggle(on: boolean)
		includeRuntime = on
		toggle.Text = (on and "✅" or "❌") .. "  Include Runtime in Treehouse"
		renderToggleDesc()  -- hide the connect hint when runtime is included
		if onRuntimeChanged then onRuntimeChanged(on) end
		if opts.onToggleRuntime then
			opts.onToggleRuntime(on)
		end
	end
	toggle.Activated:Connect(function()
		setRuntimeToggle(not includeRuntime)
	end)

	-- Clear Output, pinned to the bottom, full width
	local clearOut = makeButton("ClearOutput", "Clear Output",
		Color3.fromRGB(120, 120, 130), -- neutral gray
		UDim2.new(1, -2 * MARGIN, 0, 40), UDim2.new(0, MARGIN, 1, -8), backdrop)
	clearOut.AnchorPoint = Vector2.new(0, 1)

	-- Status area: a ScrollingFrame holding the dynamic status text, the
	-- ready-to-run command boxes (one per OS), and the runtime note. Children
	-- are stacked by a UIListLayout; the canvas height tracks their total size.
	local status = Instance.new("ScrollingFrame")
	status.Name = "Status"
	status.BackgroundColor3 = Color3.fromRGB(28, 28, 34)
	status.BackgroundTransparency = 0.25
	status.BorderSizePixel = 0
	status.Position = UDim2.fromOffset(MARGIN, HEADER_H)
	status.Size = UDim2.new(1, -2 * MARGIN, 1, -(HEADER_H + FOOTER_H))
	status.CanvasSize = UDim2.new()
	status.ScrollBarThickness = 8
	status.ZIndex = 6
	status.Parent = backdrop
	corner(status, 8)
	local spad = Instance.new("UIPadding")
	spad.PaddingLeft = UDim.new(0, 8)
	spad.PaddingRight = UDim.new(0, 8)
	spad.PaddingTop = UDim.new(0, 6)
	spad.PaddingBottom = UDim.new(0, 6)
	spad.Parent = status
	local slist = Instance.new("UIListLayout")
	slist.FillDirection = Enum.FillDirection.Vertical
	slist.SortOrder = Enum.SortOrder.LayoutOrder
	slist.Padding = UDim.new(0, 6)
	slist.Parent = status

	-- "Do you have Python installed?" toggle. Drives the setup guide + command
	-- boxes: when off, the guide adds a one-line "install uv" step (uv fetches
	-- Python for you) and the commands switch to `uv run`.
	local hasPython = true
	local pyToggle = Instance.new("TextButton")
	pyToggle.Name = "TogglePythonInstalled"
	pyToggle.Text = "✅ I already have Python installed"
	pyToggle.Font = Enum.Font.GothamMedium
	pyToggle.TextSize = 13
	pyToggle.TextXAlignment = Enum.TextXAlignment.Left
	pyToggle.TextColor3 = Color3.fromRGB(235, 235, 240)
	pyToggle.BackgroundColor3 = Color3.fromRGB(50, 50, 60)
	pyToggle.AutoButtonColor = true
	pyToggle.BorderSizePixel = 0
	pyToggle.Size = UDim2.new(1, 0, 0, 28)
	pyToggle.AutomaticSize = Enum.AutomaticSize.Y
	pyToggle.LayoutOrder = 0
	pyToggle.ZIndex = 6
	pyToggle.Parent = status
	corner(pyToggle, 6)
	local pyPad = Instance.new("UIPadding")
	pyPad.PaddingLeft = UDim.new(0, 8)
	pyPad.PaddingTop = UDim.new(0, 5)
	pyPad.PaddingBottom = UDim.new(0, 5)
	pyPad.Parent = pyToggle

	local function setPythonToggle(on: boolean)
		hasPython = on
		pyToggle.Text = on and "✅ I already have Python installed"
			or "❌ No Python - use uv (it installs Python for you)"
		if opts.onTogglePython then opts.onTogglePython(on) end
	end
	pyToggle.Activated:Connect(function() setPythonToggle(not hasPython) end)

	local statusText = Instance.new("TextLabel")
	statusText.Name = "StatusText"
	statusText.Text = ""
	statusText.Font = Enum.Font.Gotham
	statusText.TextSize = 13
	statusText.TextWrapped = true
	statusText.TextXAlignment = Enum.TextXAlignment.Left
	statusText.TextYAlignment = Enum.TextYAlignment.Top
	statusText.TextColor3 = Color3.fromRGB(225, 225, 230)
	statusText.BackgroundTransparency = 1
	statusText.Size = UDim2.new(1, 0, 0, 0)
	statusText.AutomaticSize = Enum.AutomaticSize.Y
	statusText.LayoutOrder = 1
	statusText.ZIndex = 6
	statusText.Parent = status

	-- Hint above the command boxes
	local cmdHint = Instance.new("TextLabel")
	cmdHint.Name = "CommandHint"
	cmdHint.Text = "Copy the line for your system, paste it into Terminal (Mac) / "
		.. "Command Prompt (Windows), and press Enter:"
	cmdHint.Font = Enum.Font.GothamMedium
	cmdHint.TextSize = 12
	cmdHint.TextWrapped = true
	cmdHint.TextXAlignment = Enum.TextXAlignment.Left
	cmdHint.TextYAlignment = Enum.TextYAlignment.Top
	cmdHint.TextColor3 = Color3.fromRGB(240, 200, 120)
	cmdHint.BackgroundTransparency = 1
	cmdHint.Size = UDim2.new(1, 0, 0, 0)
	cmdHint.AutomaticSize = Enum.AutomaticSize.Y
	cmdHint.LayoutOrder = 5 -- below runtime status (2) + hide-path (3) + src toggle (4)
	cmdHint.ZIndex = 6
	cmdHint.Parent = status

	-- A label + selectable command box. The box is editable only so selection
	-- works and you can tweak the path; selecting never clears it.
	local function commandBox(order: number, labelText: string, command: string)
		local lbl = Instance.new("TextLabel")
		lbl.Text = labelText
		lbl.Font = Enum.Font.GothamBold
		lbl.TextSize = 12
		lbl.TextXAlignment = Enum.TextXAlignment.Left
		lbl.TextColor3 = Color3.fromRGB(200, 200, 210)
		lbl.BackgroundTransparency = 1
		lbl.Size = UDim2.new(1, 0, 0, 16)
		lbl.LayoutOrder = order
		lbl.ZIndex = 6
		lbl.Parent = status

		local box = Instance.new("TextBox")
		box.Name = (labelText:gsub("[^%w]", "")) .. "Command"
		box.Text = command
		box.ClearTextOnFocus = false
		box.TextEditable = true
		box.MultiLine = true
		box.Font = Enum.Font.Code
		box.TextSize = 13
		box.TextXAlignment = Enum.TextXAlignment.Left
		box.TextYAlignment = Enum.TextYAlignment.Top
		box.TextWrapped = true
		box.TextColor3 = Color3.fromRGB(235, 235, 240)
		box.BackgroundColor3 = Color3.fromRGB(16, 16, 20)
		box.BorderSizePixel = 0
		box.Size = UDim2.new(1, 0, 0, 0)
		box.AutomaticSize = Enum.AutomaticSize.Y
		box.LayoutOrder = order + 1
		box.ZIndex = 6
		box.Parent = status
		corner(box, 6)
		local bpad = Instance.new("UIPadding")
		bpad.PaddingLeft = UDim.new(0, 6)
		bpad.PaddingRight = UDim.new(0, 6)
		bpad.PaddingTop = UDim.new(0, 5)
		bpad.PaddingBottom = UDim.new(0, 5)
		bpad.Parent = box
		return box
	end

	local macBox = commandBox(6, "macOS / Linux", "cd ~/Treehouse && python3 mailbox/server.py")
	local winBox = commandBox(8, "Windows (Command Prompt)", 'cd /d "%USERPROFILE%\\Treehouse" && python mailbox\\server.py')

	local function setCommands(mac: string, win: string)
		macBox.Text = mac
		winBox.Text = win
	end

	-- "Connect your project src" toggle (+ a privacy toggle right above it that hides
	-- the local path). Both are auto-managed and shown only while "Include Runtime in
	-- Treehouse" is on. The plugin auto-ticks "connected" when the mailbox reports a
	-- valid TREE_SRC.
	local srcConnected = false
	local hidePath = false                 -- privacy: omit the local path from the line
	local lastAuto: boolean? = false       -- remember the last reported auto/path so the
	local lastPath: string? = nil          -- line can be re-rendered when hidePath flips

	-- Privacy toggle: hides the local src path (e.g. while screen-recording).
	local hidePathToggle = Instance.new("TextButton")
	hidePathToggle.Name = "ToggleHideSrcPath"
	hidePathToggle.Font = Enum.Font.GothamMedium
	hidePathToggle.TextSize = 12
	hidePathToggle.TextXAlignment = Enum.TextXAlignment.Left
	hidePathToggle.TextColor3 = Color3.fromRGB(205, 205, 215)
	hidePathToggle.BackgroundColor3 = Color3.fromRGB(45, 45, 55)
	hidePathToggle.AutoButtonColor = true
	hidePathToggle.BorderSizePixel = 0
	hidePathToggle.Size = UDim2.new(1, 0, 0, 24)
	hidePathToggle.AutomaticSize = Enum.AutomaticSize.Y
	hidePathToggle.LayoutOrder = 3         -- directly above the src toggle (4)
	hidePathToggle.ZIndex = 6
	hidePathToggle.Visible = false
	hidePathToggle.Parent = status
	corner(hidePathToggle, 6)
	local hpPad = Instance.new("UIPadding")
	hpPad.PaddingLeft = UDim.new(0, 8)
	hpPad.PaddingTop = UDim.new(0, 4)
	hpPad.PaddingBottom = UDim.new(0, 4)
	hpPad.Parent = hidePathToggle

	local srcToggle = Instance.new("TextButton")
	srcToggle.Name = "ToggleSrcConnected"
	srcToggle.Text = "❌  Connect your project src (fills the * / ** markers)"
	srcToggle.Font = Enum.Font.GothamMedium
	srcToggle.TextSize = 13
	srcToggle.TextXAlignment = Enum.TextXAlignment.Left
	srcToggle.TextColor3 = Color3.fromRGB(235, 235, 240)
	srcToggle.BackgroundColor3 = Color3.fromRGB(50, 50, 60)
	srcToggle.AutoButtonColor = true
	srcToggle.BorderSizePixel = 0
	srcToggle.Size = UDim2.new(1, 0, 0, 28)
	srcToggle.AutomaticSize = Enum.AutomaticSize.Y
	srcToggle.LayoutOrder = 4 -- above the command boxes (runtime status is 2)
	srcToggle.ZIndex = 6
	srcToggle.Visible = false
	srcToggle.Parent = status
	corner(srcToggle, 6)
	local srcPad = Instance.new("UIPadding")
	srcPad.PaddingLeft = UDim.new(0, 8)
	srcPad.PaddingTop = UDim.new(0, 5)
	srcPad.PaddingBottom = UDim.new(0, 5)
	srcPad.Parent = srcToggle

	-- Reflect the connected/not state. With "Hide src path" on, the path is omitted.
	local function renderSrcToggle()
		if srcConnected then
			local showPath = (not hidePath) and lastAuto and lastPath ~= nil and lastPath ~= ""
			srcToggle.Text = "✅  Project src connected" .. (showPath and ("  (" .. lastPath .. ")") or "")
		else
			srcToggle.Text = "❌  Connect your project src (fills the * / ** markers)"
		end
	end
	local function setSrcToggle(on: boolean, auto: boolean?, path: string?)
		srcConnected = on
		lastAuto = auto
		lastPath = path
		renderSrcToggle()
	end
	srcToggle.Activated:Connect(function()
		srcConnected = not srcConnected
		lastAuto = false
		lastPath = nil
		renderSrcToggle()
		if opts.onToggleSrc then opts.onToggleSrc(srcConnected) end
	end)

	local function renderHidePath()
		hidePathToggle.Text = (hidePath and "✅" or "❌") .. "  Hide src path"
	end
	renderHidePath()
	hidePathToggle.Activated:Connect(function()
		hidePath = not hidePath
		renderHidePath()
		renderSrcToggle()
	end)

	-- show the src + privacy toggles only while runtime is included
	onRuntimeChanged = function(on: boolean)
		srcToggle.Visible = on
		hidePathToggle.Visible = on
	end

	-- Runtime note (✅/❌), updated when the toggle changes.
	local runtimeText = Instance.new("TextLabel")
	runtimeText.Name = "RuntimeText"
	runtimeText.Text = ""
	runtimeText.Font = Enum.Font.Gotham
	runtimeText.TextSize = 13
	runtimeText.TextWrapped = true
	runtimeText.TextXAlignment = Enum.TextXAlignment.Left
	runtimeText.TextYAlignment = Enum.TextYAlignment.Top
	runtimeText.TextColor3 = Color3.fromRGB(225, 225, 230)
	runtimeText.BackgroundTransparency = 1
	runtimeText.Size = UDim2.new(1, 0, 0, 0)
	runtimeText.AutomaticSize = Enum.AutomaticSize.Y
	runtimeText.LayoutOrder = 2 -- runtime status sits ABOVE the command boxes
	runtimeText.ZIndex = 6
	runtimeText.Parent = status

	-- Drive the scroll canvas from the laid-out content height so it always scrolls.
	local function syncCanvas()
		status.CanvasSize = UDim2.new(0, 0, 0, slist.AbsoluteContentSize.Y + 16)
	end
	slist:GetPropertyChangedSignal("AbsoluteContentSize"):Connect(syncCanvas)
	syncCanvas()

	local function setStatus(text: string, isError: boolean?)
		statusText.Text = text
		statusText.TextColor3 = isError and Color3.fromRGB(255, 120, 120) or Color3.fromRGB(225, 225, 230)
		status.CanvasPosition = Vector2.new(0, 0) -- show the start of each new message
	end

	local function setRuntimeText(text: string)
		runtimeText.Text = text
	end

	-- Scroll to the bottom (used after toggling runtime so the note is visible).
	local function scrollStatusToBottom()
		task.wait() -- let the new content lay out so the canvas size is final
		local maxY = math.max(0, status.AbsoluteCanvasSize.Y - status.AbsoluteWindowSize.Y)
		status.CanvasPosition = Vector2.new(0, maxY)
	end

	-- Busy guard: while one Treehouse is generating, the clicked button shows
	-- "Generating … Treehouse…" and every generate button ignores clicks until it
	-- finishes (then the label resets). Runs in a thread so the widget stays live.
	local generating = false
	local function runGen(btn: TextButton, name: string, fn: ((any) -> ())?)
		if not fn then
			print("[AttributeTool] Generate " .. name .. " Treehouse clicked (no handler)")
			return
		end
		if generating then return end
		generating = true
		local orig = btn.Text
		btn.Text = "Generating " .. name .. " Treehouse…"
		btn.AutoButtonColor = false
		task.spawn(function()
			local ok, err = pcall(fn, setStatus)
			btn.Text = orig
			btn.AutoButtonColor = true
			generating = false
			if not ok then warn("[Treehouse] " .. name .. " generate failed: " .. tostring(err)) end
		end)
	end
	genAttr.Activated:Connect(function() runGen(genAttr, "Attribute", opts.onGenerateAttribute) end)
	genValue.Activated:Connect(function() runGen(genValue, "Value*", opts.onGenerateValue) end)
	genCollision.Activated:Connect(function() runGen(genCollision, "Geometry", opts.onGenerateCollision) end)
	genOwnership.Activated:Connect(function()
		runGen(genOwnership, "Ownership", opts.onGenerateOwnership and function(ss)
			opts.onGenerateOwnership(ss, getOwnershipClasses())
		end or nil)
	end)

	-- Hover a generate button -> the info area below retargets to that Treehouse: the dock
	-- title, the gray tint, the runtime row (attribute / value* only), the feature blurb,
	-- and the Ownership asset-class checkboxes all follow the last-hovered button. Attribute
	-- is the default (matches the dock's "Treehouse - Attribute Explorer").
	local PROFILES = {
		attribute = { title = "Treehouse - Attribute Explorer", color = Color3.fromRGB(120, 170, 235), runtime = true,
			pages = "Generate for 2 pages to open.  One for a hierarchy map, the other for a hierarchy tree.  Categorize by search, service, host instance type.  Find the attribute you need and copy back text for code or hierarchy search." },
		value = { title = "Treehouse - Value* Explorer", color = Color3.fromRGB(235, 120, 120), runtime = true,
			pages = "Generate for 2 pages to open.  One for a hierarchy map, the other for a hierarchy tree.  Categorize by search, service, host instance type.  Find the ValueBase object you need and copy back text for code or hierarchy search." },
		geometry = { title = "Treehouse - Geometry Explorer", color = Color3.fromRGB(120, 205, 165), runtime = false,
			pages = "Find and sort through collision properties on the geometry in your place - CanCollide, CanQuery, CanTouch, CollisionFidelity and more - across services, with a layer map to jump around.  Opens one hierarchy tree." },
		ownership = { title = "Treehouse - Ownership Explorer", color = Color3.fromRGB(200, 160, 235), runtime = false,
			pages = "Find who created the uploaded assets in your place (user or group), sorted by instance type and by creator.  Pick which asset classes to scan above - fewer = faster.  Opens one hierarchy tree." },
	}
	local BG1, BG2 = Color3.fromRGB(40, 40, 40), Color3.fromRGB(60, 60, 80)
	local function applyProfile(key: string)
		local p = PROFILES[key]
		if not p then return end
		pcall(function() (host :: any).Title = p.title end) -- dock title (best-effort; read-only on some hosts)
		grad.Color = ColorSequence.new(BG1:Lerp(p.color, 0.16), BG2:Lerp(p.color, 0.28))
		status.BackgroundColor3 = Color3.fromRGB(28, 28, 34):Lerp(p.color, 0.10)
		toggle.BackgroundColor3 = Color3.fromRGB(50, 50, 60):Lerp(p.color, 0.16)
		toggle.Visible = p.runtime       -- runtime row is only relevant to attribute / value*
		toggleDesc.Visible = p.runtime
		htmlDesc.Text = p.pages
		ownPanel.Visible = (key == "ownership")
		-- the src "second section" (runtime note + connect-src / hide-path toggles) is
		-- attribute / value* only; the list reflows when these go invisible
		runtimeText.Visible = p.runtime
		local srcVis = p.runtime and includeRuntime
		srcToggle.Visible = srcVis
		hidePathToggle.Visible = srcVis
		if opts.onActiveTreehouse then opts.onActiveTreehouse(p.runtime) end
	end
	genAttr.MouseEnter:Connect(function() applyProfile("attribute") end)
	genValue.MouseEnter:Connect(function() applyProfile("value") end)
	genCollision.MouseEnter:Connect(function() applyProfile("geometry") end)
	genOwnership.MouseEnter:Connect(function() applyProfile("ownership") end)
	applyProfile("attribute") -- default
	clearOut.Activated:Connect(function()
		setStatus("")
	end)

	return {
		root = backdrop,
		setStatus = setStatus,
		setRuntimeText = setRuntimeText,
		setCommands = setCommands,
		scrollStatusToBottom = scrollStatusToBottom,
		setRuntimeToggle = setRuntimeToggle,
		getRuntime = function() return includeRuntime end,
		setSrcToggle = setSrcToggle,           -- (on, auto?, path?) - reflect src-connected state
		getSrcConnected = function() return srcConnected end,
	}
end

-- StarterGui usage: if this script is a LocalScript under StarterGui, auto-build.
if script:IsA("LocalScript") then
	local sg = Instance.new("ScreenGui")
	sg.Name = "AttributeToolGui"
	sg.IgnoreGuiInset = true
	sg.ResetOnSpawn = false
	sg.ZIndexBehavior = Enum.ZIndexBehavior.Sibling
	sg.Parent = game:GetService("Players").LocalPlayer:WaitForChild("PlayerGui")
	M.build(sg)
end

return M
