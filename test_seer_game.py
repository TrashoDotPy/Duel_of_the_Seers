"""Test della logica pura di gioco (SeerGame), senza UI.

Esegui con:  python -m unittest test_seer_game
"""
import unittest

from Duel_of_the_Seers import SeerGame, ALL_CARDS, is_black, suit, card_label


class HelpersTest(unittest.TestCase):
    def test_color_helpers(self):
        self.assertTrue(is_black(0))
        self.assertFalse(is_black(1))
        self.assertEqual(suit(2), "♠")
        self.assertEqual(suit(3), "♡")
        self.assertEqual(card_label(4), "4♠")


class InitialStateTest(unittest.TestCase):
    def setUp(self):
        self.g = SeerGame()

    def test_initial_state(self):
        self.assertEqual(self.g.my_hand, list(ALL_CARDS))
        self.assertEqual(self.g.cpu_possible, list(ALL_CARDS))
        self.assertEqual(self.g.turn, 0)
        self.assertEqual(self.g.phase, "setup")
        self.assertFalse(self.g.done)
        self.assertFalse(self.g.can_undo())

    def test_effective_cpu_filters_by_color(self):
        self.g.cpu_color = "black"
        self.assertEqual(self.g.effective_cpu(), [0, 2, 4, 6, 8])
        self.g.cpu_color = "white"
        self.assertEqual(self.g.effective_cpu(), [1, 3, 5, 7])
        self.g.cpu_color = None
        self.assertEqual(self.g.effective_cpu(), list(ALL_CARDS))


class SurvivingTest(unittest.TestCase):
    def setUp(self):
        self.g = SeerGame()
        self.g.cpu_color = "black"  # eff = 0,2,4,6,8
        self.g.my_card = 5

    def test_win_keeps_lower(self):
        self.g.feedback = "win"
        self.assertEqual(self.g.surviving(), [0, 2, 4])

    def test_lose_keeps_higher(self):
        self.g.feedback = "lose"
        self.assertEqual(self.g.surviving(), [6, 8])

    def test_par_keeps_equal(self):
        self.g.my_card = 4
        self.g.feedback = "par"
        self.assertEqual(self.g.surviving(), [4])

    def test_no_data_returns_empty(self):
        self.g.feedback = None
        self.assertEqual(self.g.surviving(), [])


class CpuDeckEditTest(unittest.TestCase):
    def test_toggle_and_reset(self):
        g = SeerGame()
        g.toggle_cpu_card(3)
        self.assertNotIn(3, g.cpu_possible)
        g.toggle_cpu_card(3)
        self.assertIn(3, g.cpu_possible)
        self.assertEqual(g.cpu_possible, sorted(g.cpu_possible))  # resta ordinato
        g.toggle_cpu_card(0)
        g.reset_cpu_deck()
        self.assertEqual(g.cpu_possible, list(ALL_CARDS))


class ConfirmTurnTest(unittest.TestCase):
    def test_invalid_turn_is_rejected(self):
        g = SeerGame()
        # nessuna carta/feedback => surviving vuoto => confirm rifiutato
        self.assertFalse(g.confirm_turn())
        self.assertEqual(g.turn, 0)
        self.assertFalse(g.can_undo())

    def test_win_updates_score_and_hand(self):
        g = SeerGame()
        g.my_card = 5
        g.cpu_color = "black"
        g.feedback = "win"
        self.assertTrue(g.confirm_turn())
        self.assertEqual(g.wins, 1)
        self.assertEqual(g.turn, 1)
        self.assertNotIn(5, g.my_hand)
        self.assertEqual(len(g.my_hand), 8)
        # stato del turno azzerato dopo la conferma
        self.assertIsNone(g.my_card)
        self.assertIsNone(g.feedback)
        self.assertIsNone(g.cpu_color)

    def test_unique_survivor_is_auto_removed(self):
        g = SeerGame()
        g.my_card = 1
        g.cpu_color = "black"   # eff = 0,2,4,6,8
        g.feedback = "win"      # c < 1 => solo lo 0
        self.assertEqual(g.surviving(), [0])
        g.confirm_turn()
        self.assertNotIn(0, g.cpu_possible)


