-- Offline experimental intervention: D0 changed for ONE ADD, then restored.
-- No ROM/RAM/input writes. Run alone; requires fresh explicit offline arming.
local ROOT = "C:/Users/Sebas PC/Documents/kof2002IA-mis-cambios-chatgpt/experiments/iori_speed_lab/"
ROOT = dofile(ROOT .. "settings.lua").root
for _, name in ipairs({"registerexec", "getregister", "setregister", "readword", "readbyte"}) do
  assert(type(memory[name]) == "function", "Missing memory." .. name)
end
assert(emu.romname() == "kf2k2pls", "Unverified ROM driver")
if type(emu.isonline) == "function" then
  local ok, online = pcall(emu.isonline)
  assert(ok and (online == nil or online == false or online == 0), "Offline only")
end
local arm = assert(io.open(ROOT .. "trial_arm.txt", "r"), "First run trial.py arm --offline")
local declaration, timestamp = arm:read("*l"), tonumber(arm:read("*l"))
-- Lua 5.1 strtod can follow Windows decimal locale. Parse dot decimals explicitly.
local function read_factor()
  local line = arm:read("*l") or ""
  local whole, fraction = line:match("^%s*(%d+)%.(%d+)%s*$")
  if not whole or #whole > 2 or #fraction > 8 then return nil end
  return tonumber(whole) + tonumber(fraction) / 10 ^ #fraction
end
local walk = read_factor()
local run = read_factor()
arm:close()
assert(declaration == "offline" and timestamp and os.time() >= timestamp and os.time() - timestamp <= 120,
  "Expired offline declaration; arm again")
assert(walk and walk >= 1 and walk <= 1.05 and run and run >= 1 and run <= 1.08, "Invalid factors")
assert(os.remove(ROOT .. "trial_arm.txt"), "Could not consume offline declaration")
local P1 = 0x108100
assert(memory.readbyte(P1 + 0x71) == 21, "Select Iori P1")
local routes = {
  {0x2e714, 0x2e718, "walk_positive", 171520, 2, walk, 0x4eb9},
  {0x2e66c, 0x2e670, "walk_negative", -171520, 1, walk, 0x206c},
  {0x2f6a8, 0x2f6ac, "run_negative", -425984, 46, run, 0x7000}
}
for _, p in ipairs(routes) do
  assert(memory.readword(p[1]) == 0xd1ac and memory.readword(p[1] + 2) == 0x18
      and memory.readword(p[2]) == p[7], "Instruction mismatch")
end
local function reg(name) return memory.getregister("m68000." .. name) end
assert(type(reg("sr")) == "number", "Status register unavailable")
local function fixed(address)
  local n = memory.readword(address) * 65536 + memory.readword(address + 2)
  return n >= 2147483648 and n - 4294967296 or n
end
local function rounded(n) return n >= 0 and math.floor(n + 0.5) or math.ceil(n - 0.5) end
local path = ROOT .. "captures/trial_" .. os.date("%Y%m%d_%H%M%S") .. ".csv"
local old = io.open(path, "r")
if old then old:close(); error("Trial exists; wait a second") end
local out = assert(io.open(path, "w"), "Captures directory missing")
out:write("frame,phase,route,original,applied,x_before,x_after,velocity_after,restored_d0,exact_add,restored_ok\n")
local active, frames, phase, failure, ticket = true, 0, "baseline", nil, nil
local pending, modified = {}, 0
local rejected, hits = {}, 0
local velocity_examples, example_counts = {}, {}
local function reject(reason)
  rejected[reason] = (rejected[reason] or 0) + 1
end
local function set_d0(n)
  local ok = pcall(memory.setregister, "m68000.d0", n)
  return ok and reg("d0") == n
