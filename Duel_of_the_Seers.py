import tkinter as tk
from tkinter import font as tkfont
import os, sys
from datetime import datetime
from functools import lru_cache
import json


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
        # PyInstaller crea una cartella temporanea e memorizza il percorso in _MEIPASS
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


class SeerGame:
    """Stato e logica di gioco/AI puri, senza dipendenze da Tkinter.

    Questa classe è completamente testabile in isolamento: la UI (``ContesaApp``)
    si limita a leggere lo stato e a invocare le transizioni.
    """

    def __init__(self):
        self.reset()

    # ── STATO ───────────────────────────────────────────────────────────────

    def reset(self):
        self.my_hand      = list(ALL_CARDS)
        self.cpu_possible = list(ALL_CARDS)
        self.turn         = 0
        self.wins         = 0
        self.losses       = 0
        self.ties         = 0
        self.coins        = 0
        self.done         = False
        self.who_first    = None
        self.my_card      = None
        self.cpu_color    = None
        self.feedback     = None
        self.phase        = "setup"
        self.turn_history = []
        self.log_lines    = []     # più recente in testa
        self.message      = ""     # messaggio di fine partita
        self._history     = []     # stack per l'undo

    # ── QUERY ────────────────────────────────────────────────────────────────

    def effective_cpu(self):
        """Carte del computer compatibili col colore giocato in questo turno."""
        if self.cpu_color is None:
            return list(self.cpu_possible)
        if self.cpu_color == "black":
            return [c for c in self.cpu_possible if is_black(c)]
        return [c for c in self.cpu_possible if not is_black(c)]

    def surviving(self):
        """Carte del computer compatibili con carta giocata + esito del turno."""
        if self.my_card is None or self.feedback is None:
            return []
        eff = self.effective_cpu()
        if self.feedback == "win":
            return [c for c in eff if c < self.my_card]
        if self.feedback == "lose":
            return [c for c in eff if c > self.my_card]
        if self.feedback == "par":
            return [c for c in eff if c == self.my_card]
        return []

    def get_warnings(self):
        """Genera avvisi se il computer è costretto a giocare mosse prevedibili."""
        warnings = []
        if not self.cpu_possible:
            return warnings

        # CPU ha solo 1 carta rimanente in totale
        if len(self.cpu_possible) == 1:
            warnings.append(f"Il computer ha in mano solo il {card_label(self.cpu_possible[0])}!")
            return warnings

        # Controlla i colori rimanenti
        blacks = [c for c in self.cpu_possible if is_black(c)]
        whites = [c for c in self.cpu_possible if not is_black(c)]

        if not whites and blacks:
            warnings.append("Il computer ha esaurito le carte Bianche! Giocherà solo carte Nere ♠.")
        elif not blacks and whites:
            warnings.append("Il computer ha esaurito le carte Nere! Giocherà solo carte Bianche ♡.")

        return warnings

    def get_suggestion(self):
        """Migliori carte da giocare ordinate per probabilità e conservazione."""
        if not self.my_hand:
            return []

        # Prime due mosse: suggerimenti fissi
        if self.turn == 0:
            if 0 in self.my_hand:
                return [{"card": 0, "pct": 0, "fixed": "Apertura consigliata"}]
            return []

        if self.turn == 1:
            if 1 in self.my_hand:
                return [{"card": 1, "pct": 0, "fixed": "Continuazione consigliata"}]
            return []

        # Dal terzo turno in poi: logica standard
        if self.cpu_color is None:
            if not self.cpu_possible:
                return []
            card_pcts = {c: round(sum(1 for x in self.cpu_possible if c > x) / len(self.cpu_possible) * 100)
                         for c in self.my_hand}
        else:
            eff = self.effective_cpu()
            total = len(eff)
            if total == 0:
                return []
            if self.my_card is not None:
                return []
            card_pcts = {c: round(sum(1 for x in eff if c > x) / total * 100)
                         for c in self.my_hand}

        if not card_pcts:
            return []

        # Conservazione risorse: preferiamo carte più basse se la probabilità è simile.
        card_scores = {c: card_pcts[c] - c * 2.5 for c in self.my_hand}
        sorted_cards = sorted(self.my_hand, key=lambda c: (-card_scores[c], c))

        # Se la probabilità massima è bassa, usiamo un sacrificio conservativo.
        max_pct = max(card_pcts.values())
        if max_pct < 35:
            lowest = sorted(self.my_hand)
            return [{"card": lowest[0], "pct": card_pcts[lowest[0]]}]

        return [{"card": c, "pct": card_pcts[c]} for c in sorted_cards[:3]]

    def deduce_cpu_remaining(self):
        """Deduce le carte ancora possibili del computer incrociando lo storico turni."""
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

    # ── EDITING MAZZO CPU ────────────────────────────────────────────────────

    def toggle_cpu_card(self, c):
        if c in self.cpu_possible:
            self.cpu_possible.remove(c)
        else:
            self.cpu_possible.append(c)
            self.cpu_possible.sort()

    def reset_cpu_deck(self):
        self.cpu_possible = list(ALL_CARDS)

    # ── TRANSIZIONI ──────────────────────────────────────────────────────────

    def set_first(self, who):
        self.who_first = who
        self.phase = "action"

    def pick_color(self, col):
        self.cpu_color = col
        if self.my_card is not None:
            self.go_feedback()

    def pick_card(self, c):
        self.my_card = c
        if self.cpu_color is not None:
            self.go_feedback()

    def go_feedback(self):
        self.phase = "feedback"
        self.feedback = None

    def go_back(self):
        self.phase = "action"
        self.feedback = None

    def set_feedback(self, val):
        self.feedback = val
        if self.surviving():
            self.confirm_turn()

    # ── UNDO ─────────────────────────────────────────────────────────────────

    def snapshot(self):
        return {
            "my_hand": self.my_hand.copy(),
            "cpu_possible": self.cpu_possible.copy(),
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
            "log_lines": self.log_lines.copy(),
            "message": self.message,
        }

    def _restore(self, s):
        self.my_hand      = s["my_hand"]
        self.cpu_possible = s["cpu_possible"]
        self.turn         = s["turn"]
        self.wins         = s["wins"]
        self.losses       = s["losses"]
        self.ties         = s.get("ties", 0)
        self.coins        = s["coins"]
        self.done         = s["done"]
        self.who_first    = s["who_first"]
        self.my_card      = s["my_card"]
        self.cpu_color    = s["cpu_color"]
        self.feedback     = s["feedback"]
        self.phase        = s["phase"]
        self.turn_history = [dict(item) for item in s["turn_history"]]
        self.log_lines    = s["log_lines"]
        self.message      = s["message"]

    def can_undo(self):
        return bool(self._history)

    def undo(self):
        if not self._history:
            return False
        self._restore(self._history.pop())
        return True

    # ── CONFERMA TURNO ───────────────────────────────────────────────────────

    def confirm_turn(self):
        """Applica il turno corrente. Restituisce True se applicato, False se invalido."""
        surv = self.surviving()
        if not surv:
            return False

        # Snapshot PRIMA di qualsiasi mutazione: così l'undo ripristina anche le
        # carte rimosse automaticamente per deduzione.
        self._history.append(self.snapshot())

        deduced_card_str = ""
        if len(surv) == 1:
            exact_card = surv[0]
            if exact_card in self.cpu_possible:
                self.cpu_possible.remove(exact_card)
                deduced_card_str = f" [Rimossa in auto: {card_label(exact_card)}]"
        else:
            deduced_card_str = f" [Era una tra: {','.join(str(c) for c in surv)}]"

        if self.my_card in self.my_hand:
            self.my_hand.remove(self.my_card)

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
        self._log(f"T{self.turn}: {card_label(self.my_card)} vs {col_str} → {res}{deduced_card_str}")

        self.turn_history.append({
            "turn": self.turn,
            "cpu_color": self.cpu_color,
            "my_card": self.my_card,
            "feedback": self.feedback,
            "candidates": list(surv),
            "cpu_card": surv[0] if len(surv) == 1 else None,
        })

        self.cpu_possible = sorted(self.deduce_cpu_remaining())

        self.turn     += 1
        self.my_card   = None
        self.feedback  = None
        self.cpu_color = None
        self.phase     = "action"

        if not self.my_hand:
            self.done = True
            score_diff = self.wins - self.losses
            bonus = score_diff if score_diff > 0 else 0
            self.coins = self.wins + bonus
            extra = f" ({self.wins}+{bonus} bonus margine)" if bonus else ""
            self.message = (f"Partita conclusa! {self.wins} vitt., {self.losses} scf., "
                            f"{self.ties} par. → {self.coins} monete{extra}.")
        return True

    def _log(self, text):
        self.log_lines.insert(0, text)

    def to_record(self):
        """Record serializzabile della partita, per il log su disco/analisi."""
        return {
            "who_first": self.who_first,
            "wins": self.wins,
            "losses": self.losses,
            "ties": self.ties,
            "coins": self.coins,
            "done": self.done,
            "turns": [dict(item) for item in self.turn_history],
        }


