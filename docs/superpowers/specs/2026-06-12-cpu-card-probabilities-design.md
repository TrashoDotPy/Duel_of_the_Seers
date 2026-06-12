# Design — Percentuali P(in mano) per le carte del PC

Data: 2026-06-12
Progetto: Duel of the Seers (Contesa dei Veggenti) — `Duel_of_the_Seers.py`

## Obiettivo

Nella schermata di gioco, mostrare per ogni carta del PC ancora possibile la
probabilità che sia **ancora in mano** al computer, dedotta dai turni precedenti
della partita corrente.

## Decisioni prese (brainstorming)

1. **Fonte dati**: solo la partita corrente (vincoli dedotti: colore dichiarato +
   esito di ogni turno passato). Nessuno storico dai log.
2. **Metodo di calcolo**: pesato sulle ricostruzioni coerenti. Si enumerano tutte
   le permutazioni della mano del PC compatibili con i vincoli e si calcola, per
   ogni carta, in quante di esse risulta ancora in mano.
3. **Significato del numero**: `P(in mano)` per carta — valore indipendente 0–100%
   per ciascuna carta. Le percentuali **non** sommano a 100%.
4. **Visualizzazione**: la % va direttamente sotto ogni carta nel mazzo del PC
   ("Mazzo Computer"), stesso pattern già usato per le carte del giocatore.

## Architettura

Due modifiche, entrambe in `Duel_of_the_Seers.py`, classe `ContesaApp`:

### 1. Nuovo metodo puro `_cpu_hand_probabilities()`

Riusa la struttura DFS già presente in `_deduce_cpu_remaining`.

- Base di partenza: `manual = set(self.cpu_possible)` — rispetta anche le modifiche
  manuali al mazzo fatte dall'utente.
- Per ogni turno in `self.turn_history` costruisce l'insieme dei candidati coerenti
  (filtro per colore + filtro per esito `win`/`lose`/`par`), identico a quanto già
  fa `_deduce_cpu_remaining`.
- Enumera **tutte** le assegnazioni valide (carte distinte, una per ciascun turno
  passato) e, per ogni carta `c in manual`, conta in quante assegnazioni `c` resta
  *non usata* (= ancora in mano).
- `P(in mano, c) = (assegnazioni in cui c è rimasta) / (totale assegnazioni)`.
- **Ritorno**: `dict {c: prob}` con `prob` in `[0.0, 1.0]`, solo per le carte in
  `cpu_possible`.

Casi limite:
- Nessun turno passato (`turn_history` vuota) → tutte le carte possibili a `1.0`.
- Nessuna assegnazione coerente (contraddizione nei dati) → fallback: tutte le
  carte possibili a `1.0` (nessuna informazione, non blocca la UI).
- **Salvaguardia performance**: se il numero di assegnazioni valide supera una
  soglia (es. 50.000), interrompe l'enumerazione e usa lo stesso fallback a `1.0`.
  In pratica `_deduce_cpu_remaining` già enumera tutto dal vivo a ogni conferma,
  quindi il costo è allineato a quello esistente; la soglia è solo una rete di
  sicurezza.

### 2. Render in `_render_cpu_deck()`

- Calcola le probabilità una volta per render: `probs = self._cpu_hand_probabilities()`.
- Per ogni carta in `ALL_CARDS`:
  - se è in `cpu_possible`: aggiunge sotto la carta una `tk.Label` con il testo
    `f"{round(prob*100)}%"`, colorata con soglie semplici;
  - se **non** è in `cpu_possible` (giocata/dedotta o rimossa a mano): resta grigia,
    **senza** etichetta percentuale.
- Colore della %: verde per valori alti, arancio per medi, rosso per bassi
  (coerente con le soglie cromatiche già usate nella UI per le carte del giocatore).

## Flusso dati e aggiornamento

- La % dipende **solo dai turni passati** (`turn_history`), quindi:
  - si aggiorna a ogni "Conferma Turno" (quando `turn_history` cresce e
    `cpu_possible` viene ricalcolato);
  - si aggiorna a ogni modifica manuale del mazzo (click su una carta del PC, che
    già chiama `_render_cpu_deck`);
  - **non** cambia durante la scelta del colore del turno corrente (quel dato non è
    ancora confermato).
- Nessuna nuova variabile di stato persistente: la % è derivata, ricalcolata al
  momento del render.

## Esempio di verifica

Scenario: *T0 — il PC gioca Nera ♠, il giocatore gioca 5 e vince.*
Il PC aveva una tra {0, 2, 4} (nere < 5). Risultato atteso:

| Carta | P(in mano) |
|-------|-----------|
| 0, 2, 4 (nere < 5) | 67% |
| 6, 8 (nere ≥ 5)    | 100% |
| 1, 3, 5, 7 (bianche) | 100% |

## Testing

- `_cpu_hand_probabilities()` è una funzione **pura** sullo stato (`cpu_possible`,
  `turn_history`): verificabile senza UI.
- Verifica manuale/asserzione sullo scenario d'esempio sopra (0/2/4 = 2/3,
  6/8/bianche = 1).
- Il progetto non ha attualmente un framework di test. Validazione minima: uno
  snippet/asserzione che costruisce uno stato fittizio e controlla i valori attesi.

## Fuori scope (YAGNI)

- Probabilità basate sullo storico dei log (deciso: solo partita corrente).
- Distribuzione "prossima mossa" normalizzata a 100% (deciso: P(in mano) per carta).
- Pannello/lista separata di percentuali (ridondante col mazzo già visibile).
