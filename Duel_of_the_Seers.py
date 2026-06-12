import tkinter as tk
from tkinter import font as tkfont
import os, sys, json
from datetime import datetime

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

ALL_CARDS = list(range(9))
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def resource_path(relative_path):
    """ Ottiene il percorso assoluto della risorsa, compatibile con dev e PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = SCRIPT_DIR
    return os.path.join(base_path, relative_path)


def is_black(c):
    return c % 2 == 0


def suit(c):
    return "♠" if is_black(c) else "♡"


def card_label(c):
    return f"{c}{suit(c)}"


def cpu_hand_probabilities(cpu_possible, turn_history, cpu_played=(), cap=50000):
    """P(in mano) per ogni carta del PC, dedotta dai vincoli della partita corrente.

    Considera tutte le permutazioni della mano del PC coerenti con i turni passati
    (colore dichiarato + esito) e calcola, per ogni carta ancora possibile, in quante
    di esse risulta ancora in mano. Ritorna {carta: probabilità in [0,1]} solo per le
    carte in `cpu_possible`.

    `cpu_played` sono le carte già dedotte come giocate dal PC: non sono più in mano
    (e non compaiono nel risultato), ma fanno parte dell'universo da cui pescare per
    riempire i turni passati — in particolare i pareggi, in cui la carta giocata viene
    rimossa da `cpu_possible` pur restando un vincolo necessario della ricostruzione.

    Funzione pura (nessuno stato GUI): testabile in isolamento.
    """
    possible = set(cpu_possible)
    universe = possible | set(cpu_played)
    if not possible:
        return {}
    if not turn_history:
        return {c: 1.0 for c in possible}

    # Candidati coerenti per ogni turno passato (stessa logica di _deduce_cpu_remaining),
    # pescati dall'intero universo (incluse le carte già dedotte come giocate).
    allowed_options = []
    for item in turn_history:
        color = item["cpu_color"]
        my_card = item["my_card"]
        feedback = item["feedback"]
        candidates = [c for c in universe if (is_black(c) if color == "black" else not is_black(c))]
        if feedback == "win":
            candidates = [c for c in candidates if c < my_card]
        elif feedback == "lose":
            candidates = [c for c in candidates if c > my_card]
        elif feedback == "par":
            candidates = [c for c in candidates if c == my_card]
        else:
            candidates = []
        if not candidates:
            # Dati contraddittori: nessuna info affidabile -> fallback neutro
            return {c: 1.0 for c in possible}
        allowed_options.append(candidates)

    # Ordina per ampiezza per potare prima (non cambia i conteggi)
    allowed_options.sort(key=len)

    total = 0
    remaining_counts = {c: 0 for c in universe}
    aborted = False

    def dfs(index, used):
        nonlocal total, aborted
        if aborted:
            return
        if index == len(allowed_options):
            total += 1
            if total > cap:
                aborted = True
                return
            for c in universe:
                if c not in used:
                    remaining_counts[c] += 1
            return
        for c in allowed_options[index]:
            if c in used:
                continue
            used.add(c)
            dfs(index + 1, used)
            used.remove(c)
            if aborted:
                return

    dfs(0, set())

    if aborted or total == 0:
        # Troppe permutazioni o nessuna coerente: fallback neutro, non blocca la UI
        return {c: 1.0 for c in possible}

    return {c: remaining_counts[c] / total for c in possible}


class ContesaApp:

    BG = "#1b1b1f"
    FG = "#f4f4f8"
    MUTED = "#9aa0ad"
    CARD_BG = "#252f3c"
    CARD_FG = "#f4f4f8"
    SEL_BG = "#22344f"
    SEL_FG = "#a8d4ff"
    SEL_BD = "#64b5ff"
    BTN_BG = "#2b3340"
    BTN_FG = "#f4f4f8"
    BTN_ACTIVE_BG = "#3a4a61"
    BTN_ACTIVE_FG = "#ffffff"
    BTN_BORDER = "#4d5c71"
    GREEN = "#4caf7d"
    ORANGE = "#ff9800"
    RED = "#ef5350"
    INFO_BG = "#22303d"
    INFO_FG = "#c8ebff"
    WARN_BG = "#55372a"
    WARN_FG = "#ffd87d"
    SECTION_BG = "#222830"
    PANEL_BG = "#232b36"
    LEGEND_BG = "#1f2430"
    LEGEND_FG = "#8b96ad"
    PLAYED_BG = "#1a1a2a"
    PLAYED_FG = "#6a6a8a"
    BANNER_IMAGE_PATH = resource_path("banner.png")

    def __init__(self, root):
        self.root = root
        self.root.title("Contesa dei Veggenti — Tracker & AI")
        self.root.configure(bg=self.BG)
        self.root.resizable(False, False)
        self.bold = tkfont.Font(family="Helvetica", size=11, weight="bold")
        self.normal = tkfont.Font(family="Helvetica", size=11)
        self.small = tkfont.Font(family="Helvetica", size=9)
        self.big = tkfont.Font(family="Helvetica", size=18, weight="bold")
        self.card_font = tkfont.Font(family="Helvetica", size=14, weight="bold")
        self.suit_font = tkfont.Font(family="Helvetica", size=9)
        self._build_ui()
        self._init_game()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        tk.Label(self.root, text="Contesa dei Veggenti", bg=self.BG, fg=self.FG,
                 font=self.big).pack(fill="x", padx=10, pady=(10, 0))
        tk.Label(self.root,
                 text="Obiettivo: identifica le carte ancora possibili del computer e registra il risultato di ogni turno.",
                 bg=self.BG, fg=self.FG, font=self.normal, wraplength=580, justify="left").pack(fill="x", padx=10, pady=(0, 10))

        stats = tk.Frame(self.root, bg=self.SECTION_BG, padx=10, pady=10)
        stats.pack(fill="x", padx=10, pady=(0, 8))
        self.stats_frame = stats
        self.lbl_turn = self._stat_box(stats, "Turno", "0/9")
        self.lbl_wins = self._stat_box(stats, "Vittorie", "0", self.GREEN)
        self.lbl_losses = self._stat_box(stats, "Sconfitte", "0", self.RED)
        self.lbl_coins = self._stat_box(stats, "Monete", "0")

        self.cpu_section = tk.LabelFrame(self.root, text="Mazzo Computer", bg=self.SECTION_BG,
                                         fg=self.FG, font=self.small, labelanchor="nw",
                                         bd=1, relief="groove", padx=8, pady=8)
        self.cpu_section.pack(fill="x", padx=10, pady=(0, 8))

        header = tk.Frame(self.cpu_section, bg=self.SECTION_BG)
        header.pack(fill="x", pady=(0, 4))
        tk.Label(header, text="Clicca per scartare/recuperare carte.",
                 bg=self.SECTION_BG, fg=self.MUTED, font=self.small).pack(side="left")
        self._btn(header, "Ripristina mazzo", self._reset_cpu_deck,
                  bg=self.BTN_BG, fg=self.BTN_FG).pack(side="right", padx=(8, 0))
        self.cpu_count_lbl = tk.Label(header, text="Carte possibili: 9", bg=self.SECTION_BG,
                                      fg=self.FG, font=self.small)
        self.cpu_count_lbl.pack(side="right")

        self.cpu_deck_frame = tk.Frame(self.cpu_section, bg=self.PANEL_BG, bd=1, relief="sunken",
                                       padx=10, pady=10)
        self.cpu_deck_frame.pack(fill="x")

        # Sezione carte già giocate dal computer (dedotte con certezza)
        self.cpu_played_header = tk.Label(self.cpu_section,
                                          text="Carte giocate dal computer (dedotte): nessuna",
                                          bg=self.SECTION_BG, fg=self.MUTED, font=self.small, anchor="w")
        self.cpu_played_header.pack(fill="x", pady=(6, 2))
        self.cpu_played_frame = tk.Frame(self.cpu_section, bg=self.SECTION_BG)
        self.cpu_played_frame.pack(fill="x")

        self.activity_section = tk.LabelFrame(self.root, text="Turno e scelta", bg=self.SECTION_BG,
                                              fg=self.FG, font=self.small, labelanchor="nw",
                                              bd=1, relief="groove", padx=8, pady=8)
        self.activity_section.pack(fill="x", padx=10, pady=(0, 8))

        self.main_frame = tk.Frame(self.activity_section, bg=self.SECTION_BG)
        self.main_frame.pack(fill="x")

        tk.Label(self.root, text="Legenda: ♠ = pari / ♡ = dispari", bg=self.BG,
                 fg=self.LEGEND_FG, font=self.small).pack(fill="x", padx=10, pady=(0, 8))

        self.log_section = tk.LabelFrame(self.root, text="Log partita", bg=self.SECTION_BG,
                                         fg=self.FG, font=self.small, labelanchor="nw",
                                         bd=1, relief="groove", padx=8, pady=8)
        self.log_section.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        self.log_text = tk.Text(self.log_section, height=5, bg=self.CARD_BG, fg=self.FG,
                                font=self.small, relief="flat", state="disabled",
                                wrap="word", borderwidth=0, highlightthickness=0)
        self.log_text.pack(fill="both", side="left", expand=True)
        scrollbar = tk.Scrollbar(self.log_section, command=self.log_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.log_text.config(yscrollcommand=scrollbar.set)

        bot = tk.Frame(self.root, bg=self.BG)
        bot.pack(fill="x", padx=10, pady=(0, 8))
        self._btn(bot, "Nuova partita", self._init_game, bg=self.BTN_BG, fg=self.BTN_FG).pack(side="left")
        self.undo_btn = self._btn(bot, "Undo", self._undo, bg="#3b3f48", fg=self.FG, state="disabled")
        self.undo_btn.pack(side="left", padx=(8, 0))
        self.gomsg = tk.Label(bot, text="", bg=self.BG, fg=self.GREEN, font=self.bold)
        self.gomsg.pack(side="left", padx=12)

        self.banner_frame = tk.Frame(self.root, bg=self.BG)
        self.banner_frame.pack(fill="both", padx=10, pady=(0, 10))
        self.banner_label = tk.Label(self.banner_frame, bg=self.BG, fg=self.MUTED,
                                     font=self.small, text="Caricamento banner...")
        self.banner_label.pack(fill="both", expand=True)
        self.banner_photo = None
        self._load_banner_image()

    def _stat_box(self, parent, label, value, color=None):
        f = tk.Frame(parent, bg=self.SECTION_BG, padx=12, pady=8)
        f.pack(side="left", expand=True, fill="x", padx=3)
        tk.Label(f, text=label, bg=self.SECTION_BG, fg=self.MUTED, font=self.small).pack()
        lbl = tk.Label(f, text=value, bg=self.SECTION_BG, fg=color or self.FG, font=self.big)
        lbl.pack()
        return lbl

    def _btn(self, parent, text, cmd, bg=None, fg=None, state="normal"):
        return tk.Button(parent, text=text, command=cmd,
                         bg=bg or self.BTN_BG, fg=fg or self.BTN_FG,
                         font=self.normal, relief="flat", bd=1,
                         activebackground=self.BTN_ACTIVE_BG, activeforeground=self.BTN_ACTIVE_FG,
                         highlightbackground=self.BTN_BORDER, highlightthickness=1,
                         padx=14, pady=6, cursor="hand2", state=state)

    def _load_banner_image(self):
        if not os.path.exists(self.BANNER_IMAGE_PATH):
            self.banner_label.config(text="Immagine banner non trovata.")
            self.banner_photo = None
            return
        if HAS_PIL:
            try:
                image = Image.open(self.BANNER_IMAGE_PATH)
                max_width = 700
                max_height = 180
                ratio = min(max_width / image.width, max_height / image.height, 1.0)
                if ratio < 1.0:
                    try:
                        resample = Image.Resampling.LANCZOS
                    except AttributeError:
                        resample = 3
                    new_width = int(image.width * ratio)
                    new_height = int(image.height * ratio)
                    image = image.resize((new_width, new_height), resample)
                self.banner_photo = ImageTk.PhotoImage(image)
                self.banner_label.config(image=self.banner_photo, text="")
                return
            except Exception:
                pass
        self.banner_label.config(text="Installa Pillow per mostrare il banner: pip install Pillow")
        self.banner_photo = None

    def _reset_cpu_deck(self):
        self.cpu_possible = list(ALL_CARDS)
        self._render_cpu_deck()
        self._render_main()

    # ── GAME LOGIC & AI ───────────────────────────────────────────────────────

    def _init_game(self):
        self.my_hand = list(ALL_CARDS)
        self.cpu_possible = list(ALL_CARDS)
        self.cpu_confirmed_played = []   # carte del computer dedotte con certezza
        self.turn = 0
        self.wins = 0
        self.losses = 0
        self.ties = 0
        self.coins = 0
        self.done = False
        self.who_first = None
        self.my_card = None
        self.cpu_color = None
        self.feedback = None
        self.phase = "setup"
        self.history = []
        self.turn_history = []
        self.gomsg.config(text="")
        self._clear_log()
        self._update_stats()
        self._render_cpu_deck()
        self._render_main()
        self.undo_btn.config(state="disabled")

    def _update_stats(self):
        self.lbl_turn.config(text=f"{self.turn}/9")
        self.lbl_wins.config(text=str(self.wins))
        self.lbl_losses.config(text=str(self.losses))
        self.lbl_coins.config(text=str(self.coins))

    def _update_section_styles(self):
        action_active = self.phase in ("setup", "action", "feedback")
        cpu_active = self.phase == "action"

        active_bg = self.SECTION_BG
        inactive_bg = "#15171c"
        active_bd = 2
        inactive_bd = 1

        self.cpu_section.config(bg=active_bg if cpu_active else inactive_bg,
                                 bd=active_bd if cpu_active else inactive_bd)
        self.activity_section.config(bg=active_bg if action_active else inactive_bg,
                                      bd=active_bd if action_active else inactive_bd)
        self.main_frame.config(bg=active_bg if action_active else inactive_bg)
        self.cpu_count_lbl.config(fg=self.FG if cpu_active else self.MUTED)

        for child in self.cpu_section.winfo_children():
            try:
                child.config(bg=active_bg if cpu_active else inactive_bg)
            except tk.TclError:
                pass

        for child in self.activity_section.winfo_children():
            if child is self.main_frame:
                continue
            try:
                child.config(bg=active_bg if action_active else inactive_bg)
            except tk.TclError:
                pass

        self.stats_frame.config(bg=inactive_bg)
        self.log_section.config(bg=inactive_bg)
        self.banner_frame.config(bg=inactive_bg)
        self.banner_label.config(bg=inactive_bg)

    def _effective_cpu(self):
        if self.cpu_color is None:
            return list(self.cpu_possible)
        if self.cpu_color == "black":
            return [c for c in self.cpu_possible if is_black(c)]
        return [c for c in self.cpu_possible if not is_black(c)]

    def _surviving(self):
        if self.my_card is None or self.feedback is None:
            return []
        eff = self._effective_cpu()
        if self.feedback == "win":
            return [c for c in eff if c < self.my_card]
        if self.feedback == "lose":
            return [c for c in eff if c > self.my_card]
        if self.feedback == "par":
            return [c for c in eff if c == self.my_card]
        return []

    def _get_warnings(self):
        """Genera avvisi se il computer è costretto a giocare mosse prevedibili."""
        warnings = []
        if not self.cpu_possible:
            return warnings

        if len(self.cpu_possible) == 1:
            warnings.append(f"Il computer ha in mano solo il {card_label(self.cpu_possible[0])}!")
            return warnings

        blacks = [c for c in self.cpu_possible if is_black(c)]
        whites = [c for c in self.cpu_possible if not is_black(c)]

        if not whites and blacks:
            warnings.append("Il computer ha esaurito le carte Bianche! Giocherà solo carte Nere ♠.")
        elif not blacks and whites:
            warnings.append("Il computer ha esaurito le carte Nere! Giocherà solo carte Bianche ♡.")

        return warnings

    def _get_suggestion(self):
        """
        Suggerimento AI basato su Expected Value con formula monete non lineare.

        Principi matematici:
        - monete = vittorie + max(0, vittorie - sconfitte) = vittorie + max(0, 2V-9)
        - La soglia critica è 5 vittorie: il 5° punto vale il doppio degli altri.
        - Obiettivo: massimizzare P(vittorie >= 5), non solo il win rate per turno.
        - Strategia: gioca la carta MINIMA che supera la soglia P(win) >= 60%
          rispetto alle carte CPU ancora possibili (aggiornate bayesianamente).
          Se nessuna carta raggiunge la soglia, sacrifica la più piccola disponibile.
        - La soglia si abbassa (40%) se siamo sotto il ritmo 5/9 necessario,
          e si alza (70%) se siamo già avanti per conservare le carte forti.
        """
        if not self.my_hand:
            return []

        # T0/T1: sacrifici fissi — matematicamente ottimali (0 e 1 non vincono quasi mai)
        if self.turn == 0:
            return [{"card": 0, "pct": 0, "fixed": "Sacrificio ottimale (EV)"}]
        if self.turn == 1:
            if 1 in self.my_hand:
                return [{"card": 1, "pct": 0, "fixed": "Sacrificio ottimale (EV)"}]
            else:
                return []

        # Carte CPU ancora possibili filtrate per colore (se noto)
        eff = self._effective_cpu()
        total = len(eff)
        if total == 0:
            return []

        # P(win) per ogni carta della mia mano rispetto alle CPU effettive
        def p_win(card):
            return sum(1 for x in eff if card > x) / total

        # Turni rimanenti (incluso questo)
        turns_left = 9 - self.turn
        wins_needed_for_5 = max(0, 5 - self.wins)

        # Soglia adattiva: se siamo in ritardo, abbassa la soglia per rischiare di più;
        # se siamo in vantaggio, alzala per conservare le carte alte.
        # Usiamo i turni rimanenti come riferimento (non quelli passati) per evitare
        # falsi allarmi ai primissimi turni dove wins=0 è normale.
        wins_needed_for_5 = max(0, 5 - self.wins)
        turns_left = 9 - self.turn
        pace_ok = (self.wins / max(self.turn, 1)) >= (5 / 9)

        if turns_left > 0 and wins_needed_for_5 > turns_left * 0.75:
            # Situazione critica: serve più del 75% di win rate nei turni rimanenti
            threshold = 0.40
        elif self.wins >= 5:
            # Già sopra soglia monete: conserva le carte alte
            threshold = 0.70
        else:
            # Ritmo normale: soglia matematica del 60%
            threshold = 0.60

        # Calcola P(win) e score EV per ogni carta
        # Score EV = P(win ora) - costo opportunità (penalità per usare una carta alta
        # quando non è necessario, perché potrebbe servire in un turno più favorevole)
        scored = []
        for card in self.my_hand:
            pw = p_win(card)
            # Costo opportunità: le carte alte hanno più valore futuro
            # (stima: ogni punto di valore carta = ~3% di win rate futuro medio)
            opportunity_cost = (card / 8) * 0.15
            ev_score = pw - opportunity_cost
            scored.append({
                "card": card,
                "pct": round(pw * 100),
                "ev": round(ev_score * 100, 1),
                "above_threshold": pw >= threshold,
            })

        # Ordina: prima quelli sopra soglia (per carta crescente = minimo sufficiente),
        # poi quelli sotto soglia (per EV score decrescente come fallback)
        above = sorted([s for s in scored if s["above_threshold"]], key=lambda s: s["card"])
        below = sorted([s for s in scored if not s["above_threshold"]], key=lambda s: -s["ev"])

        if above:
            # Strategia principale: carta minima che supera la soglia
            best = above[0]
            result = [{"card": best["card"], "pct": best["pct"], "ev": best["ev"],
                       "label": f"Min-Sufficient ≥{round(threshold*100)}% (EV)"}]
            # Mostra anche le alternative sopra soglia (max 2 extra)
            for alt in above[1:3]:
                result.append({"card": alt["card"], "pct": alt["pct"], "ev": alt["ev"]})
            return result
        else:
            # Nessuna carta sopra soglia: sacrifica la più piccola
            sacrifice = sorted(self.my_hand)[0]
            pw = p_win(sacrifice)
            return [{"card": sacrifice, "pct": round(pw * 100),
                     "ev": 0, "label": "Sacrificio (nessuna carta ≥ soglia)"}]

    def _cpu_hand_probabilities(self):
        """P(in mano) per carta del PC, dedotta dai turni passati della partita."""
        return cpu_hand_probabilities(self.cpu_possible, self.turn_history,
                                      self.cpu_confirmed_played)

    def _deduce_cpu_remaining(self):
        manual = set(self.cpu_possible)
        if not self.turn_history:
            return manual

        allowed_options = []
        for item in self.turn_history:
            color = item["cpu_color"]
            my_card = item["my_card"]
            feedback = item["feedback"]

            candidates = [c for c in manual if (is_black(c) if color == "black" else not is_black(c))]

            if feedback == "win":
                candidates = [c for c in candidates if c < my_card]
            elif feedback == "lose":
                candidates = [c for c in candidates if c > my_card]
            elif feedback == "par":
                candidates = [c for c in candidates if c == my_card]
            else:
                candidates = []

            if not candidates:
                return manual

            allowed_options.append(candidates)

        allowed_options.sort(key=len)

        possible_remaining = set()

        def dfs(index, used):
            if index == len(allowed_options):
                possible_remaining.update(manual - used)
                return
            for c in allowed_options[index]:
                if c in used:
                    continue
                used.add(c)
                dfs(index + 1, used)
                used.remove(c)

        dfs(0, set())
        return possible_remaining if possible_remaining else manual

    # ── RENDER ────────────────────────────────────────────────────────────────

    def _clear_main(self):
        for w in self.main_frame.winfo_children():
            w.destroy()

    def _section(self, text):
        tk.Label(self.main_frame, text=text.upper(), bg=self.BG, fg=self.MUTED,
                 font=self.small, anchor="w").pack(fill="x", pady=(8, 3))

    def _render_main(self):
        self._update_section_styles()
        self._clear_main()
        if self.done:
            return
        {"setup": self._render_setup,
         "action": self._render_action,
         "feedback": self._render_feedback}[self.phase]()

    def _render_cpu_deck(self):
        possible_count = len(self.cpu_possible)

        # Colore contatore: verde > 3, arancione <= 3, rosso = 1
        if possible_count == 1:
            count_color = self.RED
        elif possible_count <= 3:
            count_color = self.ORANGE
        else:
            count_color = self.FG

        self.cpu_count_lbl.config(text=f"Carte possibili: {possible_count}", fg=count_color)

        for w in self.cpu_deck_frame.winfo_children():
            w.destroy()

        probs = self._cpu_hand_probabilities()

        for c in ALL_CARDS:
            is_active = c in self.cpu_possible
            bg = self.CARD_BG if is_active else self.SECTION_BG
            fg = self.CARD_FG if is_active else self.MUTED
            bd = self.SEL_BD if is_active else self.BTN_BORDER

            outer = tk.Frame(self.cpu_deck_frame, bg=bd, padx=1, pady=1)
            outer.pack(side="left", padx=3)
            inner = tk.Frame(outer, bg=bg, width=48, height=78, bd=1, relief="solid")
            inner.pack()
            inner.pack_propagate(False)
            tk.Label(inner, text=str(c), bg=bg, fg=fg, font=self.bold).pack(expand=True)
            tk.Label(inner, text=suit(c), bg=bg, fg=fg, font=self.suit_font).pack()

            if is_active:
                pct = round(probs.get(c, 1.0) * 100)
                p_col = self.GREEN if pct >= 67 else (self.RED if pct < 34 else self.ORANGE)
                tk.Label(inner, text=f"{pct}%", bg=bg, fg=p_col, font=self.small).pack(pady=(0, 3))

            def on_click(event, card=c):
                if card in self.cpu_possible:
                    self.cpu_possible.remove(card)
                else:
                    self.cpu_possible.append(card)
                    self.cpu_possible.sort()
                self._render_cpu_deck()
                self._render_main()

            for w in [inner] + inner.winfo_children():
                w.bind("<Button-1>", on_click)

        # Aggiorna sezione carte già giocate dal computer
        for w in self.cpu_played_frame.winfo_children():
            w.destroy()

        played = getattr(self, "cpu_confirmed_played", [])
        if played:
            self.cpu_played_header.config(
                text=f"Carte giocate dal computer (dedotte): {', '.join(card_label(c) for c in played)}")
            for c in played:
                lbl = tk.Label(self.cpu_played_frame, text=card_label(c),
                               bg=self.PLAYED_BG, fg=self.PLAYED_FG,
                               font=self.small, padx=6, pady=2, relief="flat")
                lbl.pack(side="left", padx=2)
        else:
            self.cpu_played_header.config(text="Carte giocate dal computer (dedotte): nessuna")

    # ── FASI ──────────────────────────────────────────────────────────────────

    def _render_setup(self):
        self._section("Chi inizia per primo? (Serve solo per il log)")
        row = tk.Frame(self.main_frame, bg=self.BG)
        row.pack(anchor="w", pady=4)
        self._btn(row, "Inizio io", lambda: self._set_first("me")).pack(side="left", padx=(0, 8))
        self._btn(row, "Inizia il computer", lambda: self._set_first("cpu")).pack(side="left")

    def _set_first(self, who):
        self.who_first = who
        self.phase = "action"
        self._update_stats()
        self._render_main()

    def _render_action(self):
        # --- ALLARMI AI ---
        warnings = self._get_warnings()
        for w in warnings:
            tk.Label(self.main_frame, text=f"⚠️ ATTENZIONE: {w}", bg=self.WARN_BG, fg=self.WARN_FG,
                     font=self.bold, padx=10, pady=4, anchor="w").pack(fill="x", pady=(0, 6))

        # 1. Scelta colore computer
        tk.Label(self.main_frame, text="1. CHE COLORE HA GIOCATO IL COMPUTER?",
                 bg=self.BG, fg=self.MUTED, font=self.small).pack(anchor="w", pady=(0, 2))
        color_row = tk.Frame(self.main_frame, bg=self.BG)
        color_row.pack(anchor="w", pady=2)

        def pick_color(col):
            self.cpu_color = col
            if self.my_card is not None:
                self._go_feedback()
            else:
                self._render_main()

        for label, col in [("Nera ♠ (Pari)", "black"), ("Bianca ♡ (Dispari)", "white")]:
            bg = "#1a3a2a" if self.cpu_color == col else self.BTN_BG
            self._btn(color_row, label, lambda c=col: pick_color(c), bg=bg).pack(side="left", padx=(0, 8))

        # 2. Scelta carta giocatore
        tk.Label(self.main_frame, text="2. CHE CARTA HAI GIOCATO TU?",
                 bg=self.BG, fg=self.MUTED, font=self.small).pack(anchor="w", pady=(10, 2))
        cards_row = tk.Frame(self.main_frame, bg=self.BG)
        cards_row.pack(anchor="w", pady=2)

        eff = self._effective_cpu()
        total = len(eff)

        for c in sorted(self.my_hand):
            sel = self.my_card == c
            bg = self.SEL_BG if sel else self.CARD_BG
            fg = self.SEL_FG if sel else self.CARD_FG
            bd = self.SEL_BD if sel else ("#aaaaaa" if is_black(c) else "#555555")

            outer = tk.Frame(cards_row, bg=bd, padx=1, pady=1)
            outer.pack(side="left", padx=3)
            inner = tk.Frame(outer, bg=bg, width=46, height=78)
            inner.pack()
            inner.pack_propagate(False)
            tk.Label(inner, text=str(c), bg=bg, fg=fg, font=self.card_font).pack(expand=True)
            tk.Label(inner, text=suit(c), bg=bg, fg=fg, font=self.suit_font).pack()

            if total > 0:
                win = sum(1 for x in eff if c > x)
                pct = round(win / total * 100)
                pct_str = f"{pct}%"
                p_col = self.GREEN if pct >= 50 else (self.RED if pct < 30 else self.MUTED)
            else:
                pct_str = "-%"
                p_col = self.MUTED

            tk.Label(inner, text=pct_str, bg=bg, fg=p_col, font=self.small).pack(pady=(0, 3))

            def on_click(card=c):
                self.my_card = card
                if self.cpu_color is not None:
                    self._go_feedback()
                else:
                    self._render_main()

            for w in [inner] + inner.winfo_children():
                w.bind("<Button-1>", lambda e, f=on_click: f())

        # --- SUGGERIMENTO AI ---
        suggestions = self._get_suggestion()
        if suggestions:
            best = suggestions[0]
            if "fixed" in best:
                text = f"💡 {best['fixed']}: {card_label(best['card'])}"
            elif "label" in best and len(suggestions) == 1:
                text = f"💡 {best['label']}: {card_label(best['card'])} ({best['pct']}%)"
            elif "label" in best:
                medals = ["🥇", "🥈", "🥉"]
                righe = [f"{medals[0]} {card_label(best['card'])} → {best['pct']}%  [{best['label']}]"]
                for i, item in enumerate(suggestions[1:], 1):
                    righe.append(f"{medals[i]} {card_label(item['card'])} → {item['pct']}%")
                text = "💡 Strategia EV:\n" + "\n".join(righe)
            else:
                medals = ["🥇", "🥈", "🥉"]
                righe = [f"{medals[i]} {card_label(item['card'])} → {item['pct']}%"
                         for i, item in enumerate(suggestions)]
                text = "💡 Migliori giocate:\n" + "\n".join(righe)

            tk.Label(self.main_frame, text=text, justify="left",
                     bg="#2d2d00", fg="#ffd700", font=self.bold,
                     padx=10, pady=6, anchor="w").pack(fill="x", pady=(10, 0))

        # 3. Vai al feedback
        can_go = self.my_card is not None and self.cpu_color is not None
        btn_row = tk.Frame(self.main_frame, bg=self.BG)
        btn_row.pack(anchor="w", pady=(15, 0))
        self._btn(btn_row, "Avanti al Risultato", self._go_feedback,
                  bg="#1a4a2a" if can_go else self.BTN_BG,
                  fg=self.GREEN if can_go else self.MUTED,
                  state="normal" if can_go else "disabled").pack(side="left")

    def _go_feedback(self):
        self.phase = "feedback"
        self.feedback = None
        self._render_main()

    def _snapshot_state(self):
        return {
            "my_hand": self.my_hand.copy(),
            "cpu_possible": self.cpu_possible.copy(),
            "cpu_confirmed_played": list(self.cpu_confirmed_played),
            "turn": self.turn,
            "wins": self.wins,
            "losses": self.losses,
            "ties": self.ties,
            "coins": self.coins,
            "done": self.done,
            "who_first": self.who_first,
            "my_card": self.my_card,
            "cpu_color": self.cpu_color,
            "feedback": self.feedback,
            "phase": self.phase,
            "turn_history": [dict(item) for item in self.turn_history],
            "gomsg": self.gomsg.cget("text"),
            "log": self.log_text.get("1.0", "end"),
        }

    def _undo(self):
        if not self.history:
            return
        state = self.history.pop()
        self.my_hand = state["my_hand"]
        self.cpu_possible = state["cpu_possible"]
        self.cpu_confirmed_played = state.get("cpu_confirmed_played", [])
        self.turn = state["turn"]
        self.wins = state["wins"]
        self.losses = state["losses"]
        self.ties = state.get("ties", 0)
        self.coins = state["coins"]
        self.done = state["done"]
        self.who_first = state["who_first"]
        self.my_card = state["my_card"]
        self.cpu_color = state["cpu_color"]
        self.feedback = state["feedback"]
        self.phase = state["phase"]
        self.gomsg.config(text=state["gomsg"])
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.insert("1.0", state["log"])
        self.log_text.config(state="disabled")
        self.turn_history = [dict(item) for item in state["turn_history"]]
        self._update_stats()
        self._render_cpu_deck()
        self._render_main()
        self.undo_btn.config(state="normal" if self.history else "disabled")

    def _render_feedback(self):
        self._section(f"Rispetto alla tua carta {card_label(self.my_card)}, qual è il risultato?")
        row = tk.Frame(self.main_frame, bg=self.BG)
        row.pack(anchor="w", pady=4)

        for label, val, sel_bg, sel_fg in [
            ("Hai vinto", "win", "#1a3a2a", self.GREEN),
            ("Pari", "par", "#333333", self.FG),
            ("Hai perso", "lose", "#3a1a1a", self.RED),
        ]:
            sel = self.feedback == val
            self._btn(row, label, lambda v=val: self._set_feedback(v),
                      bg=sel_bg if sel else self.BTN_BG,
                      fg=sel_fg if sel else self.BTN_FG).pack(side="left", padx=(0, 6))

        tk.Label(self.main_frame,
                 text="Indica se il tuo punteggio è stato una vittoria, un pareggio o una sconfitta.",
                 bg=self.BG, fg=self.MUTED, font=self.small).pack(anchor="w", pady=(8, 0))

        if self.feedback is not None:
            surv = self._surviving()
            if surv:
                msg = f"Il computer ha giocato una di queste: {', '.join(card_label(c) for c in surv)}"
                tk.Label(self.main_frame, text=msg, bg=self.INFO_BG, fg=self.INFO_FG,
                         font=self.normal, padx=10, pady=6, anchor="w").pack(fill="x", pady=4)
            else:
                tk.Label(self.main_frame,
                         text="Errore Logico: Nessuna carta del computer compatibile coi dati inseriti.",
                         bg=self.WARN_BG, fg=self.WARN_FG,
                         font=self.normal, padx=10, pady=6, anchor="w").pack(fill="x", pady=4)

        btn_row = tk.Frame(self.main_frame, bg=self.BG)
        btn_row.pack(anchor="w", pady=(15, 4))

        can = self.feedback is not None and len(self._surviving()) > 0
        self._btn(btn_row, "Conferma Turno", self._confirm_turn,
                  bg="#1a4a2a" if can else self.BTN_BG,
                  fg=self.GREEN if can else self.MUTED,
                  state="normal" if can else "disabled").pack(side="left", padx=(0, 8))
        self._btn(btn_row, "Indietro", self._go_back).pack(side="left")

    def _set_feedback(self, val):
        self.feedback = val
        if len(self._surviving()) > 0:
            self._confirm_turn()
        else:
            self._render_main()

    def _go_back(self):
        self.phase = "action"
        self.feedback = None
        self._render_main()

    def _confirm_turn(self):
        surv = self._surviving()
        if not surv:
            return

        # Snapshot PRIMA di modificare lo stato (per undo corretto)
        self.history.append(self._snapshot_state())
        self.undo_btn.config(state="normal")

        # Deduzione carta computer
        deduced_card_str = ""
        if len(surv) == 1:
            exact_card = surv[0]
            if exact_card in self.cpu_possible:
                self.cpu_possible.remove(exact_card)
            self.cpu_confirmed_played.append(exact_card)
            deduced_card_str = f" [Dedotta: {card_label(exact_card)}]"
        else:
            deduced_card_str = f" [Era una tra: {', '.join(card_label(c) for c in surv)}]"

        # Rimuovi la carta giocata dal giocatore (una sola volta)
        if self.my_card in self.my_hand:
            self.my_hand.remove(self.my_card)

        # Aggiorna statistiche
        if self.feedback == "win":
            self.wins += 1
            res = "Vinto +1"
        elif self.feedback == "par":
            self.ties += 1
            res = "Pari"
        else:
            self.losses += 1
            res = "Perso"

        col_str = "Nera" if self.cpu_color == "black" else "Bianca"
        self._log(f"T{self.turn + 1}: {card_label(self.my_card)} vs {col_str} → {res}{deduced_card_str}")

        self.turn_history.append({
            "cpu_color": self.cpu_color,
            "my_card": self.my_card,
            "feedback": self.feedback,
        })

        self.cpu_possible = sorted(self._deduce_cpu_remaining())
        self.turn += 1
        self.my_card = None
        self.feedback = None
        self.cpu_color = None
        self.phase = "action"

        if not self.my_hand:
            self.done = True
            score_diff = self.wins - self.losses
            self.coins = self.wins + max(0, score_diff)
            result_str = "Vittoria! 🏆" if score_diff > 0 else ("Pareggio" if score_diff == 0 else "Sconfitta")
            self.gomsg.config(
                text=f"Partita Conclusa! {result_str} — "
                     f"{self.wins}V {self.losses}S {self.ties}P → {self.coins} monete")
            self._save_game_logs()

        self._update_stats()
        self._render_cpu_deck()
        self._render_main()

    def _save_game_logs(self):
        """Salva il log della partita nei file .txt e .json appropriati."""
        timestamp = datetime.now().isoformat()

        # Scegli i file in base a chi ha iniziato
        if self.who_first == "me":
            txt_file = resource_path("logs_IO.txt")
            json_file = resource_path("logs_IO.json")
            started_by_str = "Giocatore"
        else:
            txt_file = resource_path("logs_PC.txt")
            json_file = resource_path("logs_PC.json")
            started_by_str = "Computer"

        # ── Costruisci il log GUI invertito (come nel tuo formato di riferimento) ──
        gui_log_lines = self.log_text.get("1.0", "end").strip().splitlines()
        gui_log_lines_reversed = list(reversed(gui_log_lines))

        # ── Costruisci il blocco TXT ──
        lines = []
        lines.append("############################################################")
        lines.append(f"==== Partita: {timestamp} ====")
        lines.append(f"Iniziata da: {started_by_str}")
        lines.append(f"Vittorie: {self.wins}, Sconfitte: {self.losses}, Pari: {self.ties}, Monete: {self.coins}")
        lines.append("Turni:")
        for i, t in enumerate(self.turn_history):
            c = t["my_card"]
            color = t["cpu_color"]
            fb = t["feedback"]
            lines.append(f"T{i}: {card_label(c)} vs {color} -> {fb}")
        lines.append("Log GUI:")
        lines.extend(gui_log_lines_reversed)
        lines.append("############################################################")
        txt_block = "\n".join(lines) + "\n"

        # ── Scrivi TXT (append) ──
        try:
            with open(txt_file, "a", encoding="utf-8") as f:
                f.write(txt_block)
        except Exception as e:
            print(f"[WARN] Impossibile scrivere {txt_file}: {e}")

        # ── Costruisci il record JSON ──
        record = {
            "timestamp": timestamp,
            "started_by": "me" if self.who_first == "me" else "cpu",
            "wins": self.wins,
            "losses": self.losses,
            "ties": self.ties,
            "coins": self.coins,
            "turn_history": [dict(t) for t in self.turn_history],
        }

        # ── Scrivi JSON (una riga per record, append) ──
        try:
            with open(json_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[WARN] Impossibile scrivere {json_file}: {e}")

    def _log(self, text):
        self.log_text.config(state="normal")
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _clear_log(self):
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")


if __name__ == "__main__":
    root = tk.Tk()
    root.geometry("600x900")
    app = ContesaApp(root)
    root.mainloop()