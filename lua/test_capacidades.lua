-- Prueba de capacidades de Lua en el FBNeo de Fightcade, para entrenar el bot mas rapido:
--   1) joypad.set mueve al jugador 1 (control sin teclado ni foco)
--   2) emu.speedmode quita el limite de velocidad (entrenar acelerado)
--   3) AL FINAL: savestate con numero de ranura (la version sin ranura cerro el emulador)
-- Usar en modo practica. Resultados en la consola de Lua y en lua_test.txt.

local ROOT = "C:/Users/Sebas PC/Desktop/kof2002IA/"
local OUT = ROOT .. "lua_test.txt"
local FRAMES = ROOT .. "lua_frame.txt"
local P1 = 0x108100
local lines = {}

local function log(msg)
  print(msg)
  lines[#lines + 1] = msg
  local f = io.open(OUT, "w")
  if f then f:write(table.concat(lines, "\n"), "\n"); f:close() end
end

local function p1x() return memory.readword(P1 + 0x18) end

local frame = 0
local x_start = nil
local turbo_frame = nil
local done = false

local function step()
  if done then return end
  frame = frame + 1
  if frame % 10 == 0 then   -- para medir la velocidad real desde fuera (reloj de pared)
    local f = io.open(FRAMES, "w")
    if f then f:write(frame, "\n"); f:close() end
  end

  -- 1) joypad.set: mantener P1 derecha 120 frames
  if frame == 30 then
    x_start = p1x()
    log("1) joypad.set: x inicial = " .. x_start .. ", pulsando P1 Right 120 frames...")
  end
  if frame > 30 and frame <= 150 then
    local ok, err = pcall(joypad.set, {["P1 Right"] = true})
    if frame == 31 and not ok then log("   joypad.set fallo: " .. tostring(err)) end
  end
  if frame == 160 then
    local x = p1x()
    log(string.format("   x %d -> %d (se movio %d) => %s", x_start, x, x - x_start,
      (x ~= x_start) and "FUNCIONA" or "NO MOVIO"))
  end

  -- 2) velocidad: 600 frames sin limite (la velocidad real la mide tools/watch_speed.py)
  if frame == 200 then
    local ok, err = pcall(emu.speedmode, "maximum")
    local mode = "maximum"
    if not ok then ok, err = pcall(emu.speedmode, "turbo"); mode = "turbo" end
    log("2) emu.speedmode('" .. mode .. "'): " .. tostring(ok) .. (ok and "" or (" (" .. tostring(err) .. ")")))
    turbo_frame = frame
  end
  if frame == 800 then
    pcall(emu.speedmode, "normal")
    log("   velocidad vuelta a normal")
  end

  -- 3) savestate con ranura, lo ultimo (puede cerrar el emulador)
  if frame == 860 then
    log("3) savestate con ranura 1: guardando... (si el emulador se cierra aqui, no sirve)")
    local ok, err = pcall(function()
      local s = savestate.create(1)
      savestate.save(s)
    end)
    log("   guardado: " .. tostring(ok) .. (ok and "" or (" (" .. tostring(err) .. ")")) .. ", x = " .. p1x())
  end
  if frame > 860 and frame <= 920 then
    pcall(joypad.set, {["P1 Right"] = true})
  end
  if frame == 930 then
    local x_before = p1x()
    local ok, err = pcall(function() savestate.load(savestate.create(1)) end)
    log("   cargado: " .. tostring(ok) .. (ok and "" or (" (" .. tostring(err) .. ")")) ..
        string.format(", x antes de cargar %d", x_before))
  end
  if frame == 935 then
    log("   x despues de cargar = " .. p1x())
    log("PRUEBA TERMINADA.")
    done = true
  end
end

if emu.registerbefore then
  emu.registerbefore(step)
else
  emu.registerafter(step)
end
log("test_capacidades.lua (v2) en marcha, unos 15 segundos...")
