"""Test della funzione pura cpu_hand_probabilities (P(in mano) per carta).

Esegui:  python test_cpu_probabilities.py
"""
from Duel_of_the_Seers import cpu_hand_probabilities


def approx(a, b, t=1e-9):
    return abs(a - b) < t


def test_no_history_all_full():
    p = cpu_hand_probabilities(list(range(9)), [])
    assert all(approx(p[c], 1.0) for c in range(9)), p


def test_example_t0_black_win5():
    # T0: PC gioca Nera, gioco 5, vinco -> PC aveva una tra {0,2,4}
    th = [{"cpu_color": "black", "my_card": 5, "feedback": "win"}]
    p = cpu_hand_probabilities(list(range(9)), th)
    for c in (0, 2, 4):
        assert approx(p[c], 2 / 3), (c, p[c])
    for c in (6, 8, 1, 3, 5, 7):
        assert approx(p[c], 1.0), (c, p[c])


def test_two_identical_constraints():
    # Due turni: PC gioca due carte distinte tra {0,2,4} -> ognuna 1/3 di restare
    th = [{"cpu_color": "black", "my_card": 5, "feedback": "win"}] * 2
    p = cpu_hand_probabilities(list(range(9)), th)
    for c in (0, 2, 4):
        assert approx(p[c], 1 / 3), (c, p[c])
    for c in (6, 8, 1, 3, 5, 7):
        assert approx(p[c], 1.0), (c, p[c])


def test_contradiction_fallback():
    # Nessun candidato coerente (nera < 0) -> fallback a 1.0 per tutte
    th = [{"cpu_color": "black", "my_card": 0, "feedback": "win"}]
    p = cpu_hand_probabilities(list(range(9)), th)
    assert all(approx(p[c], 1.0) for c in range(9)), p


def test_respects_manual_possible():
    # Se l'utente ha rimosso a mano alcune carte, restano solo quelle in cpu_possible
    th = [{"cpu_color": "black", "my_card": 5, "feedback": "win"}]
    p = cpu_hand_probabilities([0, 2, 4, 6, 8], th)
    assert set(p.keys()) == {0, 2, 4, 6, 8}, p
    for c in (0, 2, 4):
        assert approx(p[c], 2 / 3), (c, p[c])
    for c in (6, 8):
        assert approx(p[c], 1.0), (c, p[c])


if __name__ == "__main__":
    test_no_history_all_full()
    test_example_t0_black_win5()
    test_two_identical_constraints()
    test_contradiction_fallback()
    test_respects_manual_possible()
    print("ALL TESTS PASSED")
