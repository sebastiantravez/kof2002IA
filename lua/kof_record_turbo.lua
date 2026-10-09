-- Igual que kof_record.lua pero con el juego SIN LIMITE de velocidad: para grabar
-- repeticiones mas rapido (la grabacion es frame a frame, no le importa la velocidad).
-- Si Fightcade manda la repeticion al ritmo normal, el emulador espera los datos y
-- simplemente no gana velocidad.
-- SOLO para repeticiones: nunca en una partida en vivo ni en practica.
-- AVISO (reportado por el usuario, 2026-10-08): en repeticiones largas de Fightcade (retas a 5)
-- acelerar DESFASA la repeticion y los datos quedan mal. Para eso usar kof_record.lua a
-- velocidad normal. Solo sirve en repeticiones cortas, revisando que no se desfase.
-- Cargar en el emulador de la REPETICION: Game -> Lua Scripting -> ... -> Run.
--
-- Si la consola dice que no encontro kof_record.lua, escribe aqui la ruta de tu carpeta
-- KOF_Grabador (con / y terminando en /), por ejemplo "C:/Users/TuUsuario/Desktop/KOF_Grabador/":
local CARPETA = nil

KOF_RECORD_TURBO = true
print("AVISO: el turbo puede desfasar repeticiones largas de Fightcade. Para retas largas usa kof_record.lua.")

local function exists(path)
  local f = io.open(path, "r")
  if f then f:close() return true end
  return false
end

local list = {}
local function add(dir)
  if type(dir) ~= "string" then return end
  dir = dir:gsub("\\", "/")
  if dir ~= "" and dir:sub(-1) ~= "/" then dir = dir .. "/" end
  list[#list + 1] = dir
end
add(CARPETA)
if debug and debug.getinfo then
  local ok, info = pcall(debug.getinfo, 1, "S")
  local src = ok and info and info.source
  if type(src) == "string" then
    add((src:gsub("^@", ""):gsub("\\", "/"):match("^(.*/)lua/[^/]*$")))
  end
end
local home = os and os.getenv and (os.getenv("USERPROFILE") or "") or ""
if home ~= "" then
  for _, place in ipairs({"Desktop", "Escritorio", "OneDrive/Desktop", "OneDrive/Escritorio",
                          "Downloads", "Descargas", "Documents", "Documentos"}) do
    add(home .. "/" .. place .. "/KOF_Grabador")
    add(home .. "/" .. place .. "/KOF_Grabador/KOF_Grabador")
    add(home .. "/" .. place .. "/kof2002IA")
  end
end
add("C:/Users/Sebas PC/Desktop/kof2002IA")

for _, dir in ipairs(list) do
  if exists(dir .. "lua/kof_record.lua") then
    KOF_GRABADOR_DIR = dir
    dofile(dir .. "lua/kof_record.lua")
    return
  end
end
print("ERROR: no encontre kof_record.lua. Probe:")
for _, dir in ipairs(list) do print("  " .. dir .. "lua/kof_record.lua") end
print("Solucion: pon la carpeta KOF_Grabador en el Escritorio, o escribe su ruta en la")
print("linea 'local CARPETA = ...' al inicio de este archivo.")
