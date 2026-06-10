# Analisi strategica — Contesa dei Veggenti (minigioco evento Metin2)

Strumenti riproducibili (solo libreria standard) per studiare la strategia del
minigioco PvE *Duel of the Seers* / *Contesa dei Veggenti*.

## Regole reali (wiki ufficiale Metin2)

- Ogni giocatore ha **9 carte `0–8`** (una copia ciascuna). Pari = dorso nero ♠,
  dispari = dorso bianco ♡.
- 9 confronti: la carta più alta vince il round (+1). Pari = nessun punto.
- **Non vedi il valore della carta del computer**, solo il **colore** (parità) e
  l'**esito** del confronto → devi *dedurre* le carte possibili dell'avversario
  (è esattamente ciò che fa l'app).
- L'avversario è un **computer / AI fissa (PvE)**, non un giocatore razionale.
- **Monete Veggenza** = punti (vittorie); se vinci la manche, **+ (tue vittorie −
  sue vittorie)**. La formula nel codice dell'app è quindi **corretta**.

## Implicazione chiave sull'obiettivo

Nel regime in cui vinci la manche, le monete valgono `3·vittorie + pari − 9`.
Quindi l'obiettivo operativo è **massimizzare il numero di round vinti**, non il
margine. (La prima versione di questa analisi usava il margine: metrica errata.)

## Script

| File | Cosa fa |
|------|---------|
| `strategy_analysis.py` | Simula le strategie con la metrica corretta (monete) vs computer casuale e vs bot prevedibili. |
| `equilibrium.py` | *Solo nota teorica* (avversario razionale). Non operativo: l'avversario reale è un bot. |

```bash
python analysis/strategy_analysis.py
python analysis/equilibrium.py
```

## Conclusioni (corrette per il contesto PvE)

1. **Contro un computer casuale, la strategia è irrilevante**: ~4.0 vittorie /
   ~4.6 monete per *qualunque* strategia. Non si può guadagnare nulla contro il caso.
2. **Contro un bot prevedibile, la scelta della strategia vale tantissimo** (da ~3
   a ~15 monete). Esempi (monete medie del giocatore):

   | giocatore \ bot | casuale | crescente (0→8) | decrescente (8→0) |
   |---|---|---|---|
   | euristica app (`author`) | 4.59 | **3.00** | 12.00 |
   | `min_winner` (max-vittorie) | 4.59 | **15.00** | 4.00 |

3. **Nessuna strategia è la migliore contro tutti i bot** (di nuovo non-transitivo).
   L'euristica attuale dell'app contro un bot crescente fa addirittura *peggio del
   non-far-nulla* (3.00 < 4.60).
4. Poiché l'avversario è un bot fisso, **non bisogna randomizzare/giocare
   l'equilibrio: bisogna sfruttarlo.** Ma la policy del bot non è documentata.

## Cosa serve davvero (l'unico vero passo avanti)

Per ottimizzare sul serio bisogna **identificare il pattern del computer reale**.
Questo richiede di **registrare le partite su disco** e dedurne la policy.

➡️ **Il logging ora è implementato.** A fine partita l'app salva una riga JSON in
`logs/duel_logs.jsonl` con lo storico di ogni turno: colore del computer, la tua
carta, l'esito, i candidati dedotti e la carta esatta del computer quando è
univocamente deducibile.

Dopo aver accumulato un po' di partite, analizzale con:

```bash
python analysis/analyze_logs.py
```

che riporta, per posizione di turno, con che colore gioca il computer e quali carte
esatte ha giocato. Se emerge una regolarità (apertura tipica, colore preferito,
carte alte/basse in certe fasi), quella è la leva da sfruttare e potremo poi
adattare il suggeritore dell'app a quella policy.
