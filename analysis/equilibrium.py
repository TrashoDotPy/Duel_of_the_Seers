"""Equilibrio (esatto-ish) del gioco su mazzo ridotto {0..n-1}, via induzione a
ritroso + fictitious play sui giochi a somma zero di ogni stato.

Mostra che il valore del gioco e' 0 e che la mossa di APERTURA all'equilibrio
e' uniformemente casuale.

CAVEAT IMPORTANTE: questa e' un'analisi puramente teorica valida SOLO se
l'avversario fosse un giocatore RAZIONALE. Nel minigioco Metin2 l'avversario e'
un COMPUTER (bot fisso, PvE): contro un bot non si gioca l'equilibrio, si SFRUTTA
la sua policy (vedi strategy_analysis.py). Questo file resta come nota teorica:
serve a spiegare perche', tra avversari razionali, nessuna strategia pura domina.

Esegui con:  python analysis/equilibrium.py
"""


def solve_zero_sum(M, iters=4000):
    """Fictitious play. M[i][j] = payoff alla riga (massimizza).
    Ritorna (valore_stimato, strategia_riga)."""
    R, C = len(M), len(M[0])
    rowCnt = [0] * R
    colCnt = [0] * C
    colCum = [0.0] * R   # payoff cumulato di ogni riga, date le scelte della colonna
    rowCum = [0.0] * C   # payoff cumulato di ogni colonna, date le scelte della riga
    for _ in range(iters):
        i = max(range(R), key=lambda i: colCum[i])
        rowCnt[i] += 1
        for j in range(C):
            rowCum[j] += M[i][j]
        j = min(range(C), key=lambda j: rowCum[j])
        colCnt[j] += 1
        for ii in range(R):
            colCum[ii] += M[ii][j]
    s = sum(rowCnt)
    strat = [c / s for c in rowCnt]
    lo = min(colCum) / iters
    hi = max(rowCum) / iters
    return (lo + hi) / 2, strat


def build_and_solve(N, iters=3000):
    full = frozenset(range(N))
    memo = {}

    def value(A, B):
        if not A:
            return 0.0
        key = (A, B)
        if key in memo:
            return memo[key]
        la, lb = sorted(A), sorted(B)
        M = [[(1 if a > b else -1 if a < b else 0) + value(A - {a}, B - {b})
              for b in lb] for a in la]
        v, _ = solve_zero_sum(M, iters)
        memo[key] = v
        return v

    la = sorted(full)
    M = [[(1 if a > b else -1 if a < b else 0) + value(full - {a}, full - {b})
          for b in la] for a in la]
    v0, strat0 = solve_zero_sum(M, iters * 3)
    return v0, dict(zip(la, strat0))


if __name__ == "__main__":
    for N in (4, 5):
        v, opening = build_and_solve(N)
        print(f"--- Mazzo {{0..{N - 1}}} ---")
        print(f"  Valore del gioco all'equilibrio: {v:+.3f}  (atteso 0 per simmetria)")
        print(f"  Distribuzione mossa di apertura all'equilibrio:")
        for c, p in sorted(opening.items()):
            bar = "#" * round(p * 40)
            print(f"    carta {c}: {p * 100:5.1f}%  {bar}")
        print()