class UndoTest(unittest.TestCase):
    def test_undo_restores_auto_removed_card(self):
        """Regressione: lo snapshot va preso PRIMA della rimozione automatica."""
        g = SeerGame()
        g.my_card = 1
        g.cpu_color = "black"
        g.feedback = "win"  # survivor unico = 0, rimosso in auto
        g.confirm_turn()
        self.assertNotIn(0, g.cpu_possible)
        self.assertTrue(g.can_undo())

        self.assertTrue(g.undo())
        # la carta auto-rimossa deve tornare disponibile
        self.assertIn(0, g.cpu_possible)
        self.assertEqual(g.cpu_possible, list(ALL_CARDS))
        self.assertEqual(g.turn, 0)
        self.assertEqual(len(g.my_hand), 9)
        self.assertEqual(g.wins, 0)
        self.assertFalse(g.can_undo())

    def test_undo_on_empty_history(self):
        g = SeerGame()
        self.assertFalse(g.undo())


class CoinsTest(unittest.TestCase):
    def test_coins_with_margin_bonus(self):
        g = SeerGame()
        # Prepara una partita quasi finita: una sola carta in mano.
        g.my_hand = [3]
        g.wins, g.losses, g.ties = 2, 1, 0
        g.my_card = 3
        g.cpu_color = "black"   # eff: 0,2 < 3
        g.feedback = "win"
        g.confirm_turn()
        self.assertTrue(g.done)
        # wins=3, losses=1 => margine=2 => 3 + 2 = 5
        self.assertEqual(g.coins, 5)

    def test_coins_without_margin(self):
        g = SeerGame()
        g.my_hand = [0]
        g.wins, g.losses, g.ties = 1, 4, 4
        g.my_card = 0
        g.cpu_color = "white"   # eff: 1,3,5,7 > 0
        g.feedback = "lose"
        g.confirm_turn()
        self.assertTrue(g.done)
        # losses diventa 5, margine negativo => nessun bonus => coins = wins = 1
        self.assertEqual(g.coins, 1)


class DeduceTest(unittest.TestCase):
    def test_deduction_narrows_possibilities(self):
        g = SeerGame()
        # Turno: computer Nera, io gioco 7, perdo => computer aveva 8 (unico nero > 7)
        g.turn_history = [{"cpu_color": "black", "my_card": 7, "feedback": "lose"}]
        remaining = g.deduce_cpu_remaining()
        # l'8 è stato sicuramente usato dal computer in quel turno
        self.assertNotIn(8, remaining)

    def test_deduction_without_history_returns_manual(self):
        g = SeerGame()
        g.cpu_possible = [2, 4, 6]
        self.assertEqual(g.deduce_cpu_remaining(), {2, 4, 6})


class RecordTest(unittest.TestCase):
    def test_to_record_with_unique_deduction(self):
        g = SeerGame()
        g.who_first = "me"
        g.my_card = 1
        g.cpu_color = "black"
        g.feedback = "win"     # unico sopravvissuto = 0
        g.confirm_turn()
        rec = g.to_record()
        self.assertEqual(rec["who_first"], "me")
        self.assertEqual(rec["wins"], 1)
        self.assertEqual(len(rec["turns"]), 1)
        t = rec["turns"][0]
        self.assertEqual(t["turn"], 0)
        self.assertEqual(t["cpu_color"], "black")
        self.assertEqual(t["my_card"], 1)
        self.assertEqual(t["feedback"], "win")
        self.assertEqual(t["candidates"], [0])
        self.assertEqual(t["cpu_card"], 0)   # dedotta in modo univoco

    def test_to_record_multi_candidate(self):
        g = SeerGame()
        g.my_card = 5
        g.cpu_color = "black"
        g.feedback = "win"     # candidati 0,2,4
        g.confirm_turn()
        t = g.to_record()["turns"][0]
        self.assertEqual(t["candidates"], [0, 2, 4])
        self.assertIsNone(t["cpu_card"])     # non deducibile con certezza

    def test_record_is_json_serializable(self):
        import json
        g = SeerGame()
        g.my_card = 2; g.cpu_color = "black"; g.feedback = "win"
        g.confirm_turn()
        # non deve sollevare
        json.dumps(g.to_record())


if __name__ == "__main__":
    unittest.main()
