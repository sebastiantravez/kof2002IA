-- Entrenamiento acelerado: el bot (Python) controla a P1 frame a frame desde aqui.
--
-- En cada frame este script escribe el estado en lock_req.txt ("seq frame ack" + RAM)
-- y espera la respuesta de Python en lock_resp.txt ("seq|teclas|id:ordenes|N|seq":
-- mantener las teclas N frames antes de volver a preguntar). Las
-- teclas se pulsan con joypad.set (no hace falta foco ni teclado). Cada lote de
-- ordenes tiene un id: Python lo repite hasta que "ack" (el ultimo id ejecutado)
-- lo confirma, y aqui se ejecuta una sola vez. Las ordenes son:
--   SAVE   guardar partida en la ranura 1 (inicio de ronda); SAVE2/LOAD2: ranura 2 (laboratorio)
--   LOAD   cargar la ranura 1 (reiniciar la ronda al instante)
--   TURBO  quitar el limite de velocidad;  NORMAL  volver a velocidad normal
-- Si Python no responde, el juego sigue normal sin el bot.
--
-- Cargar en FBNeo: Game -> Lua Scripting -> New Lua Script Window -> Browse -> Run.
-- Despues lanzar: python tools/train_fast.py <personaje> <minutos>

local ROOT = "C:/Users/Sebas PC/Desktop/kof2002IA/"
local REQ = ROOT .. "lock_req.txt"
local RESP = ROOT .. "lock_resp.txt"

local P1, P2 = 0x108100, 0x108300
-- Solo los bytes que usa el bot (igual que SPARSE_OFFSETS en kof_ai/lockstep.py):
-- x, altura, x/y en pantalla, personaje, agarre, flags ataque/agachado, vida, barras.
local OFFSETS = {0x18, 0x19, 0x20, 0x21, 0x24, 0x25, 0x26, 0x27, 0x71, 0x73, 0xE0, 0x139, 0x1E3}
local KEYMAP = {
  up = "P1 Up", down = "P1 Down", left = "P1 Left", right = "P1 Right",
  A = "P1 Button A", B = "P1 Button B", C = "P1 Button C", D = "P1 Button D",
}
-- Nunca esperar mucho dentro de un frame: el emulador mata en silencio los scripts
-- que tardan demasiado en un callback. Si Python no llego a tiempo (p.ej. guardando
-- la tabla), se siguen pulsando las mismas teclas y se vuelve a preguntar.
local WAIT_CONNECTED = 0.05
local WAIT_DISCONNECTED = 0.002
local MAX_MISSES = 300        -- fallos seguidos antes de dar a Python por desconectado
local misses = 0

local seq = 0
local connected = false
local last_cmd_id = 0
local dead_seq = -1   -- respuesta que ya hizo esperar en vano (Python se fue)
local current_pad = {}
local hold_left = 0   -- frames que faltan manteniendo current_pad sin preguntar a Python

local function sparse(base)
  local parts = {}
  for i, off in ipairs(OFFSETS) do
    parts[i] = string.format("%02x", memory.readbyte(base + off))
  end
  return table.concat(parts)
end

-- Respuesta "seq|teclas|ordenes|seq": el seq repetido al final detecta lecturas a
-- medio escribir (el archivo se reescribe en el mismo lugar, sin renombrar).
local function read_resp()
  local f = io.open(RESP, "r")
  if not f then return nil end
  local line = f:read("*l")
  f:close()
  if not line then return nil end
  local s, keys, cmds, hold, s2 = line:match("^(%d+)|([^|]*)|([^|]*)|(%d+)|(%d+)")
  if not s or s ~= s2 then return nil end
  return tonumber(s), keys, cmds, tonumber(hold)
end

