--[[
    MM2 STEALTH FARMER v4.1 - Minimalist Edition
    Underground coin collection + Coin Tracker + Webhook Integration
]]

local Players = game:GetService("Players")
local TweenService = game:GetService("TweenService")
local RunService = game:GetService("RunService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local HttpService = game:GetService("HttpService")
local LocalPlayer = Players.LocalPlayer
local VirtualUser = game:GetService("VirtualUser")

-- ═══════════════════════════════════════════════════════════════
-- CORE VARIABLES
-- ═══════════════════════════════════════════════════════════════

local character, hrp, humanoid
local farming = false
local stealthMode = true
local undergroundDepth = 3
local collectHeight = 0

local farmStartTime = 0
local totalFarmTime = 0
local afkModeEnabled = false

-- Coin tracking variables
local totalCoinsCollected = 0
local sessionCoinsCollected = 0
local coinLimit = 40

-- Webhook variables
local webhookType = "Discord"
local webhookUrl = ""
local telegramBotToken = ""
local telegramChatId = ""
local autoSendEnabled = true

-- ═══════════════════════════════════════════════════════════════
-- COIN TRACKER
-- ═══════════════════════════════════════════════════════════════

local function setupCoinTracker()
    local success, result = pcall(function()
        local remotesFolder = ReplicatedStorage:WaitForChild("Remotes", 10)
        if remotesFolder then
            local gameplayFolder = remotesFolder:WaitForChild("Gameplay", 10)
            if gameplayFolder then
                local coinCollectedEvent = gameplayFolder:WaitForChild("CoinCollected", 10)
                
                if coinCollectedEvent and coinCollectedEvent:IsA("RemoteEvent") then
                    coinCollectedEvent.OnClientEvent:Connect(function(currency, amount, maxAmount)
                        sessionCoinsCollected = sessionCoinsCollected + 1
                        totalCoinsCollected = totalCoinsCollected + 1
                        
                        print(string.format("[Coin Tracker] +1 coin | Session: %d | Total: %d", 
                            sessionCoinsCollected, totalCoinsCollected))
                    end)
                    
                    print("[Coin Tracker] Initialized!")
                    return true
                end
            end
        end
    end)
    
    if not success then
        warn("[Coin Tracker] Failed: " .. tostring(result))
    end
end

-- ═══════════════════════════════════════════════════════════════
-- WEBHOOK FUNCTIONS
-- ═══════════════════════════════════════════════════════════════

local function sendDiscordWebhook(message)
    if webhookUrl == "" or webhookUrl == "Webhook URL" then
        warn("[Webhook] Discord URL not configured!")
        return false
    end
    
    local data = {
        embeds = {{
            title = "🎮 MM2 Farm Report",
            description = message,
            color = 5814783,
            timestamp = os.date("!%Y-%m-%dT%H:%M:%S"),
            footer = { text = "MM2 Stealth Farmer v4.1" }
        }}
    }
    
    local success = pcall(function()
        request({
            Url = webhookUrl,
            Method = "POST",
            Headers = { ["Content-Type"] = "application/json" },
            Body = HttpService:JSONEncode(data)
        })
    end)
    
    if success then
        print("[Webhook] Discord sent!")
        return true
    else
        warn("[Webhook] Discord failed")
        return false
    end
end

local function sendTelegramMessage(message)
    if telegramBotToken == "" or telegramChatId == "" then
        warn("[Webhook] Telegram not configured!")
        return false
    end
    
    local url = string.format("https://api.telegram.org/bot%s/sendMessage", telegramBotToken)
    local data = {
        chat_id = telegramChatId,
        text = "🎮 MM2 Farm Report\n\n" .. message,
        parse_mode = "Markdown"
    }
    
    local success = pcall(function()
        request({
            Url = url,
            Method = "POST",
            Headers = { ["Content-Type"] = "application/json" },
            Body = HttpService:JSONEncode(data)
        })
    end)
    
    if success then
        print("[Webhook] Telegram sent!")
        return true
    else
        warn("[Webhook] Telegram failed")
        return false
    end
end

local function sendWebhook(message)
    if webhookType == "Discord" then
        return sendDiscordWebhook(message)
    elseif webhookType == "Telegram" then
        return sendTelegramMessage(message)
    end
    return false
end

local function generateFarmReport()
    local elapsed = totalFarmTime + (farming and (tick() - farmStartTime) or 0)
    local days = math.floor(elapsed / 86400)
    local hours = math.floor((elapsed % 86400) / 3600)
    local minutes = math.floor((elapsed % 3600) / 60)
    local seconds = math.floor(elapsed % 60)
    
    return string.format(
        "**Farm Status:**\n• Session: %d / %d\n• Total: %d\n• Time: %dd %dh %dm %ds\n• Status: %s",
        sessionCoinsCollected, coinLimit, totalCoinsCollected,
        days, hours, minutes, seconds,
        farming and "🟢 Active" or "🔴 Stopped"
    )
end

-- ═══════════════════════════════════════════════════════════════
-- MINIMALIST GUI
-- ═══════════════════════════════════════════════════════════════

local function getChar()
    local char = LocalPlayer.Character or LocalPlayer.CharacterAdded:Wait()
    local hrp = char:WaitForChild("HumanoidRootPart")
    local humanoid = char:FindFirstChildOfClass("Humanoid")
    return char, hrp, humanoid
end

character, hrp, humanoid = getChar()

local parentGui
pcall(function() parentGui = game:GetService("CoreGui") end)
if not parentGui then parentGui = LocalPlayer:WaitForChild("PlayerGui") end

local screenGui = Instance.new("ScreenGui")
screenGui.Name = "MM2FarmGUI"
screenGui.ResetOnSpawn = false
screenGui.Parent = parentGui

-- Animation helper
local function tween(object, properties, duration, style)
    TweenService:Create(
        object, 
        TweenInfo.new(duration or 0.3, style or Enum.EasingStyle.Quad, Enum.EasingDirection.Out),
        properties
    ):Play()
end

-- ═══════════════════════════════════════════════════════════════
-- MAIN CONTAINER
-- ═══════════════════════════════════════════════════════════════

local main = Instance.new("Frame")
main.Name = "Main"
main.Size = UDim2.new(0, 360, 0, 480)
main.Position = UDim2.new(0.5, -180, 0.5, -240)
main.BackgroundColor3 = Color3.fromRGB(18, 18, 24)
main.BorderSizePixel = 0
main.Active = true
main.Draggable = true
main.Parent = screenGui
main.ClipsDescendants = true

local mainCorner = Instance.new("UICorner", main)
mainCorner.CornerRadius = UDim.new(0, 16)

local mainShadow = Instance.new("ImageLabel", main)
mainShadow.Name = "Shadow"
mainShadow.Size = UDim2.new(1, 40, 1, 40)
mainShadow.Position = UDim2.new(0, -20, 0, -20)
mainShadow.BackgroundTransparency = 1
mainShadow.Image = "rbxasset://textures/ui/GuiImagePlaceholder.png"
mainShadow.ImageColor3 = Color3.fromRGB(0, 0, 0)
mainShadow.ImageTransparency = 0.7
mainShadow.ScaleType = Enum.ScaleType.Slice
mainShadow.SliceCenter = Rect.new(10, 10, 118, 118)
mainShadow.ZIndex = 0

local glow = Instance.new("UIStroke", main)
glow.Color = Color3.fromRGB(88, 166, 255)
glow.Thickness = 1.5
glow.Transparency = 0.5

-- Animated glow effect
task.spawn(function()
    while task.wait(0.05) do
        local pulse = 0.3 + (math.sin(tick() * 2) * 0.2)
        glow.Transparency = pulse
    end
end)

-- ═══════════════════════════════════════════════════════════════
-- HEADER
-- ═══════════════════════════════════════════════════════════════

local header = Instance.new("Frame", main)
header.Name = "Header"
header.Size = UDim2.new(1, 0, 0, 50)
header.BackgroundTransparency = 1

local titleLabel = Instance.new("TextLabel", header)
titleLabel.Size = UDim2.new(1, -60, 1, 0)
titleLabel.Position = UDim2.new(0, 20, 0, 0)
titleLabel.BackgroundTransparency = 1
titleLabel.Text = "MM2 Farm"
titleLabel.TextColor3 = Color3.fromRGB(255, 255, 255)
titleLabel.Font = Enum.Font.GothamBold
titleLabel.TextSize = 20
titleLabel.TextXAlignment = Enum.TextXAlignment.Left

local closeBtn = Instance.new("TextButton", header)
closeBtn.Size = UDim2.new(0, 30, 0, 30)
closeBtn.Position = UDim2.new(1, -40, 0, 10)
closeBtn.BackgroundColor3 = Color3.fromRGB(30, 30, 38)
closeBtn.Text = "×"
closeBtn.TextColor3 = Color3.fromRGB(200, 200, 200)
closeBtn.Font = Enum.Font.GothamBold
closeBtn.TextSize = 20
closeBtn.AutoButtonColor = false
Instance.new("UICorner", closeBtn).CornerRadius = UDim.new(1, 0)

closeBtn.MouseEnter:Connect(function()
    tween(closeBtn, {BackgroundColor3 = Color3.fromRGB(255, 80, 80)})
end)
closeBtn.MouseLeave:Connect(function()
    tween(closeBtn, {BackgroundColor3 = Color3.fromRGB(30, 30, 38)})
end)
closeBtn.MouseButton1Click:Connect(function()
    tween(main, {Size = UDim2.new(0, 0, 0, 0)}, 0.3)
    task.wait(0.3)
    main.Visible = false
    main.Size = UDim2.new(0, 360, 0, 480)
end)

-- ═══════════════════════════════════════════════════════════════
-- TABS
-- ═══════════════════════════════════════════════════════════════

local tabContainer = Instance.new("Frame", main)
tabContainer.Name = "Tabs"
tabContainer.Size = UDim2.new(1, -40, 0, 36)
tabContainer.Position = UDim2.new(0, 20, 0, 60)
tabContainer.BackgroundColor3 = Color3.fromRGB(25, 25, 33)
tabContainer.BorderSizePixel = 0
Instance.new("UICorner", tabContainer).CornerRadius = UDim.new(0, 10)

local tabList = Instance.new("UIListLayout", tabContainer)
tabList.FillDirection = Enum.FillDirection.Horizontal
tabList.HorizontalAlignment = Enum.HorizontalAlignment.Center
tabList.SortOrder = Enum.SortOrder.LayoutOrder
tabList.Padding = UDim.new(0, 4)

local tabPadding = Instance.new("UIPadding", tabContainer)
tabPadding.PaddingLeft = UDim.new(0, 4)
tabPadding.PaddingRight = UDim.new(0, 4)
tabPadding.PaddingTop = UDim.new(0, 4)
tabPadding.PaddingBottom = UDim.new(0, 4)

local activeTab = "Farm"

local function createTab(name, icon)
    local tab = Instance.new("TextButton", tabContainer)
    tab.Name = name
    tab.Size = UDim2.new(0.48, 0, 1, 0)
    tab.BackgroundColor3 = (name == "Farm") and Color3.fromRGB(88, 166, 255) or Color3.fromRGB(30, 30, 38)
    tab.Text = icon .. " " .. name
    tab.TextColor3 = Color3.fromRGB(255, 255, 255)
    tab.Font = Enum.Font.GothamBold
    tab.TextSize = 13
    tab.AutoButtonColor = false
    Instance.new("UICorner", tab).CornerRadius = UDim.new(0, 8)
    
    return tab
end

local farmTab = createTab("Farm", "⚡")
local webhookTab = createTab("Webhook", "📡")

-- ═══════════════════════════════════════════════════════════════
-- CONTENT CONTAINER
-- ═══════════════════════════════════════════════════════════════

local content = Instance.new("Frame", main)
content.Name = "Content"
content.Size = UDim2.new(1, -40, 1, -116)
content.Position = UDim2.new(0, 20, 0, 106)
content.BackgroundTransparency = 1
content.ClipsDescendants = true

-- ═══════════════════════════════════════════════════════════════
-- FARM CONTENT
-- ═══════════════════════════════════════════════════════════════

local farmContent = Instance.new("Frame", content)
farmContent.Name = "FarmContent"
farmContent.Size = UDim2.new(1, 0, 1, 0)
farmContent.BackgroundTransparency = 1

-- Stats Card
local statsCard = Instance.new("Frame", farmContent)
statsCard.Size = UDim2.new(1, 0, 0, 110)
statsCard.BackgroundColor3 = Color3.fromRGB(25, 25, 33)
statsCard.BorderSizePixel = 0
Instance.new("UICorner", statsCard).CornerRadius = UDim.new(0, 12)

local statsGlow = Instance.new("UIStroke", statsCard)
statsGlow.Color = Color3.fromRGB(88, 166, 255)
statsGlow.Thickness = 1
statsGlow.Transparency = 0.8

local statsPadding = Instance.new("UIPadding", statsCard)
statsPadding.PaddingLeft = UDim.new(0, 15)
statsPadding.PaddingRight = UDim.new(0, 15)
statsPadding.PaddingTop = UDim.new(0, 12)
statsPadding.PaddingBottom = UDim.new(0, 12)

local coinsLabel = Instance.new("TextLabel", statsCard)
coinsLabel.Size = UDim2.new(1, 0, 0, 24)
coinsLabel.BackgroundTransparency = 1
coinsLabel.Text = "💰 0 / 40"
coinsLabel.TextColor3 = Color3.fromRGB(255, 215, 0)
coinsLabel.Font = Enum.Font.GothamBold
coinsLabel.TextSize = 18
coinsLabel.TextXAlignment = Enum.TextXAlignment.Left

local totalLabel = Instance.new("TextLabel", statsCard)
totalLabel.Size = UDim2.new(1, 0, 0, 18)
totalLabel.Position = UDim2.new(0, 0, 0, 28)
totalLabel.BackgroundTransparency = 1
totalLabel.Text = "Total: 0 coins"
totalLabel.TextColor3 = Color3.fromRGB(150, 150, 160)
totalLabel.Font = Enum.Font.Gotham
totalLabel.TextSize = 12
totalLabel.TextXAlignment = Enum.TextXAlignment.Left

local timeLabel = Instance.new("TextLabel", statsCard)
timeLabel.Size = UDim2.new(1, 0, 0, 18)
timeLabel.Position = UDim2.new(0, 0, 0, 50)
timeLabel.BackgroundTransparency = 1
timeLabel.Text = "⏱️ 0h 0m 0s"
timeLabel.TextColor3 = Color3.fromRGB(180, 180, 190)
timeLabel.Font = Enum.Font.Gotham
totalLabel.TextSize = 12
timeLabel.TextXAlignment = Enum.TextXAlignment.Left

local statusLabel = Instance.new("TextLabel", statsCard)
statusLabel.Size = UDim2.new(1, 0, 0, 18)
statusLabel.Position = UDim2.new(0, 0, 0, 72)
statusLabel.BackgroundTransparency = 1
statusLabel.Text = "🟢 Ready"
statusLabel.TextColor3 = Color3.fromRGB(100, 220, 100)
statusLabel.Font = Enum.Font.GothamBold
statusLabel.TextSize = 11
statusLabel.TextXAlignment = Enum.TextXAlignment.Left

-- Button helper
local function createButton(parent, text, yPos, color, height)
    local btn = Instance.new("TextButton", parent)
    btn.Size = UDim2.new(1, 0, 0, height or 40)
    btn.Position = UDim2.new(0, 0, 0, yPos)
    btn.BackgroundColor3 = color
    btn.Text = text
    btn.TextColor3 = Color3.fromRGB(255, 255, 255)
    btn.Font = Enum.Font.GothamBold
    btn.TextSize = 14
    btn.AutoButtonColor = false
    Instance.new("UICorner", btn).CornerRadius = UDim.new(0, 10)
    
    local btnGlow = Instance.new("UIStroke", btn)
    btnGlow.Color = color
    btnGlow.Thickness = 0
    btnGlow.Transparency = 1
    
    btn.MouseEnter:Connect(function()
        tween(btn, {BackgroundColor3 = Color3.new(
            math.min(color.R * 1.2, 1),
            math.min(color.G * 1.2, 1),
            math.min(color.B * 1.2, 1)
        )}, 0.2)
        tween(btnGlow, {Thickness = 2, Transparency = 0.5}, 0.2)
    end)
    
    btn.MouseLeave:Connect(function()
        tween(btn, {BackgroundColor3 = color}, 0.2)
        tween(btnGlow, {Thickness = 0, Transparency = 1}, 0.2)
    end)
    
    return btn
end

local farmBtn = createButton(farmContent, "▶ Start Farm", 120, Color3.fromRGB(88, 166, 255), 45)

-- Small buttons row
local btnRow = Instance.new("Frame", farmContent)
btnRow.Size = UDim2.new(1, 0, 0, 36)
btnRow.Position = UDim2.new(0, 0, 0, 175)
btnRow.BackgroundTransparency = 1

local afkBtn = createButton(btnRow, "Anti-AFK", 0, Color3.fromRGB(70, 130, 200), 36)
afkBtn.Size = UDim2.new(0.48, 0, 1, 0)

local afkModeBtn = createButton(btnRow, "AFK Mode", 0, Color3.fromRGB(100, 120, 180), 36)
afkModeBtn.Size = UDim2.new(0.48, 0, 1, 0)
afkModeBtn.Position = UDim2.new(0.52, 0, 0, 0)

local espBtn = createButton(farmContent, "👁️ Coin ESP", 221, Color3.fromRGB(120, 100, 200), 36)
local resetBtn = createButton(farmContent, "🔄 Reset Session", 267, Color3.fromRGB(200, 100, 100), 36)

-- Speed control
local speedFrame = Instance.new("Frame", farmContent)
speedFrame.Size = UDim2.new(1, 0, 0, 60)
speedFrame.Position = UDim2.new(0, 0, 0, 313)
speedFrame.BackgroundTransparency = 1

local speedTitle = Instance.new("TextLabel", speedFrame)
speedTitle.Size = UDim2.new(1, 0, 0, 20)
speedTitle.BackgroundTransparency = 1
speedTitle.Text = "⚡ Speed: 35"
speedTitle.TextColor3 = Color3.fromRGB(200, 200, 210)
speedTitle.Font = Enum.Font.GothamBold
speedTitle.TextSize = 12
speedTitle.TextXAlignment = Enum.TextXAlignment.Left

local speedSlider = Instance.new("Frame", speedFrame)
speedSlider.Size = UDim2.new(1, 0, 0, 8)
speedSlider.Position = UDim2.new(0, 0, 0, 30)
speedSlider.BackgroundColor3 = Color3.fromRGB(35, 35, 45)
speedSlider.BorderSizePixel = 0
Instance.new("UICorner", speedSlider).CornerRadius = UDim.new(1, 0)

local speedFill = Instance.new("Frame", speedSlider)
speedFill.Size = UDim2.new(0.5, 0, 1, 0)
speedFill.BackgroundColor3 = Color3.fromRGB(88, 166, 255)
speedFill.BorderSizePixel = 0
Instance.new("UICorner", speedFill).CornerRadius = UDim.new(1, 0)

local speedDot = Instance.new("Frame", speedSlider)
speedDot.Size = UDim2.new(0, 20, 0, 20)
speedDot.Position = UDim2.new(0.5, -10, 0.5, -10)
speedDot.BackgroundColor3 = Color3.fromRGB(255, 255, 255)
speedDot.BorderSizePixel = 0
Instance.new("UICorner", speedDot).CornerRadius = UDim.new(1, 0)

local speedInput = Instance.new("TextBox", speedFrame)
speedInput.Size = UDim2.new(0, 70, 0, 28)
speedInput.Position = UDim2.new(1, -70, 0, 46)
speedInput.BackgroundColor3 = Color3.fromRGB(35, 35, 45)
speedInput.Text = "35"
speedInput.TextColor3 = Color3.fromRGB(255, 255, 255)
speedInput.Font = Enum.Font.GothamBold
speedInput.TextSize = 13
speedInput.ClearTextOnFocus = false
Instance.new("UICorner", speedInput).CornerRadius = UDim.new(0, 8)

-- ═══════════════════════════════════════════════════════════════
-- WEBHOOK CONTENT
-- ═══════════════════════════════════════════════════════════════

local webhookContent = Instance.new("Frame", content)
webhookContent.Name = "WebhookContent"
webhookContent.Size = UDim2.new(1, 0, 1, 0)
webhookContent.BackgroundTransparency = 1
webhookContent.Visible = false

-- Method selector
local methodFrame = Instance.new("Frame", webhookContent)
methodFrame.Size = UDim2.new(1, 0, 0, 36)
methodFrame.BackgroundTransparency = 1

local discordBtn = createButton(methodFrame, "Discord", 0, Color3.fromRGB(88, 101, 242), 36)
discordBtn.Size = UDim2.new(0.48, 0, 1, 0)

local telegramBtn = createButton(methodFrame, "Telegram", 0, Color3.fromRGB(50, 50, 60), 36)
telegramBtn.Size = UDim2.new(0.48, 0, 1, 0)
telegramBtn.Position = UDim2.new(0.52, 0, 0, 0)

-- Discord config
local discordConfig = Instance.new("Frame", webhookContent)
discordConfig.Size = UDim2.new(1, 0, 0, 100)
discordConfig.Position = UDim2.new(0, 0, 0, 46)
discordConfig.BackgroundColor3 = Color3.fromRGB(25, 25, 33)
discordConfig.BorderSizePixel = 0
Instance.new("UICorner", discordConfig).CornerRadius = UDim.new(0, 12)

local dcPad = Instance.new("UIPadding", discordConfig)
dcPad.PaddingLeft = UDim.new(0, 12)
dcPad.PaddingRight = UDim.new(0, 12)
dcPad.PaddingTop = UDim.new(0, 10)
dcPad.PaddingBottom = UDim.new(0, 10)

local dcLabel = Instance.new("TextLabel", discordConfig)
dcLabel.Size = UDim2.new(1, 0, 0, 16)
dcLabel.BackgroundTransparency = 1
dcLabel.Text = "Webhook URL"
dcLabel.TextColor3 = Color3.fromRGB(180, 180, 190)
dcLabel.Font = Enum.Font.GothamBold
dcLabel.TextSize = 11
dcLabel.TextXAlignment = Enum.TextXAlignment.Left

local dcInput = Instance.new("TextBox", discordConfig)
dcInput.Size = UDim2.new(1, 0, 0, 60)
dcInput.Position = UDim2.new(0, 0, 0, 24)
dcInput.BackgroundColor3 = Color3.fromRGB(35, 35, 45)
dcInput.Text = ""
dcInput.PlaceholderText = "https://discord.com/api/webhooks/..."
dcInput.TextColor3 = Color3.fromRGB(200, 200, 210)
dcInput.Font = Enum.Font.Gotham
dcInput.TextSize = 10
dcInput.TextWrapped = true
dcInput.TextYAlignment = Enum.TextYAlignment.Top
dcInput.MultiLine = true
dcInput.ClearTextOnFocus = false
Instance.new("UICorner", dcInput).CornerRadius = UDim.new(0, 8)
local dcInPad = Instance.new("UIPadding", dcInput)
dcInPad.PaddingLeft = UDim.new(0, 8)
dcInPad.PaddingTop = UDim.new(0, 6)

dcInput.FocusLost:Connect(function()
    webhookUrl = dcInput.Text
end)

-- Telegram config
local tgConfig = Instance.new("Frame", webhookContent)
tgConfig.Size = UDim2.new(1, 0, 0, 160)
tgConfig.Position = UDim2.new(0, 0, 0, 46)
tgConfig.BackgroundColor3 = Color3.fromRGB(25, 25, 33)
tgConfig.BorderSizePixel = 0
tgConfig.Visible = false
Instance.new("UICorner", tgConfig).CornerRadius = UDim.new(0, 12)

local tgPad = Instance.new("UIPadding", tgConfig)
tgPad.PaddingLeft = UDim.new(0, 12)
tgPad.PaddingRight = UDim.new(0, 12)
tgPad.PaddingTop = UDim.new(0, 10)
tgPad.PaddingBottom = UDim.new(0, 10)

local tgLabel1 = Instance.new("TextLabel", tgConfig)
tgLabel1.Size = UDim2.new(1, 0, 0, 16)
tgLabel1.BackgroundTransparency = 1
tgLabel1.Text = "Bot Token"
tgLabel1.TextColor3 = Color3.fromRGB(180, 180, 190)
tgLabel1.Font = Enum.Font.GothamBold
tgLabel1.TextSize = 11
tgLabel1.TextXAlignment = Enum.TextXAlignment.Left

local tgInput1 = Instance.new("TextBox", tgConfig)
tgInput1.Size = UDim2.new(1, 0, 0, 50)
tgInput1.Position = UDim2.new(0, 0, 0, 24)
tgInput1.BackgroundColor3 = Color3.fromRGB(35, 35, 45)
tgInput1.PlaceholderText = "1234567890:ABC..."
tgInput1.TextColor3 = Color3.fromRGB(200, 200, 210)
tgInput1.Font = Enum.Font.Gotham
tgInput1.TextSize = 10
tgInput1.TextWrapped = true
tgInput1.TextYAlignment = Enum.TextYAlignment.Top
tgInput1.MultiLine = true
tgInput1.ClearTextOnFocus = false
Instance.new("UICorner", tgInput1).CornerRadius = UDim.new(0, 8)
local tg1Pad = Instance.new("UIPadding", tgInput1)
tg1Pad.PaddingLeft = UDim.new(0, 8)
tg1Pad.PaddingTop = UDim.new(0, 6)

tgInput1.FocusLost:Connect(function()
    telegramBotToken = tgInput1.Text
end)

local tgLabel2 = Instance.new("TextLabel", tgConfig)
tgLabel2.Size = UDim2.new(1, 0, 0, 16)
tgLabel2.Position = UDim2.new(0, 0, 0, 82)
tgLabel2.BackgroundTransparency = 1
tgLabel2.Text = "Chat ID"
tgLabel2.TextColor3 = Color3.fromRGB(180, 180, 190)
tgLabel2.Font = Enum.Font.GothamBold
tgLabel2.TextSize = 11
tgLabel2.TextXAlignment = Enum.TextXAlignment.Left

local tgInput2 = Instance.new("TextBox", tgConfig)
tgInput2.Size = UDim2.new(1, 0, 0, 32)
tgInput2.Position = UDim2.new(0, 0, 0, 106)
tgInput2.BackgroundColor3 = Color3.fromRGB(35, 35, 45)
tgInput2.PlaceholderText = "123456789"
tgInput2.TextColor3 = Color3.fromRGB(200, 200, 210)
tgInput2.Font = Enum.Font.Gotham
tgInput2.TextSize = 10
tgInput2.ClearTextOnFocus = false
Instance.new("UICorner", tgInput2).CornerRadius = UDim.new(0, 8)

tgInput2.FocusLost:Connect(function()
    telegramChatId = tgInput2.Text
end)

-- Send button
local sendBtn = createButton(webhookContent, "📤 Send Report", 156, Color3.fromRGB(88, 166, 255), 42)

sendBtn.MouseButton1Click:Connect(function()
    local report = generateFarmReport()
    local success = sendWebhook(report)
    
    if success then
        sendBtn.Text = "✓ Sent!"
        tween(sendBtn, {BackgroundColor3 = Color3.fromRGB(80, 200, 100)})
    else
        sendBtn.Text = "✗ Failed"
        tween(sendBtn, {BackgroundColor3 = Color3.fromRGB(200, 80, 80)})
    end
    
    task.wait(2)
    sendBtn.Text = "📤 Send Report"
    tween(sendBtn, {BackgroundColor3 = Color3.fromRGB(88, 166, 255)})
end)

-- Auto-send toggle
local autoFrame = Instance.new("Frame", webhookContent)
autoFrame.Size = UDim2.new(1, 0, 0, 50)
autoFrame.Position = UDim2.new(0, 0, 0, 208)
autoFrame.BackgroundColor3 = Color3.fromRGB(25, 25, 33)
autoFrame.BorderSizePixel = 0
Instance.new("UICorner", autoFrame).CornerRadius = UDim.new(0, 12)

local autoLabel = Instance.new("TextLabel", autoFrame)
autoLabel.Size = UDim2.new(0.7, 0, 1, 0)
autoLabel.Position = UDim2.new(0, 15, 0, 0)
autoLabel.BackgroundTransparency = 1
autoLabel.Text = "Auto-Send on Stop"
autoLabel.TextColor3 = Color3.fromRGB(200, 200, 210)
autoLabel.Font = Enum.Font.GothamBold
autoLabel.TextSize = 12
autoLabel.TextXAlignment = Enum.TextXAlignment.Left

local autoToggle = Instance.new("TextButton", autoFrame)
autoToggle.Size = UDim2.new(0, 50, 0, 28)
autoToggle.Position = UDim2.new(1, -60, 0.5, -14)
autoToggle.BackgroundColor3 = Color3.fromRGB(80, 200, 100)
autoToggle.Text = "ON"
autoToggle.TextColor3 = Color3.fromRGB(255, 255, 255)
autoToggle.Font = Enum.Font.GothamBold
autoToggle.TextSize = 11
autoToggle.AutoButtonColor = false
Instance.new("UICorner", autoToggle).CornerRadius = UDim.new(0, 8)

autoToggle.MouseButton1Click:Connect(function()
    autoSendEnabled = not autoSendEnabled
    if autoSendEnabled then
        autoToggle.Text = "ON"
        tween(autoToggle, {BackgroundColor3 = Color3.fromRGB(80, 200, 100)})
    else
        autoToggle.Text = "OFF"
        tween(autoToggle, {BackgroundColor3 = Color3.fromRGB(200, 80, 80)})
    end
end)

-- ═══════════════════════════════════════════════════════════════
-- TAB SWITCHING
-- ═══════════════════════════════════════════════════════════════

local function switchTab(tab)
    if tab == activeTab then return end
    activeTab = tab
    
    if tab == "Farm" then
        tween(farmTab, {BackgroundColor3 = Color3.fromRGB(88, 166, 255)})
        tween(webhookTab, {BackgroundColor3 = Color3.fromRGB(30, 30, 38)})
        
        webhookContent.Visible = false
        farmContent.Visible = true
    else
        tween(webhookTab, {BackgroundColor3 = Color3.fromRGB(88, 166, 255)})
        tween(farmTab, {BackgroundColor3 = Color3.fromRGB(30, 30, 38)})
        
        farmContent.Visible = false
        webhookContent.Visible = true
    end
end

farmTab.MouseButton1Click:Connect(function() switchTab("Farm") end)
webhookTab.MouseButton1Click:Connect(function() switchTab("Webhook") end)

-- Webhook method switching
discordBtn.MouseButton1Click:Connect(function()
    webhookType = "Discord"
    tween(discordBtn, {BackgroundColor3 = Color3.fromRGB(88, 101, 242)})
    tween(telegramBtn, {BackgroundColor3 = Color3.fromRGB(50, 50, 60)})
    discordConfig.Visible = true
    tgConfig.Visible = false
    sendBtn.Position = UDim2.new(0, 0, 0, 156)
    autoFrame.Position = UDim2.new(0, 0, 0, 208)
end)

telegramBtn.MouseButton1Click:Connect(function()
    webhookType = "Telegram"
    tween(telegramBtn, {BackgroundColor3 = Color3.fromRGB(0, 136, 204)})
    tween(discordBtn, {BackgroundColor3 = Color3.fromRGB(50, 50, 60)})
    tgConfig.Visible = true
    discordConfig.Visible = false
    sendBtn.Position = UDim2.new(0, 0, 0, 216)
    autoFrame.Position = UDim2.new(0, 0, 0, 268)
end)

-- ═══════════════════════════════════════════════════════════════
-- TOGGLE BUTTON
-- ═══════════════════════════════════════════════════════════════

local toggleBtn = Instance.new("TextButton")
toggleBtn.Size = UDim2.new(0, 56, 0, 56)
toggleBtn.Position = UDim2.new(1, -76, 1, -76)
toggleBtn.BackgroundColor3 = Color3.fromRGB(88, 166, 255)
toggleBtn.Text = "⚡"
toggleBtn.TextColor3 = Color3.fromRGB(255, 255, 255)
toggleBtn.Font = Enum.Font.GothamBold
toggleBtn.TextSize = 24
toggleBtn.Active = true
toggleBtn.Draggable = true
toggleBtn.Parent = screenGui
Instance.new("UICorner", toggleBtn).CornerRadius = UDim.new(1, 0)

local toggleGlow = Instance.new("UIStroke", toggleBtn)
toggleGlow.Color = Color3.fromRGB(88, 166, 255)
toggleGlow.Thickness = 3
toggleGlow.Transparency = 0.5

toggleBtn.MouseButton1Click:Connect(function()
    main.Visible = not main.Visible
    if main.Visible then
        main.Size = UDim2.new(0, 0, 0, 0)
        tween(main, {Size = UDim2.new(0, 360, 0, 480)}, 0.4, Enum.EasingStyle.Back)
    else
        tween(main, {Size = UDim2.new(0, 0, 0, 0)}, 0.3)
    end
end)

main.Visible = false

-- ═══════════════════════════════════════════════════════════════
-- CORE FARM FUNCTIONS
-- ═══════════════════════════════════════════════════════════════

local flySpeed = 35
local coinCache = {}
local lastFullScan = 0
local SCAN_INTERVAL = 2

local function updateCoinCache()
    local newCache = {}
    for _, obj in ipairs(workspace:GetDescendants()) do
        if obj:IsA("BasePart") and obj.Name:lower():find("coin") then
            newCache[obj] = true
            if not coinCache[obj] then
                obj.AncestryChanged:Connect(function()
                    coinCache[obj] = nil
                end)
            end
        end
    end
    coinCache = newCache
    lastFullScan = tick()
end

updateCoinCache()

local function getCoins()
    if tick() - lastFullScan > SCAN_INTERVAL then
        updateCoinCache()
    end

    local coins = {}
    for coin, _ in pairs(coinCache) do
        if coin and coin.Parent and coin:IsDescendantOf(workspace) then
            table.insert(coins, coin)
        else
            coinCache[coin] = nil
        end
    end
    return coins
end

local function updateSpeed(value)
    flySpeed = math.clamp(math.floor(value), 25, 45)
    speedInput.Text = tostring(flySpeed)
    speedTitle.Text = "⚡ Speed: " .. flySpeed
    local percent = (flySpeed - 25) / 20
    speedFill.Size = UDim2.new(percent, 0, 1, 0)
    speedDot.Position = UDim2.new(percent, -10, 0.5, -10)

    if flySpeed <= 30 then
        tween(speedFill, {BackgroundColor3 = Color3.fromRGB(80, 200, 120)})
    elseif flySpeed <= 37 then
        tween(speedFill, {BackgroundColor3 = Color3.fromRGB(88, 166, 255)})
    else
        tween(speedFill, {BackgroundColor3 = Color3.fromRGB(255, 140, 80)})
    end
end

local dragging = false
local dragInput
local dragStart
local startPos

local function updateDrag(input)
    local relativeX = input.Position.X - speedSlider.AbsolutePosition.X
    local percent = math.clamp(relativeX / speedSlider.AbsoluteSize.X, 0, 1)
    local value = 25 + (percent * 20)
    updateSpeed(value)
end

speedDot.InputBegan:Connect(function(input)
    if input.UserInputType == Enum.UserInputType.MouseButton1 or input.UserInputType == Enum.UserInputType.Touch then
        dragging = true
        dragStart = input.Position
        startPos = speedDot.Position
        
        input.Changed:Connect(function()
            if input.UserInputState == Enum.UserInputState.End then
                dragging = false
            end
        end)
    end
end)

game:GetService("UserInputService").InputChanged:Connect(function(input)
    if dragging and (input.UserInputType == Enum.UserInputType.MouseMovement or input.UserInputType == Enum.UserInputType.Touch) then
        updateDrag(input)
    end
end)

speedInput.FocusLost:Connect(function()
    local value = tonumber(speedInput.Text)
    if value then
        updateSpeed(value)
    else
        speedInput.Text = tostring(flySpeed)
    end
end)

-- Update displays
task.spawn(function()
    while task.wait(0.5) do
        coinsLabel.Text = string.format("💰 %d / %d", sessionCoinsCollected, coinLimit)
        totalLabel.Text = string.format("Total: %d coins", totalCoinsCollected)
        
        if farming then
            local elapsed = totalFarmTime + (tick() - farmStartTime)
            local hours = math.floor(elapsed / 3600)
            local minutes = math.floor((elapsed % 3600) / 60)
            local seconds = math.floor(elapsed % 60)
            timeLabel.Text = string.format("⏱️ %dh %dm %ds", hours, minutes, seconds)
        end
    end
end)

-- Noclip
local noclipConn
local function enableNoclip()
    if noclipConn then return end
    noclipConn = RunService.Stepped:Connect(function()
        if not character or not character.Parent then return end
        for _, part in ipairs(character:GetDescendants()) do
            if part:IsA("BasePart") then
                part.CanCollide = false
            end
        end
    end)
end

local function disableNoclip()
    if noclipConn then
        noclipConn:Disconnect()
        noclipConn = nil
    end
end

-- Anti-gravity
local bodyVelocity
local function enableAntiGravity()
    if bodyVelocity and bodyVelocity.Parent then return end
    if bodyVelocity then bodyVelocity:Destroy() end

    bodyVelocity = Instance.new("BodyVelocity")
    bodyVelocity.Velocity = Vector3.new(0, 0, 0)
    bodyVelocity.MaxForce = Vector3.new(0, math.huge, 0)
    bodyVelocity.Parent = hrp
end

local function disableAntiGravity()
    if bodyVelocity then
        bodyVelocity:Destroy()
        bodyVelocity = nil
    end
end

-- Coin collection
local function stealthCollectCoin(coinPart)
    if not coinPart or not hrp or not character then return false end
    if not coinPart:IsDescendantOf(workspace) then return false end
    if coinPart.Transparency ~= 0 then return false end

    local coinPos = coinPart.Position
    local undergroundPos = Vector3.new(coinPos.X, undergroundDepth, coinPos.Z)

    local distance1 = (hrp.Position - undergroundPos).Magnitude
    local time1 = math.clamp(distance1 / flySpeed, 0.1, 2.5)

    local tween1 = TweenService:Create(hrp, TweenInfo.new(time1, Enum.EasingStyle.Linear), {
        CFrame = CFrame.new(undergroundPos)
    })

    local success1 = pcall(function()
        tween1:Play()
        tween1.Completed:Wait()
    end)

    if not success1 or not coinPart.Parent then return false end
    if coinPart.Transparency ~= 0 then return false end

    local collected = false

    for attempt = 1, 4 do
        if coinPart.Transparency ~= 0 or not coinPart.Parent then
            collected = true
            break
        end

        local heightOffset = (attempt - 1) * 0.4
        local targetY = coinPos.Y + collectHeight + heightOffset
        local coinLevelPos = Vector3.new(coinPos.X, targetY, coinPos.Z)

        local distance2 = (hrp.Position - coinLevelPos).Magnitude
        local time2 = math.clamp(distance2 / flySpeed, 0.15, 0.8)

        local tween2 = TweenService:Create(hrp, TweenInfo.new(time2, Enum.EasingStyle.Linear), {
            CFrame = CFrame.new(coinLevelPos)
        })

        pcall(function()
            tween2:Play()
            tween2.Completed:Wait()
        end)

        task.wait(0.12)

        if coinPart.Transparency ~= 0 or not coinPart.Parent then
            collected = true
            break
        end
    end

    local backPos = Vector3.new(hrp.Position.X, undergroundDepth, hrp.Position.Z)
    local distance3 = (hrp.Position - backPos).Magnitude
    local time3 = math.clamp(distance3 / (flySpeed * 1.5), 0.1, 0.6)

    local tween3 = TweenService:Create(hrp, TweenInfo.new(time3, Enum.EasingStyle.Linear), {
        CFrame = CFrame.new(backPos)
    })

    pcall(function()
        tween3:Play()
        tween3.Completed:Wait()
    end)

    return collected
end

-- Farm control
local farmTask

local function findMapModel()
    for _, child in ipairs(workspace:GetChildren()) do
        if child:IsA("Model") and child:GetAttribute("MapID") then
            return child
        end
    end
    return nil
end

local function waitForRound()
    statusLabel.Text = "🔍 Searching map..."

    local mapModel = findMapModel()
    while not mapModel and farming and afkModeEnabled do
        mapModel = findMapModel()
        task.wait(1)
    end

    if not farming or not afkModeEnabled then
        return false
    end

    local mapPos = mapModel:IsA("Model") and mapModel:GetPivot().Position or mapModel.Position
    statusLabel.Text = "👻 Hiding..."

    enableNoclip()
    enableAntiGravity()

    local hidePos = Vector3.new(mapPos.X + math.random(-20, 20), undergroundDepth, mapPos.Z + math.random(-20, 20))
    hrp.CFrame = CFrame.new(hidePos)

    local roundTimer = workspace:FindFirstChild("RoundTimerPart")
    while not roundTimer and farming and afkModeEnabled do
        hrp.CFrame = CFrame.new(hidePos)
        roundTimer = workspace:FindFirstChild("RoundTimerPart")
        task.wait(0.5)
    end

    if not farming or not afkModeEnabled then
        return false
    end

    while farming and afkModeEnabled do
        local timeAttr = roundTimer:GetAttribute("Time")
        if timeAttr and timeAttr ~= -1 then
            statusLabel.Text = "⚡ Round started!"
            return true
        end

        hrp.CFrame = CFrame.new(hidePos)
        task.wait(0.5)
    end

    return false
end

local function startFarm()
    if farming then return end
    farming = true
    farmStartTime = tick()

    pcall(function() humanoid.PlatformStand = true end)

    farmBtn.Text = "⏸ Stop Farm"
    tween(farmBtn, {BackgroundColor3 = Color3.fromRGB(200, 80, 80)})
    statusLabel.Text = "🟢 Farming..."

    farmTask = task.spawn(function()
        if afkModeEnabled then
            local roundReady = waitForRound()
            if not roundReady or not farming then
                if farming then stopFarm() end
                return
            end
        end

        enableNoclip()
        enableAntiGravity()

        hrp.CFrame = CFrame.new(hrp.Position.X, undergroundDepth, hrp.Position.Z)

        while farming do
            local success = pcall(function()
                if not hrp or not hrp.Parent or not humanoid or humanoid.Health <= 0 then
                    character, hrp, humanoid = getChar()
                    task.wait(1)
                    return
                end

                local coins = getCoins()
                local visibleCoins = {}

                for _, c in ipairs(coins) do
                    if c.Transparency == 0 then
                        table.insert(visibleCoins, c)
                    end
                end

                if #visibleCoins > 0 then
                    table.sort(visibleCoins, function(a, b)
                        local distA = (Vector3.new(a.Position.X, 0, a.Position.Z) - Vector3.new(hrp.Position.X, 0, hrp.Position.Z)).Magnitude
                        local distB = (Vector3.new(b.Position.X, 0, b.Position.Z) - Vector3.new(hrp.Position.X, 0, hrp.Position.Z)).Magnitude
                        return distA < distB
                    end)

                    statusLabel.Text = string.format("⚡ Collecting... (%d)", #visibleCoins)

                    local closest = visibleCoins[1]
                    local collected = stealthCollectCoin(closest)

                    if not collected then
                        task.wait(0.3)
                    end
                else
                    statusLabel.Text = "⏳ Waiting..."
                    task.wait(0.5)
                end
            end)

            if not success then task.wait(0.1) end
            task.wait(0.08)
        end
    end)
end

function stopFarm()
    farming = false
    if farmTask then task.cancel(farmTask) end
    totalFarmTime = totalFarmTime + (tick() - farmStartTime)

    disableNoclip()
    disableAntiGravity()

    pcall(function() humanoid.PlatformStand = false end)

    farmBtn.Text = "▶ Start Farm"
    tween(farmBtn, {BackgroundColor3 = Color3.fromRGB(88, 166, 255)})
    statusLabel.Text = "🔴 Stopped"
    
    if autoSendEnabled then
        task.spawn(function()
            task.wait(1)
            local report = generateFarmReport()
            local success = sendWebhook(report)
            if success then
                print("[Webhook] Auto-sent!")
            end
        end)
    end
end

-- Anti-AFK
local AntiAFK = false
local afkConn

local function startAFK()
    if AntiAFK then return end
    AntiAFK = true
    afkConn = LocalPlayer.Idled:Connect(function()
        VirtualUser:CaptureController()
        VirtualUser:ClickButton2(Vector2.new())
    end)
    afkBtn.Text = "✓ Anti-AFK"
    tween(afkBtn, {BackgroundColor3 = Color3.fromRGB(100, 180, 220)})
end

local function stopAFK()
    AntiAFK = false
    if afkConn then afkConn:Disconnect() end
    afkBtn.Text = "Anti-AFK"
    tween(afkBtn, {BackgroundColor3 = Color3.fromRGB(70, 130, 200)})
end

-- ESP
local espEnabled = false
local espHighlights = {}
local hue = 0
local espTask

local function createESP(part)
    if espHighlights[part] then return end

    local highlight = Instance.new("Highlight")
    highlight.Adornee = part
    highlight.FillTransparency = 0.7
    highlight.OutlineTransparency = 0
    highlight.Parent = part
    espHighlights[part] = highlight
end

local function enableESP()
    if espEnabled then return end
    espEnabled = true

    for _, part in ipairs(getCoins()) do
        createESP(part)
    end

    espTask = task.spawn(function()
        while espEnabled do
            hue = (hue + 2) % 360
            local color = Color3.fromHSV(hue / 360, 0.8, 1)

            for part, h in pairs(espHighlights) do
                if part.Parent and h.Parent then
                    h.OutlineColor = color
                    h.FillColor = color
                else
                    h:Destroy()
                    espHighlights[part] = nil
                end
            end

            if tick() % 1 < 0.3 then
                for _, part in ipairs(getCoins()) do
                    if not espHighlights[part] then
                        createESP(part)
                    end
                end
            end

            task.wait(0.03)
        end
    end)

    espBtn.Text = "✓ Coin ESP"
    tween(espBtn, {BackgroundColor3 = Color3.fromRGB(160, 120, 220)})
end

local function disableESP()
    espEnabled = false
    if espTask then task.cancel(espTask) end
    for _, h in pairs(espHighlights) do
        h:Destroy()
    end
    espHighlights = {}

    espBtn.Text = "👁️ Coin ESP"
    tween(espBtn, {BackgroundColor3 = Color3.fromRGB(120, 100, 200)})
end

-- Button connections
farmBtn.MouseButton1Click:Connect(function()
    if farming then
        stopFarm()
    else
        startFarm()
    end
end)

afkBtn.MouseButton1Click:Connect(function()
    if AntiAFK then
        stopAFK()
    else
        startAFK()
    end
end)

afkModeBtn.MouseButton1Click:Connect(function()
    if afkModeEnabled then
        afkModeEnabled = false
        afkModeBtn.Text = "AFK Mode"
        tween(afkModeBtn, {BackgroundColor3 = Color3.fromRGB(100, 120, 180)})
    else
        afkModeEnabled = true
        afkModeBtn.Text = "✓ AFK Mode"
        tween(afkModeBtn, {BackgroundColor3 = Color3.fromRGB(140, 160, 220)})
    end
end)

espBtn.MouseButton1Click:Connect(function()
    if espEnabled then
        disableESP()
    else
        enableESP()
    end
end)

resetBtn.MouseButton1Click:Connect(function()
    sessionCoinsCollected = 0
    resetBtn.Text = "✓ Reset!"
    tween(resetBtn, {BackgroundColor3 = Color3.fromRGB(100, 180, 100)})
    task.wait(1)
    resetBtn.Text = "🔄 Reset Session"
    tween(resetBtn, {BackgroundColor3 = Color3.fromRGB(200, 100, 100)})
end)

-- Character respawn
LocalPlayer.CharacterAdded:Connect(function(char)
    local wasFarming = farming

    if farming then
        stopFarm()
    end

    character = char
    hrp = char:WaitForChild("HumanoidRootPart")
    humanoid = char:FindFirstChildOfClass("Humanoid")

    updateCoinCache()

    if wasFarming then
        task.wait(1.5)
        startFarm()
    end
end)

-- Initialize
setupCoinTracker()
print("═══════════════════════════════════════")
print("MM2 Stealth Farmer v4.1 Loaded!")
print("Minimalist Edition with Smooth Animations")
print("═══════════════════════════════════════")
