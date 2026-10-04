-- Exporta la RAM de los jugadores de KOF 2002 en cada frame.
-- Cargar en FBNeo (Fightcade): Game -> Lua Scripting -> New Lua Script Window -> Browse -> Run.
-- La app de Python lee el archivo que escribe este script.

local OUT = "C:/Users/Sebas PC/Desktop/kof2002IA/state.txt"
local TMP = OUT .. ".tmp"

local P1 = 0x108100
local P2 = 0x108300
local SIZE = 0x200

local function dump(base)
  local parts = {}
  for off = 0, SIZE - 2, 2 do
    parts[#parts + 1] = string.format("%04x", memory.readword(base + off))
  end
  return table.concat(parts)
end

local function export()
  local f = io.open(TMP, "w")
  if not f then return end
  f:write(emu.framecount(), "\n", dump(P1), "\n", dump(P2), "\n")
  f:close()
  os.remove(OUT)
  os.rename(TMP, OUT)
end

emu.registerafter(export)
print("kof_state.lua activo -> " .. OUT)
