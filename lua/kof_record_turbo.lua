-- Igual que kof_record.lua pero con el juego SIN LIMITE de velocidad: para grabar
-- repeticiones de jugadores fuertes mas rapido (la grabacion es frame a frame, no le
-- importa la velocidad). Si Fightcade manda la repeticion al ritmo normal, el emulador
-- espera los datos y simplemente no gana velocidad.
-- Cargar en el emulador de la REPETICION: Game -> Lua Scripting -> ... -> Run.

KOF_RECORD_TURBO = true
dofile("C:/Users/Sebas PC/Desktop/kof2002IA/lua/kof_record.lua")