end
local function finish(reason)
  if not active then return end
  active = false
  for _, p in ipairs(routes) do
    memory.registerexec(p[1], 1, nil); memory.registerexec(p[2], 1, nil)
  end
  for _, row in ipairs(pending) do out:write(table.concat(row, ","), "\n") end
  pending = {}; out:close()
  local diagnostic = io.open(path .. ".txt", "w")
  if diagnostic then
    diagnostic:write("reason=", reason, "\nframes=", frames, "\nhook_hits=", hits,
      "\nmodified=", modified, "\n")
    local names = {}
    for name in pairs(rejected) do names[#names + 1] = name end
    table.sort(names)
    for _, name in ipairs(names) do
      diagnostic:write(name, "=", rejected[name], "\n")
      print("TRIAL FILTER: " .. name .. "=" .. rejected[name])
    end
    for _, line in ipairs(velocity_examples) do
      diagnostic:write(line, "\n"); print("TRIAL DETAIL: " .. line)
    end
    diagnostic:close()
  end
  print("TRIAL FINISHED: " .. reason .. "; modified=" .. modified .. "; " .. path)
  if modified == 0 then print("No boosted movements recorded: trial not validated.") end
end
emu.registerexit(function()
  -- Do not restore stale registers after game execution has progressed.
  if ticket then print("UNRESOLVED ADD: trial not validated; close/restart offline game before continuing") end
  finish("Stop")
end)
for _, p in ipairs(routes) do
  local point = p
  memory.registerexec(point[1], 1, function()
    if not active or failure then return end
    hits = hits + 1
    if ticket then failure = "missing post-ADD callback"; return end
    if reg("a4") ~= P1 then reject("other_player"); return end
    if reg("pc") ~= point[1] then failure = "hook timing mismatch"; return end
    if memory.readbyte(P1 + 0x71) ~= 21 then reject("not_iori"); return end
    local life = memory.readbyte(P1 + 0x139)
    if life <= 0 or life > 102 or memory.readbyte(0x108439) <= 0 then reject("life"); return end
    if memory.readword(P1 + 0x20) ~= 0 then reject("airborne"); return end
    if memory.readbyte(P1 + 0xe0) ~= 0 then reject("attack_flags"); return end
    if memory.readword(P1 + 0x72) ~= point[5] then reject("state_signature"); return end
    local original = reg("d0")
    local x_integer = memory.readword(P1 + 0x18)
    if x_integer <= 65 or x_integer >= 710 then reject("stage_edge"); return end
    if math.abs(x_integer - memory.readword(0x108318)) < 80 then reject("rival_too_close"); return end
    local stored_velocity = fixed(P1 + 0x50)
    if original ~= point[4] or stored_velocity ~= original then
      reject("velocity")
      local n = example_counts[point[3]] or 0
      if n < 3 then
        velocity_examples[#velocity_examples + 1] = point[3] .. ": d0=" .. tostring(original)
          .. ", expected=" .. tostring(point[4]) .. ", ram_velocity=" .. tostring(stored_velocity)
          .. ", words=" .. tostring(memory.readword(P1 + 0x50)) .. "/"
          .. tostring(memory.readword(P1 + 0x52)) .. ", phase=" .. phase
        example_counts[point[3]] = n + 1
      end
      return
    end
    local applied = phase == "enabled" and rounded(original * point[6]) or original
    local sr = reg("sr")
    ticket = {point=point, original=original, applied=applied, x=fixed(P1 + 0x18),
      phase=phase, frame=emu.framecount()}
    if applied ~= original then
      if not set_d0(applied) or reg("sr") ~= sr then
        local restored = set_d0(original)
        failure = restored and "register change rejected" or "register restore FAILED"
        ticket.applied = reg("d0")
      else modified = modified + 1 end
    end
  end)
  memory.registerexec(point[2], 1, function()
    if not active or not ticket or ticket.point ~= point then return end
    local t = ticket
    local aligned = reg("pc") == point[2] and reg("a4") == P1
    if not aligned then failure = "post-ADD timing mismatch"; return end
    local x_after, velocity = fixed(P1 + 0x18), fixed(P1 + 0x50)
    local expected_register = reg("d0") == t.applied
    local sr = reg("sr")
    local restored = t.applied == t.original and reg("d0") == t.original or set_d0(t.original)
    restored = restored and reg("sr") == sr
    local exact = x_after - t.x == t.applied
    pending[#pending + 1] = {t.frame,t.phase,point[3],t.original,t.applied,t.x,x_after,
      velocity,reg("d0"),exact and 1 or 0,restored and 1 or 0}
    ticket = nil
    if not expected_register or not exact or velocity ~= t.original or not restored then
      failure = "ADD/restoration verification FAILED"
    end
  end)
end
emu.registerafter(function()
  if not active then return end
  frames = frames + 1
  for _, row in ipairs(pending) do out:write(table.concat(row, ","), "\n") end
  pending = {}; out:flush()
  if ticket then failure = "unresolved ADD; restart offline game" end
  local stop = io.open(ROOT .. "trial_stop.txt", "r")
  if stop then stop:close(); finish("deactivated"); return end
  if failure then finish(failure); return end
  if memory.readbyte(P1 + 0x71) ~= 21 then finish("P1 changed"); return end
  local next_phase = frames < 900 and "baseline" or frames < 1800 and "enabled" or "restored"
  if next_phase ~= phase then phase = next_phase; print("TRIAL PHASE: " .. phase) end
  if frames >= 2700 then finish("45 seconds completed; inspect CSV before increasing factors") end
end)
print("TRIAL baseline 15s -> enabled 15s -> restored 15s; walk=" .. walk .. ", run=" .. run)
if gui and type(gui.register) == "function" and type(gui.text) == "function" then
  gui.register(function()
    local label = not active and "DESACTIVADO" or phase == "baseline" and "REFERENCIA"
      or phase == "enabled" and "MEJORA ACTIVA" or "DESACTIVADO / COMPARACION"
    gui.text(8, 8, "Iori Speed Lab: " .. label)
  end)
end
print("Return to game. Manual controls. Forward run to LEFT only is verified. " .. path)
