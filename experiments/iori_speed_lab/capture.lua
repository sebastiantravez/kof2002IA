-- Iori Speed Lab: READ ONLY. Never injects controls, loads states or writes RAM.
-- Run alone in an offline test with Iori P1 controlled manually.
local ROOT = "C:/Users/Sebas PC/Documents/kof2002IA-mis-cambios-chatgpt/experiments/iori_speed_lab/"
local cfg = dofile(ROOT .. "settings.lua")
ROOT = cfg.root
assert(not cfg.modifications_enabled, "No verified modifier: modifications_enabled must remain false")
assert(type(memory.readbyte) == "function" and type(memory.readword) == "function", "Missing read APIs")
assert(type(emu.registerafter) == "function", "Missing frame callback")
if type(emu.isonline) == "function" then
  local ok, online = pcall(emu.isonline)
  assert(ok, "Could not query session mode: " .. tostring(online))
  if online == nil then
    -- Some Fightcade builds return no Lua value (C function returns 0 results).
    -- nil is unknown, not evidence of an online session.
    print("Session mode unavailable (isonline returned nil). Use only an offline test.")
  else
    assert(online == false or online == 0, "Offline experiments only: close netplay and open Test Game")
  end
end
local game = type(emu.romname) == "function" and emu.romname() or "unknown"
assert(game == "kf2k2pls", "Unverified ROM driver: " .. game)
local id = os.date("%Y%m%d_%H%M%S")
local path = ROOT .. "captures/baseline_" .. id .. ".csv"
local existing = io.open(path, "r")
if existing then existing:close(); error("Capture already exists; wait a second before restarting") end
local file = assert(io.open(path, "w"), "Create captures directory before Run")
file:write("sample,frame,label,input_before,input_after,input_ok,p1raw,p2raw\n")
local P1, P2 = 0x108100, 0x108300 -- Existing READ-verified structures, not writable parameters.
local sample, enabled, label = 0, cfg.capture_enabled, cfg.label
local input_before, before_ok = "", false
local function clean(s) return tostring(s):gsub('[,\r\n]', '_') end
local function inputs()
  if not joypad or type(joypad.get) ~= "function" then return "", false end
  local ok, pad = pcall(joypad.get)
  if not ok or type(pad) ~= "table" then return "", false end
  local names = {}
  for name, pressed in pairs(pad) do
    if pressed == true or pressed == 1 then names[#names + 1] = clean(name) end
  end
  table.sort(names)
  return table.concat(names, "|"), true
end
local function dump(base)
  local data = {}
  for off = 0, 0x1fe, 2 do data[#data + 1] = string.format("%04x", memory.readword(base + off)) end
  return table.concat(data)
end
local function control()
  local f = io.open(ROOT .. "control.txt", "r")
  if not f then return end
  local line = f:read("*l") or ""
  f:close()
  local active, tag = line:match("^(%d)|([%w_]+)$")
  if active then enabled, label = active == "1", tag end
end
if type(emu.registerbefore) == "function" then
  emu.registerbefore(function() input_before, before_ok = inputs() end)
end
emu.registerafter(function()
  sample = sample + 1
  if sample % 10 == 1 then control() end
  local after, after_ok = inputs()
  if enabled and memory.readbyte(P1 + 0x71) == 21 then
    file:write(sample, ",", emu.framecount(), ",", clean(label), ",", input_before, ",", after, ",",
      (before_ok and after_ok) and "1" or "0", ",", dump(P1), ",", dump(P2), "\n")
  end
  if sample % cfg.flush_frames == 0 then file:flush() end
  if sample % 10 == 0 then
    local status = io.open(ROOT .. "status.txt", "w")
    if status then status:write(id, " ", sample, " ", emu.framecount(), "\n"); status:close() end
  end
end)
if type(emu.registerexit) == "function" then emu.registerexit(function() file:flush(); file:close() end) end
local meta = assert(io.open(ROOT .. "captures/baseline_" .. id .. ".txt", "w"))
meta:write("driver=", game, "\nmode=read_only\n",
  "writebyte_available=", tostring(type(memory.writebyte) == "function"), "\n",
  "writeword_available=", tostring(type(memory.writeword) == "function"), "\n",
  "No write API invoked. No verified speed or animation parameter.\n")
meta:close()
print("Iori Speed Lab READ ONLY -> " .. path)
print("Manual joystick only. Stop all other Lua scripts and bot runners.")
