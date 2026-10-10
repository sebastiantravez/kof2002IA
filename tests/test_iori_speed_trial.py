"""Validate per-instruction scaling/restoration; no real emulator modifications."""
import csv
import tempfile
import time
import unittest
from pathlib import Path
try:
    from lupa import LuaRuntime
except ImportError:
    LuaRuntime = None

LAB = Path(__file__).resolve().parents[1] / 'experiments' / 'iori_speed_lab'


@unittest.skipIf(LuaRuntime is None, 'Optional Lua runtime unavailable')
class SpeedTrialTests(unittest.TestCase):
    def test_scales_once_restores_register_and_preserves_velocity_and_p2(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'captures').mkdir()
            (root / 'trial_arm.txt').write_text(f'offline\n{int(time.time())}\n1.01\n1.01\n')
            lua = LuaRuntime()
            lua.globals().test_root = root.as_posix() + '/'
            lua.execute('''
              local hooks, pc, d0, a4, sr = {}, 0, -171520, 0x108100, 0x2000
              local x, velocity, state, frames = 500*65536, -171520, 1, 0
              local writes = 0
              local function forbidden() error('unexpected memory/input mutation') end
              memory={writebyte=forbidden,writeword=forbidden,writedword=forbidden,
                readbyte=function(a)
                  if a==0x108171 then return 21 end
                  if a==0x108239 or a==0x108439 then return 102 end
                  return 0
                end,
                readword=function(a)
                  for _,p in ipairs({0x2e714,0x2e66c,0x2f6a8}) do
                    if a==p then return 0xd1ac end
                    if a==p+2 then return 0x18 end
                  end
                  if a==0x2e718 then return 0x4eb9 end
                  if a==0x2e670 then return 0x206c end
                  if a==0x2f6ac then return 0x7000 end
                  if a==0x108172 then return state end
                  if a==0x108118 then return math.floor(x/65536)%65536 end
                  if a==0x10811a then return x%65536 end
                  if a==0x108150 then return math.floor(velocity/65536)%65536 end
                  if a==0x108152 then return velocity%65536 end
                  return 0
                end,
                getregister=function(r)
                  if r=='m68000.pc' then return pc end
                  if r=='m68000.a4' then return a4 end
                  if r=='m68000.d0' then return d0 end
                  if r=='m68000.sr' then return sr end
                end,
                setregister=function(r,n) assert(r=='m68000.d0'); d0=n; writes=writes+1 end,
                registerexec=function(a,n,f) hooks[a]=f end}
              joypad={set=forbidden}; savestate={load=forbidden}
              emu={romname=function() return 'kf2k2pls' end,isonline=function() end,
                framecount=function() return frames end,
                registerafter=function(f) after=f end,registerexit=function(f) exit=f end}
              dofile=function() return {root=test_root} end
              local function move(p,original,expected)
                velocity=original; d0=original; pc=p; hooks[p](p)
                assert(d0==expected and velocity==original)
                x=x+d0; pc=p+4; hooks[pc](pc)
                assert(d0==original and velocity==original and sr==0x2000)
              end
              function simulate()
                move(0x2e66c,-171520,-171520)
                for i=1,900 do frames=frames+1; after() end
                move(0x2e66c,-171520,-173235)
                move(0x2e66c,-171520,-173235) -- no accumulating multiplier
                state=46; move(0x2f6a8,-425984,-430244)
                local saved=writes
                a4=0x108300; pc=0x2f6a8; d0=-425984; hooks[pc](pc)
                assert(writes==saved and d0==-425984); a4=0x108100
                state=1; move(0x2e66c,-123,-123) -- unverified velocity ignored
                for i=1,900 do frames=frames+1; after() end
                move(0x2e66c,-171520,-171520)
                after(); exit(); exit()
                assert(next(hooks)==nil and writes==6)
              end
            ''')
            # Reproduce Lua 5.1 on a Windows locale rejecting dot-decimal strtod.
            lua.execute('''
              local original_tonumber = tonumber
              tonumber=function(value, base)
                if type(value)=='string' and value:find('.',1,true) then return nil end
                return original_tonumber(value, base)
              end
            ''')
            lua.execute((LAB / 'speed_trial.lua').read_text(encoding='utf-8'))
            lua.globals().simulate()
            self.assertFalse((root / 'trial_arm.txt').exists())
            diagnostic = next((root / 'captures').glob('trial_*.csv.txt')).read_text()
            self.assertIn('other_player=1', diagnostic)
            self.assertIn('velocity=1', diagnostic)
            self.assertIn('d0=-123, expected=-171520, ram_velocity=-123', diagnostic)
            self.assertIn('modified=3', diagnostic)
            with next((root / 'captures').glob('trial_*.csv')).open(newline='') as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 5)
            self.assertEqual([r['phase'] for r in rows], ['baseline', 'enabled', 'enabled', 'enabled', 'restored'])
            self.assertTrue(all(r['restored_ok'] == '1' and r['exact_add'] == '1' for r in rows))

    def test_no_direct_ram_rom_or_input_writes(self):
        source = (LAB / 'speed_trial.lua').read_text()
        for api in ('memory.writebyte(', 'memory.writeword(', 'memory.writedword(',
                    'joypad.set(', 'savestate.load('):
            self.assertNotIn(api, source)
