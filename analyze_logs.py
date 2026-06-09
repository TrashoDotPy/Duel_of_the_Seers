"""
Semplice script di analisi per i file logs_IO.json e logs_PC.json
Esegue aggregazioni: numero partite, vittorie medie, distribuzione colori CPU,
card frequency per colore e distribuzione dei feedback.
Usalo così:
    python analyze_logs.py
"""
from collections import Counter, defaultdict
import json
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


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


def analyze_games(games):
    total = len(games)
    if total == 0:
        return None

    wins = sum(g.get('wins', 0) for g in games)
    losses = sum(g.get('losses', 0) for g in games)
    ties = sum(g.get('ties', 0) for g in games)

    started_counter = Counter(g.get('started_by', 'unknown') for g in games)

    color_counter = Counter()
    card_by_color = defaultdict(Counter)
    feedback_counter = Counter()

    for g in games:
        for turn in g.get('turn_history', []):
            col = turn.get('cpu_color') or 'unknown'
            color_counter[col] += 1
            mc = turn.get('my_card')
            if mc is not None:
                card_by_color[col][mc] += 1
            feedback_counter[turn.get('feedback') or 'unknown'] += 1

    return {
        'total_games': total,
        'wins_total': wins,
        'losses_total': losses,
        'ties_total': ties,
        'started_by': dict(started_counter),
        'color_counts': dict(color_counter),
        'card_by_color': {k: dict(v) for k, v in card_by_color.items()},
        'feedback_counts': dict(feedback_counter),
    }


if __name__ == '__main__':
    paths = [os.path.join(SCRIPT_DIR, 'logs_IO.json'), os.path.join(SCRIPT_DIR, 'logs_PC.json')]
    all_games = {}
    for p in paths:
        name = os.path.basename(p)
        games = load_ndjson(p)
        summary = analyze_games(games)
        all_games[name] = summary

    for name, s in all_games.items():
        print('\n==', name, '==')
        if s is None:
            print('  nessuna partita trovata')
            continue
        print(f"  partite: {s['total_games']}")
        print(f"  vittorie totali: {s['wins_total']}, sconfitte totali: {s['losses_total']}, pari totali: {s['ties_total']}")
        print('  iniziata da:', s['started_by'])
        print('  conteggio colori CPU (per turno):', s['color_counts'])
        print('  carte giocate dal giocatore per colore CPU (frequenze):', s['card_by_color'])
        print('  feedback counts:', s['feedback_counts'])
