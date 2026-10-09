-- Igual que kof_record.lua pero mas rapido, para grabar repeticiones sin esperar toda la reta.
-- La grabacion es frame a frame: a cualquier velocidad se guardan los mismos datos.
-- Cargar en el emulador de la REPETICION: Game -> Lua Scripting -> ... -> Run.
-- Nunca en una partida en vivo ni en practica.
--
-- VELOCIDAD: el turbo sin limite (~9x) DESFASA las repeticiones largas de Fightcade (reportado
-- por el usuario, 2026-10-08, retas a 5). Por eso aqui se limita. Cambia este numero:
--   1 = normal, 2 = el doble (una reta de 30 min en 15), 3 = el triple...
-- Si la repeticion se desfasa (los personajes hacen cosas raras o no coincide con el video),
-- baja el numero y vuelve a grabar esa repeticion.
local VELOCIDAD = 2

-- Si la consola dice que no encontro kof_record.lua, escribe aqui la ruta de tu carpeta
-- KOF_Grabador (con / y terminando en /), por ejemplo "C:/Users/TuUsuario/Desktop/KOF_Grabador/":
local CARPETA = nil

KOF_RECORD_TURBO = true
KOF_RECORD_SPEED = VELOCIDAD
print(string.format("Grabando a %gx como maximo (cambia VELOCIDAD al inicio de este archivo).", VELOCIDAD))

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
