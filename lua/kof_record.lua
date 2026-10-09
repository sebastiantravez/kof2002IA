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

-- ===== CARPETA DE GRABACIONES =====================================================
-- Normalmente se encuentra sola. Si la consola dice que no encontro la carpeta, escribe
-- aqui la ruta de tu carpeta KOF_Grabador (con / y terminando en /), por ejemplo:
--   local CARPETA = "C:/Users/TuUsuario/Desktop/KOF_Grabador/"
local CARPETA = nil
-- ==================================================================================

-- Carpeta base = la que contiene lua/ y recordings/. Algunos FBNeo no dicen la ruta del
-- script (sin libreria debug), asi que se prueban tambien los lugares habituales.
local function add_unique(list, dir)
  if type(dir) ~= "string" or dir == "" then return end
  dir = dir:gsub("\\", "/")
  if dir:sub(-1) ~= "/" then dir = dir .. "/" end
  for _, d in ipairs(list) do if d == dir then return end end
  list[#list + 1] = dir
end

local function script_dir()
  if not (debug and debug.getinfo) then return nil end
  local ok, info = pcall(debug.getinfo, 1, "S")
  local src = ok and info and info.source
  if type(src) ~= "string" then return nil end
  src = src:gsub("^@", ""):gsub("\\", "/")
  return src:match("^(.*/)lua/[^/]*$")
end

local function candidates()
  local list = {}
  add_unique(list, KOF_GRABADOR_DIR)   -- definido por kof_record_turbo.lua si lo encontro
  add_unique(list, CARPETA)
  add_unique(list, script_dir())
  local home = os and os.getenv and (os.getenv("USERPROFILE") or "") or ""
  if home ~= "" then
    for _, place in ipairs({"Desktop", "Escritorio", "OneDrive/Desktop", "OneDrive/Escritorio",
                            "Downloads", "Descargas", "Documents", "Documentos"}) do
      add_unique(list, home .. "/" .. place .. "/KOF_Grabador")
      add_unique(list, home .. "/" .. place .. "/KOF_Grabador/KOF_Grabador")   -- "Extraer todo"
      add_unique(list, home .. "/" .. place .. "/kof2002IA")
    end
  end
  add_unique(list, "C:/Users/Sebas PC/Desktop/kof2002IA")
  add_unique(list, "")   -- carpeta actual del emulador (ultimo recurso)
  return list
end

local function writable(dir)
  local probe = dir .. "recordings/.prueba_escritura"
  local f = io.open(probe, "w")
  if not f then return false end
  f:close()
  if os and os.remove then pcall(os.remove, probe) end
  return true
end

local ROOT
local tried = candidates()
for _, dir in ipairs(tried) do
  if writable(dir) then ROOT = dir break end
end
print("kof_record.lua iniciando...")
if not ROOT then
  print("ERROR: no encontre la carpeta recordings. Probe:")
  for _, dir in ipairs(tried) do print("  " .. dir .. "recordings/") end
  print("Solucion: pon la carpeta KOF_Grabador en el Escritorio, o escribe su ruta en")
  print("la linea 'local CARPETA = ...' al inicio de kof_record.lua.")
  return
end
KOF_GRABADOR_DIR = ROOT
local stamp = (os and os.date and os.date("%Y%m%d_%H%M%S"))
  or (os and os.time and tostring(os.time())) or tostring(emu.framecount())
local REC = ROOT .. "recordings/rec_" .. stamp .. ".csv"

local P1 = 0x108100
local P2 = 0x108300

local rec = io.open(REC, "w")
if not rec then
  print("ERROR: no se pudo crear " .. REC)
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

-- Velocidad limitada (kof_record_turbo.lua pone KOF_RECORD_SPEED, p. ej. 2 = el doble): el
-- emulador corre en turbo y aqui se espera lo justo en cada frame para no pasar de esa
-- velocidad. En Windows os.clock() mide tiempo real.
local frame_time = KOF_RECORD_SPEED and 1 / (59.19 * KOF_RECORD_SPEED) or nil
local next_frame = os.clock()
local function throttle()
  local now = os.clock()
  if now > next_frame + 0.25 then next_frame = now end   -- tras una pausa, no correr para alcanzar
  while os.clock() < next_frame do end
  next_frame = next_frame + frame_time
end

local function on_frame()
  if frame_time then throttle() end
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
