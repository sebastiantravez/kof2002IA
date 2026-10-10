import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from kof_ai.defense_log import DefenseLogger
from kof_ai.game_state import Fighter, GameState
from kof_ai.session_metrics import snapshot, damage_line
from tools.compare_sessions import load_groups, value


class SessionMetricsTests(unittest.TestCase):
    def test_damage_snapshot_includes_chip_and_survives_round_reload(self):
        with tempfile.TemporaryDirectory() as folder:
            logger = DefenseLogger(Path(folder) / "defensa.csv", lambda: ("rival ataca", "guardia", 1))
            def state(frame, mine, theirs):
                return GameState(frame, Fighter(400, 100, 220, 0, mine), Fighter(440, 140, 220, 0, theirs))
            try:
                for s in [state(0, 102, 102), state(1, 101, 92), state(2, 95, 0), state(3, 102, 102)]:
                    logger.observe(s, {"left"})
                brain = SimpleNamespace(dealt_total=12, taken_total=5, chip_total=1)
                metrics = snapshot(logger, brain, 1)
                self.assertEqual(metrics["danio_hecho"], 10)
                self.assertEqual(metrics["danio_recibido"], 7)
                self.assertEqual(metrics["danio_recibido_golpes"], 6)
                self.assertEqual(metrics["danio_raspado"], 1)
                self.assertEqual(metrics["diferencia_logger_cerebro"], {"danio_hecho": -2, "danio_recibido_total": 1})
                restored = json.loads(json.dumps(metrics))
                self.assertEqual(damage_line(restored), "Danio hecho 10, recibido 7 total (6 en golpes + 1 de raspado bloqueando especiales)")
            finally:
                logger.close()


class CompareSessionTests(unittest.TestCase):
    def test_play_filter_and_separate_sessions_and_rivals(self):
        with tempfile.TemporaryDirectory() as folder:
            base = {"modo": "BALANCED_EXPERIMENTAL", "modo_prueba": True, "rival": "id30"}
            sessions = [base, base, {**base, "modo_prueba": False}, {**base, "rival": "Chin"},
                        {k: v for k, v in base.items() if k != "rival"}]
            for i, session in enumerate(sessions):
                (Path(folder) / f"sesion_Iori_{i}.json").write_text(json.dumps(session), encoding="utf-8")
            groups = load_groups(folder, "Iori", "id30", play=True, by_session=True)
            self.assertEqual(len(groups), 2)
            self.assertEqual(sum(map(len, load_groups(folder, "Iori", "id30").values())), 1)
            self.assertEqual(len(load_groups(folder, "Iori", play=True)), 3)

    def test_other_rounds_are_not_losses(self):
        session = {"ganadas": 4, "perdidas": 4, "otras": 4}
        self.assertAlmostEqual(value([session], None, "win"), 100 / 3)
        self.assertEqual(session["perdidas"], 4)
