import ctypes
import importlib.util
import tempfile
import unittest
from pathlib import Path

LAB = Path(__file__).resolve().parents[1] / 'experiments' / 'iori_speed_lab'
spec = importlib.util.spec_from_file_location('speed_analysis', LAB / 'analyze.py')
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)
scan_spec = importlib.util.spec_from_file_location('speed_scan', LAB / 'scan_candidates.py')
scanner = importlib.util.module_from_spec(scan_spec)
scan_spec.loader.exec_module(scanner)


def row(frame, x=200, height=0, life=102, flag=0, label='walk', inputs=''):
    raw = bytearray(512)
    raw[0x18:0x1a] = x.to_bytes(2, 'big')
    raw[0x20:0x22] = height.to_bytes(2, 'big')
    raw[0x139], raw[0xe0], raw[0x71] = life, flag, 21
    return dict(sample=str(frame), frame=str(frame), label=label, p1raw=raw.hex(), p2raw=raw.hex(),
                input_before=inputs, input_after=inputs, input_ok='1')


class SpeedLabTests(unittest.TestCase):
    def test_scanner_finds_synthetic_signed_velocity_and_excludes_position(self):
        rows = []
        for base, step in [(0, 2), (100, 6), (200, -2)]:
            for f in range(25):
                item = row(base + f, x=350 + step * f, inputs='P1 Right' if step > 0 else 'P1 Left')
                raw, rival = bytearray.fromhex(item['p1raw']), bytearray.fromhex(item['p2raw'])
                raw[0x44:0x48] = (step * 65536).to_bytes(4, 'big', signed=True)
                rival[0x18:0x1a] = (900).to_bytes(2, 'big')
                item['p1raw'], item['p2raw'] = raw.hex(), rival.hex()
                rows.append(item)
        result = scanner.scan(rows)
        self.assertGreater(result['filtered_samples'], 40)
        candidate = next(c for c in result['candidates'] if c['offset'] == '0x044' and c['signed_bits'] == 32)
        self.assertAlmostEqual(candidate['correlation_with_signed_dx'], 1)
        self.assertFalse(any(c['offset'] in {'0x018', '0x01a', '0x024'} for c in result['candidates']))

    def test_scanner_does_not_use_short_discontinuous_segments(self):
        self.assertEqual(scanner.scan([row(0), row(20, x=202)])['filtered_samples'], 0)

    def test_baseline_velocity_and_travel_frames(self):
        result = analysis.summarize([row(f, 200 + 2 * f) for f in range(61)], 100)
        self.assertEqual(result['speed_units_per_frame'], 2)
        self.assertEqual(result['traversal_frames'], [50])
        self.assertIsNone(result['startup_frames'])
        self.assertIsNone(result['physical_input_latency_ms'])

    def test_attack_damage_jump_and_reset_are_not_walking(self):
        result = analysis.summarize([row(0), row(1, 202, height=20), row(2, 204, flag=1),
                                    row(3, 206, life=80), row(1, 200)], 100)
        self.assertEqual(result['moving_samples'], 0)

    def test_input_proxy_is_not_reported_as_attack_startup(self):
        result = analysis.summarize([row(0, label='normal_A'),
                                    row(1, label='normal_A', inputs='P1 Button A'),
                                    row(2, label='normal_A', flag=1),
                                    row(3, label='normal_A', flag=1),
                                    row(4, label='normal_A')])
        self.assertEqual(result['input_to_animation_flag_frames'], [1])
        self.assertEqual(result['attack_flag_duration_frames'], [2])
        self.assertIsNone(result['recovery_frames'])

    def test_lua_51_capture_with_read_only_mock(self):
        dll = Path('C:/Users/Sebas PC/Documents/Fightcade/emulator/fbneo/lua51.dll')
        if not dll.exists():
            self.skipTest('Local Lua 5.1 runtime unavailable')
        try:
            lua = ctypes.CDLL(str(dll))
        except OSError as exc:
            if getattr(exc, 'winerror', None) == 193:
                self.skipTest('Lua local de 32 bits incompatible con Python de 64 bits')
            raise
        lua.luaL_newstate.restype = ctypes.c_void_p
        lua.luaL_openlibs.argtypes = [ctypes.c_void_p]
        lua.luaL_loadstring.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        lua.lua_pcall.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int]
        lua.lua_tolstring.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
        lua.lua_tolstring.restype = ctypes.c_char_p
        lua.lua_close.argtypes = [ctypes.c_void_p]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).as_posix() + '/'
            (Path(folder) / 'captures').mkdir()
            prefix = '''
              memory={readbyte=function(a) if a==0x108171 then return 21 end return 0 end,
                      readword=function(a) return 0 end,
                      writebyte=function() error('unexpected RAM write') end}
              joypad={get=function() return {['P1 Right']=true} end,
                      set=function() error('unexpected input injection') end}
              local before, after, exit
              emu={isonline=function() end,
                   romname=function() return 'kf2k2pls' end, framecount=function() return 1 end,
                   registerbefore=function(f) before=f end, registerafter=function(f) after=f end,
                   registerexit=function(f) exit=f end}
            '''
            config = f'dofile=function() return {{root="{root}",capture_enabled=true,label="walk",flush_frames=1}} end\n'
            suffix = '\n before(); after(); exit()\n'
            state = lua.luaL_newstate()
            try:
                lua.luaL_openlibs(state)
                error = lua.luaL_loadstring(state, (prefix + config + (LAB / 'capture.lua').read_text() + suffix).encode())
                if not error:
                    error = lua.lua_pcall(state, 0, 0, 0)
                self.assertEqual(error, 0, lua.lua_tolstring(state, -1, None))
                csv_files = list((Path(folder) / 'captures').glob('*.csv'))
                self.assertEqual(len(csv_files), 1)
                self.assertIn('P1 Right', csv_files[0].read_text())
            finally:
                lua.lua_close(state)
