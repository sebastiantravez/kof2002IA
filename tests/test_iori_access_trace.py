"""Exercise the observer without starting an emulator or changing game memory."""
import csv
import tempfile
import unittest
from pathlib import Path
try:
    from lupa import LuaRuntime
except ImportError:
    LuaRuntime = None
LAB = Path(__file__).resolve().parents[1] / 'experiments' / 'iori_speed_lab'

@unittest.skipIf(LuaRuntime is None, 'Optional Lua runtime unavailable')
class AccessTraceTests(unittest.TestCase):
    def test_execution_probe_records_before_load_and_add_without_mutation(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / 'captures').mkdir()
            lua = LuaRuntime()
            lua.globals().test_root = Path(folder).as_posix() + '/'
            lua.execute('''
              local hooks, pc, d0 = {}, 0, 123
              local function forbidden() error('unexpected game mutation') end
              memory={writebyte=forbidden, writeword=forbidden, writedword=forbidden,
                setregister=forbidden, registerread=forbidden, registerwrite=forbidden,
                readbyte=function(a) if a==0x108171 then return 21 end return 102 end,
                readword=function(a)
                  for _,p in ipairs({0x2e668,0x2e710,0x2f6a4}) do
                    if a==p then return 0x202c end
                    if a==p+2 then return 0x50 end
                    if a==p+4 then return 0xd1ac end
                    if a==p+6 then return 0x18 end
                  end
                  if a==0x108150 then return 0xfff9 end
                  if a==0x108152 then return 0x8000 end
                  if a==0x108118 then return 500 end
                  return 0
                end,
                getregister=function(r)
                  if r=='m68000.a4' then return 0x108100 end
                  if r=='m68000.d0' then return d0 end
                  return pc
                end,
                registerexec=function(a,n,f) assert(n==1); hooks[a]=f end}
              joypad={set=forbidden}; savestate={load=forbidden}
              emu={romname=function() return 'kf2k2pls' end, isonline=function() end,
                framecount=function() return 10 end,
                registerafter=function(f) after=f end, registerexit=function(f) exit=f end}
              dofile=function() return {root=test_root,modifications_enabled=false} end
              function simulate()
                pc=0x2f6a4; hooks[pc](pc,1,0)
                d0=-425984; pc=0x2f6a8; hooks[pc](pc,1,0)
                after(); exit(); exit()
                assert(next(hooks)==nil)
              end
            ''')
            lua.execute((LAB / 'probe_execution.lua').read_text(encoding='utf-8'))
            lua.globals().simulate()
            with next((Path(folder) / 'captures').glob('execution_*.csv')).open(newline='') as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual([r['point'] for r in rows], ['run_load', 'run_add'])
            self.assertEqual([r['d0'] for r in rows], ['123', '-425984'])
            self.assertTrue(all(r['velocity_fixed'] == '-425984' for r in rows))
            self.assertTrue(all(r['pc'] == r['hook_address'] for r in rows))
            self.assertTrue(all(r['x_fixed'] == str(500 * 65536) for r in rows))

    def test_hooks_stop_and_never_modify_game(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).as_posix() + '/'
            (Path(folder) / 'captures').mkdir()
            lua = LuaRuntime()
            lua.globals().test_root = root
            lua.execute('''
                local hooks = {read={}, write={}}
                local inside = false
                local frame = 0
                local function forbidden() error('unexpected game mutation') end
                memory = {
                  writebyte=forbidden, writeword=forbidden, writedword=forbidden,
                  setregister=forbidden,
                  readbyte=function(a) assert(not inside); return 21 end,
                  readword=function(a) assert(not inside); return 0x4e71 end,
                  getregister=function(r) return 256 end,
                  registerread=function(a,n,f) assert(n==4); hooks.read[a]=f end,
                  registerwrite=function(a,n,f) assert(n==4); hooks.write[a]=f end
                }
                joypad={set=forbidden}; savestate={load=forbidden}
                emu={romname=function() return 'kf2k2pls' end,
                     isonline=function() end, framecount=function() return frame end,
                     registerafter=function(f) after=f end,
                     registerexit=function(f) exit=f end}
                dofile=function() return {root=test_root, modifications_enabled=false} end
                function simulate()
                  inside=true
                  hooks.read[0x108144](0x108144,4,0)
                  hooks.write[0x108150](0x108150,4,425984)
                  inside=false
                  for i=1,1800 do frame=i; after() end
                  assert(next(hooks.read)==nil and next(hooks.write)==nil)
                  after(); exit()
                end
            ''')
            lua.execute((LAB / 'trace_access.lua').read_text(encoding='utf-8'))
            lua.globals().simulate()
            files = list((Path(folder) / 'captures').glob('access_*.csv'))
            self.assertEqual(len(files), 1)
            with files[0].open(newline='') as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual([r['kind'] for r in rows], ['read', 'write'])
            self.assertEqual(rows[1]['hook_value'], '425984')
            self.assertEqual(rows[0]['ppc_words'], '|'.join(['4e71'] * 6))

    def test_no_game_mutation_calls(self):
        for name in ('trace_access.lua', 'probe_execution.lua'):
            source = (LAB / name).read_text(encoding='utf-8')
            for api in ('memory.writebyte(', 'memory.writeword(', 'memory.writedword(',
                        'memory.setregister(', 'joypad.set(', 'savestate.load('):
                self.assertNotIn(api, source)
