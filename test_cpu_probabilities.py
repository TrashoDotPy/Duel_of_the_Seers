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


def test_par_alone_keeps_others_full():
    # T0 pareggio: il PC ha giocato esattamente la mia carta (3). La carta dedotta
    # esce da cpu_possible ed entra in cpu_confirmed_played. Le altre restano 100%.
    cpu_possible = [0, 1, 2, 4, 5, 6, 7, 8]
    played = [3]
    th = [{"cpu_color": "white", "my_card": 3, "feedback": "par"}]
    p = cpu_hand_probabilities(cpu_possible, th, played)
    assert 3 not in p, p
    assert all(approx(p[c], 1.0) for c in cpu_possible), p


def test_par_after_win_preserves_earlier_info():
    # T0: nera, gioco 5, vinco -> 0/2/4 informativi. T1: pareggio su 3 (rimossa).
    # Le percentuali dedotte a T0 NON devono azzerarsi a 100%.
    cpu_possible = [0, 1, 2, 4, 5, 6, 7, 8]
    played = [3]
    th = [
        {"cpu_color": "black", "my_card": 5, "feedback": "win"},
        {"cpu_color": "white", "my_card": 3, "feedback": "par"},
    ]
    p = cpu_hand_probabilities(cpu_possible, th, played)
    assert 3 not in p, p
    for c in (0, 2, 4):
        assert approx(p[c], 2 / 3), (c, p[c])
    for c in (1, 5, 6, 7, 8):
        assert approx(p[c], 1.0), (c, p[c])


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
    test_par_alone_keeps_others_full()
    test_par_after_win_preserves_earlier_info()
    test_respects_manual_possible()
    print("ALL TESTS PASSED")
