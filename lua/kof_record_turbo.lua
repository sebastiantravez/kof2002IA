-- Igual que kof_record.lua pero con el juego SIN LIMITE de velocidad: para grabar
-- repeticiones mas rapido (la grabacion es frame a frame, no le importa la velocidad).
-- Si Fightcade manda la repeticion al ritmo normal, el emulador espera los datos y
-- simplemente no gana velocidad.
-- SOLO para repeticiones: nunca en una partida en vivo ni en practica.
-- Cargar en el emulador de la REPETICION: Game -> Lua Scripting -> ... -> Run.

KOF_RECORD_TURBO = true
local ok, info = pcall(debug.getinfo, 1, "S")
local here = ((ok and info and info.source) or ""):gsub("^@", ""):gsub("\\", "/"):match("^(.*/)")
dofile((here or "C:/Users/Sebas PC/Desktop/kof2002IA/lua/") .. "kof_record.lua")
