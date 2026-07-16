"""
theme.py - central design system for the Developer Tracker desktop UI.

Tokens are (light, dark) tuples so CustomTkinter picks the right value for the
current appearance mode automatically. A `Colors` compatibility shim maps the
old flat colour names to the new tokens so existing handlers keep working.
"""
import tkinter as tk
import customtkinter as ctk

FAMILY = "Segoe UI"   # system UI face on Windows; falls back gracefully elsewhere

# ---- Design tokens: (light, dark) --------------------------------------------
COLORS = {
    "bg":          ("#F5F6F9", "#0D0F14"),
    "surface":     ("#FFFFFF", "#161922"),
    "surface2":    ("#EEF0F5", "#1E222C"),
    "surface3":    ("#E7EAF1", "#252A35"),
    "ink":         ("#171A21", "#EEF1F6"),
    "muted":       ("#676E7D", "#949AA8"),
    "faint":       ("#9AA0AD", "#6B7280"),
    "border":      ("#E4E7EE", "#262B36"),
    "accent":      ("#3D5AFE", "#6C82FF"),
    "accentHover": ("#2E49E0", "#5872F5"),
    "accentInk":   ("#FFFFFF", "#0D0F14"),
    "accentWeak":  ("#E9EDFF", "#1B2340"),
    "active":      ("#16A34A", "#3FB950"),
    "activeWeak":  ("#E4F5E9", "#132A1B"),
    "idle":        ("#C98A00", "#D9A400"),
    "idleWeak":    ("#FBF1DC", "#2C2410"),
    "stop":        ("#E5484D", "#FF6169"),
    "stopHover":   ("#D13B40", "#E5555C"),
    "stopWeak":    ("#FCE9EA", "#2E1618"),
}


def C(name: str):
    """Return the (light, dark) tuple for a token — pass straight to CTk."""
    return COLORS[name]


def hexof(name: str) -> str:
    """Resolve a token to a single hex for the CURRENT mode (for tk.Canvas etc.)."""
    idx = 1 if ctk.get_appearance_mode() == "Dark" else 0
    return COLORS[name][idx]


def font(size: int = 14, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(family=FAMILY, size=size, weight=weight)


def apply_appearance(mode: str = "light") -> None:
    ctk.set_appearance_mode(mode)
    ctk.set_default_color_theme("blue")


class Colors:
    """Back-compat shim: old flat names -> new theme tokens (theme-aware tuples)."""
    BG_PRIMARY   = COLORS["bg"]
    BG_SECONDARY = COLORS["surface"]
    BG_TERTIARY  = COLORS["surface2"]
    BG_DARK      = COLORS["ink"]
    ACCENT_BLUE  = COLORS["accent"]
    ACCENT_GREEN = COLORS["active"]
    ACCENT_PURPLE= COLORS["accent"]
    ACCENT_ORANGE= COLORS["idle"]
    ACCENT_RED   = COLORS["stop"]
    ACCENT_GOLD  = COLORS["idle"]
    TEXT_PRIMARY   = COLORS["ink"]
    TEXT_SECONDARY = COLORS["muted"]
    TEXT_MUTED     = COLORS["faint"]
    TEXT_LIGHT     = COLORS["accentInk"]
    BORDER_LIGHT = COLORS["border"]
    BORDER_DARK  = COLORS["border"]


# ---- Reusable widgets --------------------------------------------------------
class Card(ctk.CTkFrame):
    """Surface panel with a 1px border and rounded corners."""
    def __init__(self, master, radius: int = 14, pad: int = 20, **kw):
        super().__init__(master, fg_color=C("surface"), corner_radius=radius,
                         border_width=1, border_color=C("border"), **kw)
        self._pad = pad


class Pill(ctk.CTkLabel):
    """Small status pill. tone in {'active','idle','stop','accent'}."""
    def __init__(self, master, text: str, tone: str = "active", **kw):
        super().__init__(master, text="  " + text + "  ", corner_radius=999,
                         font=font(12, "bold"),
                         fg_color=C(tone + "Weak"), text_color=C(tone),
                         height=28, **kw)
        self._tone = tone

    def set(self, text: str, tone: str):
        self.configure(text="  " + text + "  ",
                       fg_color=C(tone + "Weak"), text_color=C(tone))


class BigTimer(ctk.CTkLabel):
    """Large tabular elapsed-time label. Drop-in for the old RadialTimerWidget:
    exposes update_progress(seconds) and reset()."""
    def __init__(self, master, **kw):
        super().__init__(master, text="00:00:00", font=font(52, "bold"),
                         text_color=C("ink"), **kw)

    def update_progress(self, elapsed_seconds: float) -> None:
        e = int(max(0, elapsed_seconds))
        self.configure(text=f"{e // 3600:02d}:{(e % 3600) // 60:02d}:{e % 60:02d}")

    def reset(self) -> None:
        self.configure(text="00:00:00")


class ActivityRing(ctk.CTkFrame):
    """Circular activity gauge drawn on a tk.Canvas (CTk has no conic gradient)."""
    def __init__(self, master, size: int = 176, thickness: int = 16, **kw):
        super().__init__(master, fg_color="transparent", **kw)
        self.size, self.th, self._pct = size, thickness, 0.0
        self.canvas = tk.Canvas(self, width=size, height=size,
                                highlightthickness=0, bd=0)
        self.canvas.pack()
        self.val = ctk.CTkLabel(self, text="0%", font=font(30, "bold"),
                                text_color=C("ink"), fg_color="transparent")
        self.val.place(relx=0.5, rely=0.44, anchor="center")
        self.sub = ctk.CTkLabel(self, text="ACTIVITY", font=font(10, "bold"),
                                text_color=C("muted"), fg_color="transparent")
        self.sub.place(relx=0.5, rely=0.60, anchor="center")
        self.set(0)

    def set(self, pct: float) -> None:
        self._pct = max(0.0, min(100.0, float(pct)))
        self.canvas.configure(bg=hexof("surface"))
        self.canvas.delete("all")
        pad = self.th // 2 + 3
        box = (pad, pad, self.size - pad, self.size - pad)
        self.canvas.create_arc(*box, start=90, extent=-359.999, style="arc",
                               width=self.th, outline=hexof("surface3"))
        if self._pct > 0:
            self.canvas.create_arc(*box, start=90, extent=-359.999 * (self._pct / 100),
                                   style="arc", width=self.th, outline=hexof("accent"))
        self.val.configure(text=f"{int(round(self._pct))}%", text_color=hexof("ink"))
