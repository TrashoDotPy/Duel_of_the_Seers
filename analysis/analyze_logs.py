"""Legge i log delle partite (logs/duel_logs.jsonl) e cerca pattern nel computer.

Questo e' il primo passo concreto per "trovare il pattern" del bot: accumula
abbastanza partite reali giocando con l'app, poi esegui:

    python analysis/analyze_logs.py [percorso_log]

Riporta, per posizione di turno: con che colore gioca il computer e quali carte
esatte ha giocato (quando il tracker le ha dedotte in modo univoco). Se emerge una
regolarita' (es. apre quasi sempre con carte alte/basse, o un colore fisso), quella
e' la leva da sfruttare.
"""
import json
import os
import sys
from collections import defaultdict, Counter


def load(path):
    games = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                games.append(json.loads(line))
    return games


def report(games):
    print(f"Partite registrate: {len(games)}")
    won = sum(1 for g in games if g["wins"] > g["losses"])
    drew = sum(1 for g in games if g["wins"] == g["losses"])
    total_coins = sum(g.get("coins", 0) for g in games)
    print(f"Manche: {won} vinte, {drew} pari, {len(games) - won - drew} perse")
    print(f"Monete totali: {total_coins}  (media {total_coins / len(games):.2f}/partita)")

    color_by_turn = defaultdict(Counter)
    card_by_turn = defaultdict(Counter)
    for g in games:
        for t in g["turns"]:
            color_by_turn[t["turn"]][t["cpu_color"]] += 1
            if t.get("cpu_card") is not None:
                card_by_turn[t["turn"]][t["cpu_card"]] += 1

    print("\nColore giocato dal computer per turno:")
    for turn in sorted(color_by_turn):
        c = color_by_turn[turn]
        tot = sum(c.values())
        print(f"  T{turn}: nere/pari {c['black']:>3}/{tot}   bianche/dispari {c['white']:>3}/{tot}")

    print("\nCarte ESATTE dedotte del computer per turno (solo quando univoche):")
    for turn in sorted(card_by_turn):
        c = card_by_turn[turn]
        dist = "  ".join(f"{card}:{n}" for card, n in sorted(c.items()))
        most = c.most_common(1)[0]
        print(f"  T{turn}: {dist}    (piu' frequente: {most[0]})")


def main():
    default = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "logs", "duel_logs.jsonl")
    path = sys.argv[1] if len(sys.argv) > 1 else default
    if not os.path.exists(path):
        print(f"File log non trovato: {path}")
        print("Gioca qualche partita nell'app per generarlo.")
        return
    games = load(path)
    if not games:
        print("Il log e' vuoto.")
        return
    report(games)


if __name__ == "__main__":
    main()
