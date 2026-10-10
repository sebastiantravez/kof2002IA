import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch


@unittest.skipUnless(sys.platform == "win32", "El bot usa APIs de Windows")
class BotSafetyTests(unittest.TestCase):
    def test_play_shutdown_does_not_save_but_training_does(self):
        from kof_ai.bot import RuleBot, _BaseBot
        for enabled in (False, True):
            bot = RuleBot.__new__(RuleBot)
            bot.save_enabled = enabled
            bot._brain = SimpleNamespace(save=Mock(), updates=0)
            bot._log = Mock()
            with patch.object(_BaseBot, "_run"):
                bot._run()
            self.assertEqual(bot._brain.save.call_count, int(enabled))

    def test_guard_rechecks_direction_and_height_each_frame(self):
        from kof_ai.bot import RuleBot
        from kof_ai.motions import keys_for
        bot = RuleBot.__new__(RuleBot)
        index = [0]
        bot._brain = SimpleNamespace(
            state=lambda: SimpleNamespace(facing_right=index[0] == 0),
            guard_low=lambda: index[0] == 0,
            can_punish_now=lambda: False, being_thrown=lambda: False)
        bot._keyboard = SimpleNamespace(set_state=Mock())
        def wait(frames, check):
            self.assertEqual(frames, 1)
            index[0] += 1
            return True
        bot._clock = SimpleNamespace(WATCH_CHUNK=2, wait_frames=wait)
        bot._should_stop = lambda: False
        self.assertTrue(bot._guard(2))
        self.assertEqual(bot._keyboard.set_state.call_args_list,
                         [unittest.mock.call(keys_for(1, "", True)),
                          unittest.mock.call(keys_for(4, "", False))])

    def test_guard_stops_when_punish_is_available(self):
        from kof_ai.bot import RuleBot
        bot = RuleBot.__new__(RuleBot)
        bot._brain = SimpleNamespace(state=lambda: SimpleNamespace(facing_right=True),
                                     guard_low=lambda: True, can_punish_now=lambda: True,
                                     being_thrown=lambda: False)
        bot._keyboard = SimpleNamespace(set_state=Mock())
        bot._clock = SimpleNamespace(wait_frames=Mock(return_value=True))
        bot._should_stop = lambda: False
        self.assertTrue(bot._guard(18))
        bot._clock.wait_frames.assert_called_once()
