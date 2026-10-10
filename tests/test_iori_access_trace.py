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
                  for i=1,600 do frame=i; after() end
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
        source = (LAB / 'trace_access.lua').read_text(encoding='utf-8')
        for api in ('memory.writebyte(', 'memory.writeword(', 'memory.writedword(',
                    'memory.setregister(', 'joypad.set(', 'savestate.load('):
            self.assertNotIn(api, source)
