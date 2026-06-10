"""
Analisi dei log reali (logs_IO.json = inizio io, logs_PC.json = inizia il PC).

Oltre ai conteggi di base, ricostruisce le carte del PC dai vincoli (colore + esito)
e mostra il pattern che conta: P(vittoria | la mia carta). Se l'esito dipende solo
da quanto è alta la TUA carta, il PC sta giocando in modo indipendente (≈ casuale).

Uso:
    python analyze_logs.py
"""
from collections import Counter, defaultdict
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# La console Windows può usare cp1252: forza UTF-8 per i caratteri speciali.
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass


def is_black(c):
    return c % 2 == 0


def load_ndjson(path):
    if not os.path.exists(path):
        return []
    games = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                games.append(json.loads(line))
            except Exception:
                continue
    return games


def reconstruct(turn_history, limit=200):
    """Tutte le permutazioni del PC coerenti coi vincoli (fino a `limit`)."""
    cand = []
    for t in turn_history:
        col, mc, fb = t['cpu_color'], t['my_card'], t['feedback']
        cs = [c for c in range(9) if (is_black(c) if col == 'black' else not is_black(c))]
        if fb == 'win':
            cs = [c for c in cs if c < mc]
        elif fb == 'lose':
            cs = [c for c in cs if c > mc]
        elif fb == 'par':
            cs = [c for c in cs if c == mc]
        cand.append(cs)
    sols = []

    def dfs(i, used, cur):
        if len(sols) >= limit:
            return
        if i == len(cand):
            sols.append(cur[:])
            return
        for c in cand[i]:
            if c in used:
                continue
            used.add(c); cur.append(c)
            dfs(i + 1, used, cur)
            cur.pop(); used.discard(c)

    dfs(0, set(), [])
    return sols


def analyze(games, label):
    print(f"\n{'=' * 60}\n {label} — {len(games)} partite\n{'=' * 60}")
    if not games:
        print("  nessuna partita")
        return

    wins = sum(g.get('wins', 0) for g in games)
    losses = sum(g.get('losses', 0) for g in games)
    ties = sum(g.get('ties', 0) for g in games)
    coins = sum(g.get('coins', 0) for g in games)
    print(f"  Totali: {wins} vitt, {losses} scf, {ties} par")
    print(f"  Monete medie: {coins / len(games):.2f}/partita")

    # P(vittoria | la mia carta) — il pattern chiave
    by_mycard = defaultdict(Counter)
    color_by_turn = defaultdict(Counter)
    for g in games:
        for i, t in enumerate(g.get('turn_history', [])):
            by_mycard[t['my_card']][t['feedback']] += 1
            color_by_turn[i][t['cpu_color']] += 1

    print("\n  P(esito) in funzione della MIA carta:")
    print("    carta |  win  lose  par   %win")
    for c in range(9):
        cc = by_mycard[c]
        n = sum(cc.values())
        if n:
            pw = cc['win'] / n * 100
            print(f"      {c}   |  {cc['win']:>3}  {cc['lose']:>3}  {cc['par']:>3}   {pw:4.0f}%")
    print("  -> se %win cresce in modo monotono con la carta, il PC NON contrasta")
    print("     la tua mossa (gioca ~ a caso).")

    print("\n  Colore del PC per turno (nere=pari / bianche=dispari):")
    for i in range(9):
        cc = color_by_turn[i]
        n = sum(cc.values())
        if n:
            print(f"    T{i}: nere {cc['black']:>2}/{n}   bianche {cc['white']:>2}/{n}")

    # Ricostruzione carte PC: quante volte la sequenza è univoca
    uniq = 0
    for g in games:
        sols = reconstruct(g.get('turn_history', []))
        if len(sols) == 1:
            uniq += 1
    print(f"\n  Sequenza PC ricostruibile in modo univoco: {uniq}/{len(games)} partite.")


if __name__ == '__main__':
    for fname, label in [('logs_IO.json', 'INIZIO IO'), ('logs_PC.json', 'INIZIA IL PC')]:
        games = load_ndjson(os.path.join(SCRIPT_DIR, fname))
        analyze(games, label)
