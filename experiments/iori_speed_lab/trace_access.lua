-- READ ONLY: observes CPU accesses; never writes game RAM or injects inputs.
-- Run ALONE, offline, Iori P1. Finishes after 600 frames or 30000 events.
local ROOT = "C:/Users/Sebas PC/Documents/kof2002IA-mis-cambios-chatgpt/experiments/iori_speed_lab/"
local cfg = dofile(ROOT .. "settings.lua")
ROOT = cfg.root
assert(not cfg.modifications_enabled, "Keep modifications_enabled false")
for _, name in ipairs({"registerread", "registerwrite", "getregister", "readword", "readbyte"}) do
  assert(type(memory[name]) == "function", "Missing API: memory." .. name)
end
assert(type(emu.registerafter) == "function" and type(emu.registerexit) == "function",
  "Missing frame/exit callback")
assert(emu.romname() == "kf2k2pls", "Unverified ROM driver")
if type(emu.isonline) == "function" then
  local ok, online = pcall(emu.isonline)
  assert(ok, "Could not query session mode")
  assert(online == nil or online == false or online == 0, "Offline tests only")
  if online == nil then print("Session mode unknown: use Test Game offline only.") end
end
assert(memory.readbyte(0x108171) == 21, "Select Iori as P1 before Run")
assert(type(memory.getregister("m68000.pc")) == "number", "68000 registers unavailable")
local path = ROOT .. "captures/access_" .. os.date("%Y%m%d_%H%M%S") .. ".csv"
local old = io.open(path, "r")
if old then old:close(); error("Trace exists; wait a second before Run") end
local out = assert(io.open(path, "w"), "Captures directory missing")
out:write("event,frame,kind,address,size,hook_value,pc,ppc,d0,d1,a0,a1,ppc_words\n")
local targets = {0x108118, 0x108144, 0x108150}
local active, internal, frames, count = true, false, 0, 0
local pending = {}
local function reg(name)
  local value = memory.getregister("m68000." .. name)
  return type(value) == "number" and string.format("%.0f", value) or ""
end
local function observe(kind)
  return function(address, size, value)
    if not active or internal or count >= 30000 then return end
    count = count + 1
    -- No memory reads inside a memory hook: avoid recursive emulator callbacks.
    pending[#pending + 1] = {count, emu.framecount(), kind, address, size, value,
      reg("pc"), reg("ppc"), reg("d0"), reg("d1"), reg("a0"), reg("a1")}
  end
end
local function flush()
  internal = true
  for _, row in ipairs(pending) do
    local ppc = tonumber(row[8])
    local words = {}
    -- Snapshot instruction bytes after frame, not inside the access callback.
    -- PC/PPC alignment must be checked during analysis; no assumed instruction length.
    if ppc and ppc >= 0 and ppc <= 0xfffff0 and ppc % 2 == 0 then
      for off = 0, 10, 2 do
        words[#words + 1] = string.format("%04x", memory.readword(ppc + off))
      end
    end
    out:write(table.concat(row, ","), ",", table.concat(words, "|"), "\n")
  end
  pending = {}
  out:flush()
  internal = false
end
local function finish(reason)
  if not active then return end
  active = false
  for _, address in ipairs(targets) do
    memory.registerread(address, 4, nil)
    memory.registerwrite(address, 4, nil)
  end
  flush()
  out:close()
  print("TRACE FINISHED: " .. reason .. "; events=" .. count .. "; " .. path)
  if count == 0 then print("No accesses observed: hook support not confirmed in this build.") end
end
emu.registerexit(function() finish("Stop") end)
for _, address in ipairs(targets) do
  memory.registerread(address, 4, observe("read"))
  memory.registerwrite(address, 4, observe("write"))
end
emu.registerafter(function()
  if not active then return end
  frames = frames + 1
  internal = true
  local iori = memory.readbyte(0x108171) == 21
  internal = false
  flush()
  if not iori then finish("P1 changed")
  elseif count >= 30000 then finish("event limit; trace may be partial")
  elseif frames >= 600 then finish("frame limit") end
end)
print("TRACE READ ONLY: move Iori manually for about 10 seconds. " .. path)