class ContesaApp:
    BG             = "#1b1b1f"
    FG             = "#f4f4f8"
    MUTED          = "#9aa0ad"
    CARD_BG        = "#252f3c"
    CARD_FG        = "#f4f4f8"
    SEL_BG         = "#22344f"
    SEL_FG         = "#a8d4ff"
    SEL_BD         = "#64b5ff"
    BTN_BG         = "#2b3340"
    BTN_FG         = "#f4f4f8"
    BTN_ACTIVE_BG  = "#3a4a61"
    BTN_ACTIVE_FG  = "#ffffff"
    BTN_BORDER     = "#4d5c71"
    GREEN          = "#4caf7d"
    RED            = "#ef5350"
    INFO_BG        = "#22303d"
    INFO_FG        = "#c8ebff"
    WARN_BG        = "#55372a"
    WARN_FG        = "#ffd87d"
    SECTION_BG     = "#222830"
    PANEL_BG       = "#232b36"
    LEGEND_BG      = "#1f2430"
    LEGEND_FG      = "#8b96ad"
    BANNER_IMAGE_PATH = resource_path("banner.png")

    def __init__(self, root):
        self.root = root
        self.game = SeerGame()
        self.root.title("Contesa dei Veggenti — Tracker & AI")
        self.root.configure(bg=self.BG)
        self.root.resizable(True, True)
        self.root.minsize(600, 760)

        self.bold       = tkfont.Font(family="Helvetica", size=11, weight="bold")
        self.normal     = tkfont.Font(family="Helvetica", size=11)
        self.small      = tkfont.Font(family="Helvetica", size=9)
        self.big        = tkfont.Font(family="Helvetica", size=18, weight="bold")
        self.card_font  = tkfont.Font(family="Helvetica", size=14, weight="bold")
        self.suit_font  = tkfont.Font(family="Helvetica", size=9)

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
        stats.pack(fill="x", padx=10, pady=(0, 4))
        self.stats_frame = stats
        self.lbl_turn   = self._stat_box(stats, "Turno",    "-")
        self.lbl_wins   = self._stat_box(stats, "Vittorie", "0", self.GREEN)
        self.lbl_losses = self._stat_box(stats, "Sconfitte","0", self.RED)
        self.lbl_coins  = self._stat_box(stats, "Monete",   "0")

        self.coins_hint = tk.Label(self.root,
                 text="Monete = vittorie + margine sul computer (solo se sei in vantaggio).",
                 bg=self.BG, fg=self.MUTED, font=self.small, anchor="w")
        self.coins_hint.pack(fill="x", padx=10, pady=(0, 8))

        self.cpu_section = tk.LabelFrame(self.root, text="Mazzo Computer", bg=self.SECTION_BG,
                                         fg=self.FG, font=self.small, labelanchor="nw",
                                         bd=1, relief="groove", padx=8, pady=8)
        self.cpu_section.pack(fill="x", padx=10, pady=(0, 8))

        header = tk.Frame(self.cpu_section, bg=self.SECTION_BG)
        header.pack(fill="x", pady=(0, 8))
        tk.Label(header, text="Clicca per scartare/recuperare carte.",
                 bg=self.SECTION_BG, fg=self.MUTED, font=self.small).pack(side="left")
        self._btn(header, "Ripristina mazzo", self._reset_cpu_deck,
                  bg=self.BTN_BG, fg=self.BTN_FG).pack(side="right", padx=(8,0))
        self.cpu_count_lbl = tk.Label(header, text="Carte possibili: 9", bg=self.SECTION_BG,
                                      fg=self.FG, font=self.small)
        self.cpu_count_lbl.pack(side="right")

        self.cpu_deck_frame = tk.Frame(self.cpu_section, bg=self.PANEL_BG, bd=1, relief="sunken",
                                       padx=10, pady=10)
        self.cpu_deck_frame.pack(fill="x")

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
        self.undo_btn.pack(side="left", padx=(8,0))
        self.gomsg = tk.Label(bot, text="", bg=self.BG, fg=self.GREEN, font=self.bold)
        self.gomsg.pack(side="left", padx=12)

        self.banner_frame = tk.Frame(self.root, bg=self.BG)
        self.banner_frame.pack(fill="both", padx=10, pady=(0, 10))
        self.banner_label = tk.Label(self.banner_frame, bg=self.BG, fg=self.MUTED,
                                     font=self.small, text=f"Caricamento banner...")
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
            except Exception as e:
                pass

        self.banner_label.config(text="Installa Pillow per mostrare il banner: pip install Pillow")
        self.banner_photo = None

    # ── BRIDGE UI ↔ LOGICA ─────────────────────────────────────────────────────

    def _init_game(self):
        self.game.reset()
        self._logged = False
        self._refresh()

    def _log_path(self):
        if getattr(sys, "frozen", False):
            base = os.path.dirname(sys.executable)
        else:
            base = SCRIPT_DIR
        log_dir = os.path.join(base, "logs")
        os.makedirs(log_dir, exist_ok=True)
        return os.path.join(log_dir, "duel_logs.jsonl")

    def _save_game_log(self):
        """Aggiunge la partita conclusa come una riga JSON. Non deve mai rompere il gioco."""
        try:
            rec = self.game.to_record()
            rec["timestamp"] = datetime.datetime.now().isoformat(timespec="seconds")
            with open(self._log_path(), "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            self.game.message += "  [salvata nel log]"
        except Exception:
            pass

    def _refresh(self):
        """Riallinea l'intera UI allo stato corrente del gioco."""
        self._update_stats()
        self._render_cpu_deck()
        self._render_main()
        self._render_log()
        self.gomsg.config(text=self.game.message)
        self.undo_btn.config(state="normal" if self.game.can_undo() else "disabled")

    def _reset_cpu_deck(self):
        self.game.reset_cpu_deck()
        self._render_cpu_deck()
        self._render_main()

    def _undo(self):
        if self.game.undo():
            if not self.game.done:
                self._logged = False
            self._refresh()

    def _update_stats(self):
        g = self.game
        self.lbl_turn.config(text=f"{g.turn}/9" if g.who_first else "-")
        self.lbl_wins.config(text=str(g.wins))
        self.lbl_losses.config(text=str(g.losses))
        self.lbl_coins.config(text=str(g.coins))

    def _update_section_styles(self):
        phase = self.game.phase
        action_active = phase in ("setup", "action", "feedback")
        cpu_active = phase == "action"

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
        self.coins_hint.config(bg=inactive_bg)
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
        if self.my_card is None or self.feedback is None: return []
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
        
        # CPU ha solo 1 carta rimanente in totale
        if len(self.cpu_possible) == 1:
            warnings.append(f"Il computer ha in mano solo il {card_label(self.cpu_possible[0])}!")
            return warnings

        # Controlla i colori rimanenti
        blacks = [c for c in self.cpu_possible if is_black(c)]
        whites = [c for c in self.cpu_possible if not is_black(c)]
        
        if not whites and blacks:
            warnings.append("Il computer ha esaurito le carte Bianche! Giocherà solo carte Nere ♠.")
        elif not blacks and whites:
            warnings.append("Il computer ha esaurito le carte Nere! Giocherà solo carte Bianche ♡.")
            
        return warnings

    @staticmethod
    def _coins(w, l):
        """Monete Veggenza: punti + margine se vinci la manche (regola ufficiale)."""
        return w + (w - l if w > l else 0)

    def _exact_coin_scores(self, hand, cpu_set, color):
        """Monete attese esatte per ogni mia carta, modellando il PC come uniforme
        sul set ancora possibile (i log mostrano che il PC gioca indipendentemente
        dalla mia carta). Il turno corrente è condizionato sul colore se già visibile.
        Ritorna [(carta, monete_attese, pct_vittoria), ...] ordinato dal migliore."""
        H0 = frozenset(hand)
        R0 = frozenset(cpu_set)

        @lru_cache(maxsize=None)
        def ec(H, R, w, l):
            if not H:
                return self._coins(w, l)
            best = -1.0
            for c in H:
                tot = len(R)
                if tot == 0:
                    v = ec(H - frozenset((c,)), R, w, l)
                else:
                    s = 0.0
                    for d in R:
                        s += ec(H - frozenset((c,)), R - frozenset((d,)),
                                w + (1 if c > d else 0), l + (1 if c < d else 0))
                    v = s / tot
                if v > best:
                    best = v
            return best

        if color is not None:
            pool = [d for d in R0 if (is_black(d) if color == "black" else not is_black(d))]
            if not pool:
                pool = list(R0)
        else:
            pool = list(R0)

        scores = []
        for c in sorted(hand):
            s = 0.0
            for d in pool:
                s += ec(H0 - frozenset((c,)), R0 - frozenset((d,)),
                        1 if c > d else 0, 1 if c < d else 0)
            ecoins = s / len(pool)
            pct = round(sum(1 for d in pool if c > d) / len(pool) * 100)
            scores.append((c, ecoins, pct))
        scores.sort(key=lambda x: (-x[1], x[0]))
        return scores

    def _get_suggestion(self):
        """Migliori carte da giocare: massimizza le MONETE attese sfruttando il set
        dedotto del PC e, quando visibile, il suo colore."""
        if not self.my_hand or self.my_card is not None:
            return []

        eff = self._effective_cpu()
        if not eff:
            return []

        # Late-game / set ristretto: calcolo esatto delle monete attese.
        if len(self.my_hand) <= 6 and len(self.cpu_possible) <= 7:
            scores = self._exact_coin_scores(self.my_hand, self.cpu_possible, self.cpu_color)
            return [{"card": c, "pct": pct} for (c, _ec, pct) in scores[:3]]

        # Early-game / set ancora ampio: euristica di conservazione.
        total = len(eff)
        def pct(c):
            return round(sum(1 for d in eff if c > d) / total * 100)

        if self.cpu_color is not None:
            # Colore visibile: vinci in modo efficiente con la minima carta che
            # supera la più bassa del PC, conservando le carte alte.
            lo = min(eff)
            winners = [c for c in sorted(self.my_hand) if c > lo]
            ranked = (winners + [c for c in sorted(self.my_hand) if c <= lo]) if winners \
                     else sorted(self.my_hand)
        else:
            # Nessuna info sul colore: 0 e 1 non vincono mai (dai log) → sacrifica
            # dal basso e conserva le carte alte.
            ranked = sorted(self.my_hand)

        # Ordina le carte per probabilità di vittoria (`pct`) decrescente
        ranked_by_pct = sorted(ranked, key=lambda c: (-pct(c), c))
        return [{"card": c, "pct": pct(c)} for c in ranked_by_pct[:3]]

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
                 font=self.small, anchor="w").pack(fill="x", pady=(8,3))

    def _render_main(self):
        self._update_section_styles()
        self._clear_main()
        if self.game.done:
            return
        {"setup":    self._render_setup,
         "action":   self._render_action,
         "feedback": self._render_feedback}[self.game.phase]()

    def _render_cpu_deck(self):
        possible_count = len(self.game.cpu_possible)
        self.cpu_count_lbl.config(text=f"Carte possibili: {possible_count}",
                                  fg=self.RED if possible_count == 1 else self.FG)

        for w in self.cpu_deck_frame.winfo_children():
            w.destroy()

        for c in ALL_CARDS:
            is_active = c in self.game.cpu_possible
            bg = self.CARD_BG if is_active else self.SECTION_BG
            fg = self.CARD_FG if is_active else self.MUTED
            bd = self.SEL_BD if is_active else self.BTN_BORDER

            outer = tk.Frame(self.cpu_deck_frame, bg=bd, padx=1, pady=1)
            outer.pack(side="left", padx=3)
            inner = tk.Frame(outer, bg=bg, width=48, height=66, bd=1, relief="solid")
            inner.pack()
            inner.pack_propagate(False)

            tk.Label(inner, text=str(c), bg=bg, fg=fg, font=self.bold).pack(expand=True)
            tk.Label(inner, text=suit(c), bg=bg, fg=fg, font=self.suit_font).pack()

            def on_click(event, card=c):
                self.game.toggle_cpu_card(card)
                self._render_cpu_deck()
                self._render_main()

            for w in [inner] + inner.winfo_children():
                w.bind("<Button-1>", on_click)

    def _render_log(self):
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        if self.game.log_lines:
            self.log_text.insert("1.0", "\n".join(self.game.log_lines) + "\n")
        self.log_text.config(state="disabled")

    # ── FASI ──────────────────────────────────────────────────────────────────

    def _render_setup(self):
        self._section("Chi inizia per primo? (Serve solo per il log)")
        row = tk.Frame(self.main_frame, bg=self.BG)
        row.pack(anchor="w", pady=4)
        self._btn(row, "Inizio io",            lambda: self._set_first("me")).pack(side="left", padx=(0,8))
        self._btn(row, "Inizia il computer",   lambda: self._set_first("cpu")).pack(side="left")

    def _set_first(self, who):
        self.game.set_first(who)
        self._refresh()

    def _render_action(self):

        # --- ALLARMI AI ---
        warnings = self.game.get_warnings()
        for w in warnings:
            tk.Label(self.main_frame, text=f"⚠️ ATTENZIONE: {w}", bg=self.WARN_BG, fg=self.WARN_FG,
                     font=self.bold, padx=10, pady=4, anchor="w").pack(fill="x", pady=(0, 6))

        # --- INSIGHT DAI LOG REALI ---
        if self.who_first == "cpu":
            tip = ("📊 Inizia il PC: imposta prima il suo COLORE qui sotto, poi scegli la carta — "
                   "il suggerimento sfrutta quell'informazione (vale ~1 moneta in più a partita).")
        else:
            tip = ("📊 Il PC gioca a caso e non contrasta la tua carta: 0–1 non vincono mai "
                   "(sacrificali), le carte ≥4 vincono quasi sempre.")
        tk.Label(self.main_frame, text=tip, bg=self.INFO_BG, fg=self.INFO_FG,
                 font=self.small, padx=10, pady=4, anchor="w", justify="left",
                 wraplength=560).pack(fill="x", pady=(0, 6))

        # 1. Scelta colore computer
        tk.Label(self.main_frame, text="1. CHE COLORE HA GIOCATO IL COMPUTER?", bg=self.BG, fg=self.MUTED, font=self.small).pack(anchor="w", pady=(0,2))
        color_row = tk.Frame(self.main_frame, bg=self.BG)
        color_row.pack(anchor="w", pady=2)

        def pick_color(col):
            self.game.pick_color(col)
            self._refresh()

        for label, col in [("Nera ♠ (Pari)", "black"), ("Bianca ♡ (Dispari)", "white")]:
            bg = "#1a3a2a" if self.game.cpu_color == col else self.BTN_BG
            self._btn(color_row, label, lambda c=col: pick_color(c), bg=bg).pack(side="left", padx=(0,8))

        # 2. Scelta carta giocatore
        tk.Label(self.main_frame, text="2. CHE CARTA HAI GIOCATO TU?", bg=self.BG, fg=self.MUTED, font=self.small).pack(anchor="w", pady=(10,2))
        cards_row = tk.Frame(self.main_frame, bg=self.BG)
        cards_row.pack(anchor="w", pady=2)

        eff = self.game.effective_cpu()
        total = len(eff)

        for c in sorted(self.game.my_hand):
            sel = self.game.my_card == c
            bg  = self.SEL_BG if sel else self.CARD_BG
            fg  = self.SEL_FG if sel else self.CARD_FG
            bd  = self.SEL_BD if sel else ("#aaaaaa" if is_black(c) else "#555555")

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

            tk.Label(inner, text=pct_str, bg=bg, fg=p_col, font=self.small).pack(pady=(0,3))

            def on_click(card=c):
                self.game.pick_card(card)
                self._refresh()

            for w in [inner] + inner.winfo_children():
                w.bind("<Button-1>", lambda e, f=on_click: f())

        # --- SUGGERIMENTO AI ---
        suggestions = self.game.get_suggestion()

        if suggestions:
            best = suggestions[0]

            if "fixed" in best:
                text = f"💡 {best['fixed']}: {card_label(best['card'])}"
            elif self.game.turn == 0 or self.game.turn == 1:
                text = f"💡 Suggerimento AI: Gioca {card_label(best['card'])}"
            elif len(suggestions) == 1:
                text = f"💡 Suggerimento AI: Gioca {card_label(best['card'])} ({best['pct']}%)"
            else:
                righe = []
                medals = ["🥇", "🥈", "🥉"]
                for i, item in enumerate(suggestions):
                    righe.append(
                        f"{medals[i]} {card_label(item['card'])} → {item['pct']}%"
                    )
                text = (
                    "💡 Migliori giocate:\n" +
                    "\n".join(righe)
                )

            tk.Label(
                self.main_frame,
                text=text,
                justify="left",
                bg="#2d2d00",
                fg="#ffd700",
                font=self.bold,
                padx=10,
                pady=6,
                anchor="w"
            ).pack(fill="x", pady=(10, 0))

        # 3. Vai al feedback
        can_go = self.game.my_card is not None and self.game.cpu_color is not None
        btn_row = tk.Frame(self.main_frame, bg=self.BG)
        btn_row.pack(anchor="w", pady=(15,0))
        self._btn(btn_row, "Avanti al Risultato", self._go_feedback,
                  bg="#1a4a2a" if can_go else self.BTN_BG,
                  fg=self.GREEN if can_go else self.MUTED,
                  state="normal" if can_go else "disabled").pack(side="left")

    def _go_feedback(self):
        self.game.go_feedback()
        self._refresh()

    def _render_feedback(self):
        self._section(f"Rispetto alla tua carta {card_label(self.game.my_card)}, qual è il risultato?")

        row = tk.Frame(self.main_frame, bg=self.BG)
        row.pack(anchor="w", pady=4)

        for label, val, sel_bg, sel_fg in [
            ("Hai vinto",  "win",  "#1a3a2a", self.GREEN),
            ("Pari",            "par",  "#333333", self.FG),
            ("Hai perso", "lose", "#3a1a1a", self.RED),
        ]:
            sel = self.game.feedback == val
            self._btn(row, label, lambda v=val: self._set_feedback(v),
                      bg=sel_bg if sel else self.BTN_BG,
                      fg=sel_fg if sel else self.BTN_FG).pack(side="left", padx=(0,6))

        tk.Label(self.main_frame,
                 text="Indica se il tuo punteggio è stato una vittoria, un pareggio o una sconfitta.",
                 bg=self.BG, fg=self.MUTED, font=self.small).pack(anchor="w", pady=(8,0))

        if self.game.feedback is not None:
            surv = self.game.surviving()
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
        btn_row.pack(anchor="w", pady=(15,4))

        can = self.game.feedback is not None and len(self.game.surviving()) > 0
        self._btn(btn_row, "Conferma Turno", self._confirm_turn,
                  bg="#1a4a2a" if can else self.BTN_BG,
                  fg=self.GREEN if can else self.MUTED,
                  state="normal" if can else "disabled").pack(side="left", padx=(0,8))
        self._btn(btn_row, "Indietro", self._go_back).pack(side="left")

    def _set_feedback(self, val):
        self.game.set_feedback(val)
        self._refresh()

    def _go_back(self):
        self.game.go_back()
        self._refresh()

    def _confirm_turn(self):
        surv = self._surviving()
        if not surv:
            return

        deduced_card_str = ""
        if len(surv) == 1:
            exact_card = surv[0]
            if exact_card in self.cpu_possible:
                self.cpu_possible.remove(exact_card)
                deduced_card_str = f" [Rimossa in auto: {card_label(exact_card)}]"
        else:
            deduced_card_str = f" [Era una tra: {','.join(str(c) for c in surv)}]"

        self.history.append(self._snapshot_state())
        self.undo_btn.config(state="normal")
        if self.my_card in self.my_hand:
            self.my_hand.remove(self.my_card)

        if self.feedback == "win":
            self.wins  += 1
            res = "Vinto +1"
        elif self.feedback == "par":
            self.ties += 1
            res = "Pari"
        else:
            self.losses += 1
            res = "Perso"

        col_str = "Nera" if self.cpu_color == "black" else "Bianca"
        self._log(f"T{self.turn}: {card_label(self.my_card)} vs {col_str} → {res}{deduced_card_str}")

        self.turn_history.append({
            "cpu_color": self.cpu_color,
            "my_card": self.my_card,
            "feedback": self.feedback,
        })

        self.cpu_possible = sorted(self._deduce_cpu_remaining())

        self.turn     += 1
        self.my_card   = None
        self.feedback  = None
        self.cpu_color = None
        self.phase     = "action"

        if not self.my_hand:
            self.done = True
            cpu_score = self.losses
            my_score = self.wins
            score_diff = my_score - cpu_score
            if score_diff > 0:
                self.coins = self.wins + score_diff
            else:
                self.coins = self.wins
            self.gomsg.config(
                text=f"Partita Conclusa! {self.wins} vitt, {self.losses} scf, {self.ties} par → {self.coins} monete.")
            # Salva i log della partita appena conclusa
            try:
                self._save_game_log()
            except Exception:
                pass

        self._update_stats()
        self._render_cpu_deck()
        self._render_main()

    def _log(self, text):
        self.log_text.config(state="normal")
        self.log_text.insert("1.0", text + "\n")
        self.log_text.config(state="disabled")

    def _clear_log(self):
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")

    def _save_game_log(self):
        """Salva l'intero log della partita su logs.txt nella cartella principale del progetto."""
        try:
            # Use script directory as project root (logs are next to the script)
            project_root = SCRIPT_DIR

            # Choose file based on who started
            if self.who_first == "me":
                target_file = "logs_IO.txt"
            else:
                target_file = "logs_PC.txt"

            logs_path = os.path.join(project_root, target_file)

            sep = "#" * 60
            header = f"==== Partita: {datetime.now().isoformat()} ===="
            started_by = "Iniziata da: Giocatore" if self.who_first == "me" else "Iniziata da: Computer"
            final = (
                f"Vittorie: {self.wins}, Sconfitte: {self.losses}, "
                f"Pari: {self.ties}, Monete: {self.coins}"
            )

            lines = [sep, header, started_by, final, "Turni:"]
            for i, t in enumerate(self.turn_history):
                card = card_label(t.get("my_card")) if t.get("my_card") is not None else "-"
                color = t.get("cpu_color") or "-"
                fb = t.get("feedback") or "-"
                lines.append(f"T{i}: {card} vs {color} -> {fb}")

            lines.append("Log GUI:")
            gui_log = self.log_text.get("1.0", "end").strip()
            if gui_log:
                lines.extend(gui_log.splitlines())

            lines.append(sep)

            with open(logs_path, "a", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")

            # Also append a JSON record (ndjson) for easier analysis
            json_obj = {
                "timestamp": datetime.now().isoformat(),
                "started_by": "me" if self.who_first == "me" else "cpu",
                "wins": self.wins,
                "losses": self.losses,
                "ties": self.ties,
                "coins": self.coins,
                "turn_history": self.turn_history,
            }
            json_path = os.path.splitext(logs_path)[0] + ".json"
            try:
                with open(json_path, "a", encoding="utf-8") as jf:
                    jf.write(json.dumps(json_obj, ensure_ascii=False) + "\n")
            except Exception:
                pass

            # Mostra conferma all'utente
            self._log(f"Log salvato su {logs_path}")
        except Exception as e:
            self._log(f"Errore salvataggio log: {e}")


if __name__ == "__main__":
    root = tk.Tk()
    root.geometry("600x900")
    app = ContesaApp(root)
    root.mainloop()