local function apply(keys, cmds)
  local id, list = cmds:match("^(%d+):(.*)$")
  id = tonumber(id)
  if id and id > last_cmd_id then
    last_cmd_id = id
    print("orden " .. id .. ": " .. list .. " (frame " .. emu.framecount() .. ")")
    for c in string.gmatch(list, "%S+") do
      -- SAVE/LOAD = ranura 1 (punto de reinicio del entrenamiento); SAVE2..SAVE9 y
      -- LOAD2..LOAD9 = otras ranuras (laboratorio de combos, pruebas de guardia)
      local op, slot = c:match("^(SAVE)(%d?)$")
      if not op then op, slot = c:match("^(LOAD)(%d?)$") end
      slot = tonumber(slot) or 1
      if op == "SAVE" then savestate.save(savestate.create(slot))
      elseif op == "LOAD" then savestate.load(savestate.create(slot))
      elseif c == "TURBO" then emu.speedmode("turbo")
      elseif c == "NORMAL" then emu.speedmode("normal")
      end
    end
  end
  local pad = {}
  for k in string.gmatch(keys, "[^,]+") do
    if KEYMAP[k] then
      pad[KEYMAP[k]] = true
    elseif k:sub(1, 1) == "2" and KEYMAP[k:sub(2)] then
      -- "2down", "2B"...: teclas de P2 (pruebas de guardia con ataques etiquetados)
      pad[KEYMAP[k:sub(2)]:gsub("^P1", "P2")] = true
    end
  end
  current_pad = pad
  joypad.set(pad)
end

-- Teclas FISICAS de P1 en este frame (mascara de bits), para grabar lo que hace una persona
-- mientras Python mueve a P2 (tools/tech_record.py). Va antes que el pedido: cuando Python lee
-- el seq, este archivo ya tiene el mismo seq. Si no hay persona, es todo ceros.
local PAD = ROOT .. "lock_pad.txt"
local PAD_BITS = {
  ["P1 Up"] = 1, ["P1 Down"] = 2, ["P1 Left"] = 4, ["P1 Right"] = 8,
  ["P1 Button A"] = 16, ["P1 Button B"] = 32, ["P1 Button C"] = 64, ["P1 Button D"] = 128,
}
local function write_pad(n)
  local ok, pad = pcall(joypad.get)
  local mask = 0
  if ok and type(pad) == "table" then
    for name, bit in pairs(PAD_BITS) do
      if pad[name] then mask = mask + bit end
    end
  end
  local f = io.open(PAD, "w")
  if f then
    f:write(n, " ", mask, " ", n, "\n")
    f:close()
  end
end

local alive_count = 0

local function on_frame()
  alive_count = alive_count + 1
  if alive_count % 600 == 0 then
    print("sigo vivo: frame " .. emu.framecount() .. ", seq " .. seq .. (connected and " (conectado)" or ""))
  end
  -- Python pidio mantener las teclas varios frames: no preguntar en cada uno.
  if hold_left > 0 then
    hold_left = hold_left - 1
    joypad.set(current_pad)
    return
  end
  seq = seq + 1
  write_pad(seq)
  -- "seq frame ack p1 p2 seq" en una linea, reescrita en el mismo lugar (Python
  -- descarta la lectura si los dos seq no coinciden).
  local f = io.open(REQ, "w")
  if f then
    f:write(seq, " ", emu.framecount(), " ", last_cmd_id, " ", sparse(P1), " ", sparse(P2), " ", seq, "\n")
    f:close()
  end
  local t0 = os.clock()
  while true do
    local s, keys, cmds, hold = read_resp()
    if s == seq then
      if not connected then print("Bot conectado.") end
      connected = true
      misses = 0
      apply(keys, cmds)
      hold_left = math.max((hold or 1) - 1, 0)
      return
    end
    -- Python vivo pero unos frames atrasado (respondio hace poco, nunca "del futuro":
    -- eso es una respuesta vieja de antes de reiniciar el script): esperarlo para
    -- sincronizar. Sin respuestas recientes, no frenar el juego.
    local behind = s and (seq - s) or -1
    local alive = connected or (s ~= nil and s ~= dead_seq and behind >= 0 and behind <= 10)
    local budget = alive and WAIT_CONNECTED or WAIT_DISCONNECTED
    if os.clock() - t0 > budget then
      if connected then
        -- Python no llego a tiempo este frame: mismas teclas y seguir.
        misses = misses + 1
        joypad.set(current_pad)
        if misses >= MAX_MISSES then
          print("Python no responde: el juego sigue sin el bot.")
          emu.speedmode("normal")
          connected = false
          current_pad = {}
          dead_seq = s
          misses = 0
        end
      elseif alive then
        dead_seq = s   -- esa respuesta ya no cuenta como "vivo"
      end
      return
    end
  end
end

emu.registerbefore(on_frame)
print("kof_train.lua listo. Lanza: python tools/train_fast.py <personaje> <minutos>")
