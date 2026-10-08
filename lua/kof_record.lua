-- Graba partidas (repeticiones o en vivo) de KOF 2002 para aprendizaje por imitacion.
-- NO escribe state.txt: si hubiera otro emulador con el bot, mezclaria las dos peleas.
-- Para jugar con el bot usar lua/kof_state.lua.
-- Cargar en FBNeo (Fightcade): Game -> Lua Scripting -> New Lua Script Window -> Browse -> Run.
--
-- Cada frame agrega una linea a recordings/rec_<fecha>.csv con, para P1 y P2:
--   x, altura, x_pantalla, y_pantalla, vida, flags(+0xE0: bit0 ataca, bit2 agachado), personaje(+0x71)
-- y los botones pulsados (joypad), si el emulador los expone durante la repeticion.
-- Ademas recordings/rec_<fecha>.bin: las dos estructuras completas por frame (~3,6 MB por
-- minuto de juego), para tools/analyze_my_play.py.

-- Carpeta base: la que contiene la carpeta lua/ de este script (asi funciona igual en el
-- proyecto y en el paquete portatil KOF_Grabador de otra PC). Las grabaciones van a
-- <base>/recordings/.
local function base_dir()
  local ok, info = pcall(debug.getinfo, 1, "S")
  local src = ok and info and info.source or ""
  src = src:gsub("^@", ""):gsub("\\", "/")
  local dir = src:match("^(.*/)lua/[^/]*$")
  return dir or "C:/Users/Sebas PC/Desktop/kof2002IA/"
end
local ROOT = base_dir()
local stamp = (os and os.date and os.date("%Y%m%d_%H%M%S"))
  or (os and os.time and tostring(os.time())) or tostring(emu.framecount())
local REC = ROOT .. "recordings/rec_" .. stamp .. ".csv"
print("kof_record.lua iniciando...")

local P1 = 0x108100
local P2 = 0x108300

local rec = io.open(REC, "w")
if not rec then
  print("ERROR: no se pudo crear " .. REC .. " (existe la carpeta recordings?)")
  return
end
-- Volcado completo: las dos estructuras de jugador (0x200 bytes cada una) por frame, en
-- binario, en el mismo orden que las lineas del CSV (registro i = linea de datos i).
-- Sirve para buscar en la RAM senales que aun no conocemos (ataque bajo, agarre, guardia).
local STRUCT = 0x200
local BIN = REC:gsub("%.csv$", ".bin")
local bin = io.open(BIN, "wb")
if not bin then print("AVISO: sin volcado completo (" .. BIN .. ")") end
local chars = {}
local function dump(base)
  for i = 0, STRUCT - 1 do chars[i + 1] = string.char(memory.readbyte(base + i)) end
  return table.concat(chars)
end
rec:write("frame,p1x,p1h,p1sx,p1sy,p1life,p1flags,p1char,p2x,p2h,p2sx,p2sy,p2life,p2flags,p2char,inputs\n")

local printed_keys = false

local function fields(base)
  return string.format("%d,%d,%d,%d,%d,%d,%d",
    memory.readword(base + 0x18), memory.readword(base + 0x20),
    memory.readword(base + 0x24), memory.readword(base + 0x26),
    memory.readbyte(base + 0x139), memory.readbyte(base + 0xE0),
    memory.readbyte(base + 0x71))
end

local function pressed()
  local ok, pad = pcall(joypad.get)
  if not ok or type(pad) ~= "table" then return "" end
  local keys = {}
  for name, value in pairs(pad) do
    if value == true or value == 1 then keys[#keys + 1] = name end
  end
  if not printed_keys then
    local all = {}
    for name, _ in pairs(pad) do all[#all + 1] = name end
    table.sort(all)
    print("Botones que expone joypad.get(): " .. table.concat(all, ", "))
    printed_keys = true
  end
  table.sort(keys)
  return table.concat(keys, "|")
end

local frames = 0
local last_time, last_frames = os.time(), 0

local function on_frame()
  local f = emu.framecount()
  rec:write(f, ",", fields(P1), ",", fields(P2), ",", pressed(), "\n")
  if bin then bin:write(dump(P1), dump(P2)) end
  frames = frames + 1
  if frames % 60 == 0 then
    rec:flush()
    if bin then bin:flush() end
  end
  -- con turbo (kof_record_turbo.lua): informar la velocidad real cada ~10 s
  if KOF_RECORD_TURBO and frames % 300 == 0 then
    local now = os.time()
    if now - last_time >= 10 then
      local fps = (frames - last_frames) / (now - last_time)
      print(string.format("grabando a %.0f fps (%.1fx)", fps, fps / 59.19))
      last_time, last_frames = now, frames
    end
  end
end

emu.registerafter(on_frame)
if KOF_RECORD_TURBO then
  emu.speedmode("turbo")
  print("Turbo activado: la repeticion se graba sin limite de velocidad.")
end
if emu.registerexit then
  emu.registerexit(function()
    rec:close()
    if bin then bin:close() end
  end)
end
print("kof_record.lua grabando -> " .. REC .. (bin and " (+ volcado completo .bin)" or ""))
