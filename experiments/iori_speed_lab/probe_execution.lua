-- READ ONLY execution timing probe. Run ALONE in Test Game offline, Iori P1.
local ROOT = "C:/Users/Sebas PC/Documents/kof2002IA-mis-cambios-chatgpt/experiments/iori_speed_lab/"
local cfg = dofile(ROOT .. "settings.lua")
ROOT = cfg.root
assert(not cfg.modifications_enabled, "Keep modifications_enabled false")
for _, name in ipairs({"registerexec", "getregister", "readword", "readbyte"}) do
  assert(type(memory[name]) == "function", "Missing API: memory." .. name)
end
assert(emu.romname() == "kf2k2pls", "Unverified ROM driver")
if type(emu.isonline) == "function" then
  local ok, online = pcall(emu.isonline)
  assert(ok and (online == nil or online == false or online == 0), "Offline only")
  if online == nil then print("Session mode unknown: use Test Game offline only.") end
end
assert(memory.readbyte(0x108171) == 21, "Select Iori P1 before Run")
local points = {
  {0x2e668, "walk_negative_load", 0x202c, 0x0050},
  {0x2e66c, "walk_negative_add", 0xd1ac, 0x0018},
  {0x2e710, "walk_positive_load", 0x202c, 0x0050},
  {0x2e714, "walk_positive_add", 0xd1ac, 0x0018},
  {0x2f6a4, "run_load", 0x202c, 0x0050},
  {0x2f6a8, "run_add", 0xd1ac, 0x0018}
}
-- Exact words observed in the user's local access traces, not invented PCs.
for _, p in ipairs(points) do
  assert(memory.readword(p[1]) == p[3] and memory.readword(p[1] + 2) == p[4],
    "Instruction differs from verified trace at " .. string.format("%x", p[1]))
end
local function signed32(address)
  local value = memory.readword(address) * 65536 + memory.readword(address + 2)
  return value >= 2147483648 and value - 4294967296 or value
end
local path = ROOT .. "captures/execution_" .. os.date("%Y%m%d_%H%M%S") .. ".csv"
local old = io.open(path, "r")
if old then old:close(); error("Trace exists; wait a second") end
local out = assert(io.open(path, "w"), "Captures directory missing")
out:write("event,frame,point,hook_address,pc,ppc,a4,d0,x_fixed,velocity_fixed,char,life,height,attack_flag,state72,state74,p2_char,p2_life\n")
local active, frames, count, failure = true, 0, 0, nil
local pending = {}
local function reg(name) return memory.getregister("m68000." .. name) end
local function flush()
  for _, row in ipairs(pending) do out:write(table.concat(row, ","), "\n") end
  pending = {}
  out:flush()
end
local function finish(reason)
  if not active then return end
  active = false
  for _, p in ipairs(points) do memory.registerexec(p[1], 1, nil) end
  flush(); out:close()
  print("PROBE FINISHED: " .. reason .. "; events=" .. count .. "; " .. path)
  if count == 0 then print("No executions observed: execution hooks not verified.") end
end
emu.registerexit(function() finish("Stop") end)
for _, p in ipairs(points) do
  local address, name = p[1], p[2]
  memory.registerexec(address, 1, function(hook_address)
    if not active or failure or count >= 6000 then return end
    local pc, a4, d0, ppc = reg("pc"), reg("a4"), reg("d0"), reg("ppc")
    if type(pc) ~= "number" or type(a4) ~= "number" or type(d0) ~= "number"
        or type(ppc) ~= "number" then failure = "register unavailable"; return end
    -- Record timing mismatches rather than assuming callback is before execution.
    if a4 ~= 0x108100 then return end
    count = count + 1
    pending[#pending + 1] = {count, emu.framecount(), name, hook_address or address,
      pc, ppc, a4, d0, signed32(a4 + 0x18), signed32(a4 + 0x50),
      memory.readbyte(a4 + 0x71), memory.readbyte(a4 + 0x139),
      memory.readword(a4 + 0x20), memory.readbyte(a4 + 0xe0),
      memory.readword(a4 + 0x72), memory.readword(a4 + 0x74),
      memory.readbyte(0x108371), memory.readbyte(0x108439)}
    -- No memory read/write hooks registered: snapshots cannot recursively invoke them.
  end)
end
emu.registerafter(function()
  if not active then return end
  frames = frames + 1
  flush()
  if failure then finish(failure)
  elseif memory.readbyte(0x108171) ~= 21 then finish("P1 changed")
  elseif count >= 6000 then finish("event limit; partial trace")
  elseif frames >= 1800 then finish("frame limit") end
end)
print("PROBE READ ONLY: return to game; walk then run forward for 30 seconds. " .. path)
