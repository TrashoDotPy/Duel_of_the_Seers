"""Analisi statistica del minigioco evento Metin2 "Contesa dei Veggenti".

REGOLE REALI (fonte: wiki ufficiale Metin2, en/it):
- Ogni giocatore ha 9 carte numerate 0..8 (una sola copia ciascuna). Pari = dorso
  nero (♠), dispari = dorso bianco (♡).
- 9 confronti. La carta piu' alta vince il round (+1 punto). Pari = nessun punto.
- NON vedi il VALORE della carta del computer: solo il COLORE (parita') e l'ESITO.
  Quindi devi DEDURRE le carte ancora possibili dell'avversario (cio' che fa l'app).
- L'avversario e' un COMPUTER (AI fissa, PvE), non un avversario razionale.
- Monete = punti (vittorie). Se vinci la manche: +(tue_vitt - sue_vitt).
  => Nel regime vincente:  monete = 3*vittorie + pari - 9.
  => L'obiettivo operativo e' MASSIMIZZARE IL NUMERO DI ROUND VINTI.

ATTENZIONE METODOLOGICA: poiche' l'avversario e' un bot, NON ha senso cercare un
equilibrio di Nash; bisogna SFRUTTARE la sua policy. Il problema e' che la policy
del bot non e' documentata. Questo script mostra che:
  1) contro un bot CASUALE nessuna strategia guadagna nulla (~4.6 monete sempre);
  2) contro un bot PREVEDIBILE la scelta della strategia vale da ~3 a ~15 monete,
     e nessuna strategia e' la migliore contro tutti i pattern.
Conclusione pratica: l'unico modo per ottimizzare davvero e' LOGGARE le partite
reali e identificare il pattern del computer.

Esegui con:  python analysis/strategy_analysis.py
"""
import random

CARDS = list(range(9))


def coins(wins, losses):
    """Monete Veggenza secondo la regola ufficiale."""
    return wins + (wins - losses if wins > losses else 0)


def play_game(strat_player, strat_cpu, rng):
    """Una manche. Ogni strategia riceve (proprie_carte, carte_avversario, rng).
    Nota: passiamo all'avversario il set reale rimanente = ipotesi di deduzione
    perfetta del tracker (caso migliore per il giocatore)."""
    p, c = set(CARDS), set(CARDS)
    wp = lp = 0
    while p:
        cp = strat_player(set(p), set(c), rng)
        cc = strat_cpu(set(c), set(p), rng)
        p.discard(cp); c.discard(cc)
        if cp > cc: wp += 1
        elif cc > cp: lp += 1
    return wp, lp


# ---- strategie / modelli di bot: f(my, opp, rng) -> card ----
def s_random(my, opp, rng):
    return rng.choice(tuple(my))


def s_author(my, opp, rng):
    """Replica dell'euristica get_suggestion dell'app: apertura fissa 0 poi 1,
    poi probabilita' P(c>x) con penalita' di conservazione."""
    turn = 9 - len(my)
    if turn == 0 and 0 in my: return 0
    if turn == 1 and 1 in my: return 1
    total = len(opp)
    pct = {c: sum(1 for x in opp if c > x) / total * 100 for c in my}
    if max(pct.values()) < 35: return min(my)
    score = {c: pct[c] - c * 2.5 for c in my}
    return max(my, key=lambda c: (score[c], -c))


def s_greedy(my, opp, rng):
    """Massimizza miopicamente P(vittoria) del round, a parita' la carta piu' bassa."""
    total = len(opp)
    return max(my, key=lambda c: (sum(1 for x in opp if c > x) / total, -c))


def s_min_winner(my, opp, rng):
    """Massimizza-vittorie (advantage shuffle): batti la carta avversaria piu'
    bassa con la tua minima carta vincente; se non puoi, sacrifica la tua minima."""
    lo = min(opp)
    winners = [c for c in my if c > lo]
    return min(winners) if winners else min(my)


def s_bot_asc(my, opp, rng):
    """Bot prevedibile: gioca sempre la carta piu' bassa (0,1,2,...,8)."""
    return min(my)


def s_bot_desc(my, opp, rng):
    """Bot prevedibile: gioca sempre la carta piu' alta (8,7,...,0)."""
    return max(my)


STRATS = {
    "random": s_random, "author": s_author, "greedy": s_greedy,
    "min_winner": s_min_winner, "bot_asc": s_bot_asc, "bot_desc": s_bot_desc,
}


def avg_coins(player, cpu, n, seed=0):
    rng = random.Random(seed)
    tot_w = tot_c = 0
    for _ in range(n):
        w, l = play_game(STRATS[player], STRATS[cpu], rng)
        tot_w += w
        tot_c += coins(w, l)
    return tot_w / n, tot_c / n


def table_vs_random():
    print("=== 1) Contro un computer CASUALE: vittorie / monete medie (200k manche) ===\n")
    print(f"{'strategia giocatore':<20}{'vitt. medie':>13}{'monete medie':>14}")
    print("-" * 47)
    for p in ["random", "author", "greedy", "min_winner"]:
        w, c = avg_coins(p, "random", 200000)
        print(f"{p:<20}{w:>13.3f}{c:>14.3f}")
    print("\n=> Tutte uguali (~4.0 vitt / ~4.6 monete): contro il caso, la strategia"
          " e' irrilevante.\n")


def table_exploitation():
    print("=== 2) Contro bot PREVEDIBILI: monete medie del giocatore ===\n")
    cpus = ["random", "bot_asc", "bot_desc"]
    players = ["random", "author", "greedy", "min_winner"]
    print(f"{'player \\ cpu':<14}" + "".join(f"{c:>12}" for c in cpus))
    print("-" * (14 + 12 * len(cpus)))
    for p in players:
        cells = []
        for c in cpus:
            deterministic = p != "random" and c != "random"
            n = 2000 if deterministic else 60000
            _, co = avg_coins(p, c, n)
            cells.append(f"{co:>12.2f}")
        print(f"{p:<14}" + "".join(cells))
    print("\n=> La strategia migliore DIPENDE dal bot: min_winner stritola il bot")
    print("   crescente (15), ma l'euristica dell'app contro lo stesso bot fa 3.00,")
    print("   PEGGIO del 4.60 del non-far-nulla. Nessuna strategia vince contro tutti.")
    print("   Morale: per ottimizzare davvero serve loggare e identificare il bot reale.")


if __name__ == "__main__":
    table_vs_random()
    table_exploitation()
