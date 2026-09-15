"""
theme.py - central design system for the Developer Tracker desktop UI.

Tokens are (light, dark) tuples so CustomTkinter picks the right value for the
current appearance mode automatically. A `Colors` compatibility shim maps the
old flat colour names to the new tokens so existing handlers keep working.
"""
import tkinter as tk
import customtkinter as ctk

FAMILY = "Inter"   # system UI face on Windows; falls back gracefully elsewhere

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

# Website dark tokens, shared with the redesigned login. Keep legacy light tokens
# available for callers, while Verisade desktop windows explicitly select dark.
from login_design import BG, CARD, BORDER, PRIMARY, PRIMARY_INK, HOVER, SECONDARY, QUIET, hsl
_dark = {
    "bg": BG, "surface": CARD, "surface2": hsl(200,20,18), "surface3": BORDER,
    "ink": "#FFFFFF", "muted": SECONDARY, "faint": QUIET, "border": BORDER,
    "accent": PRIMARY, "accentHover": HOVER, "accentInk": PRIMARY_INK,
    "accentWeak": "#24233D", "active": hsl(142,65,48), "activeWeak": "#152F24",
    "activeHover": hsl(142,65,56), "idle": hsl(38,92,55), "idleWeak": "#332B1C",
    "idleHover": hsl(38,92,63), "stop": hsl(0,72,55), "stopHover": hsl(0,72,63),
    "stopWeak": "#351F24",
}
for _name, _value in _dark.items():
    COLORS[_name] = (COLORS.get(_name, (_value, _value))[0], _value)


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
        super().__init__(master, text="00:00:00", font=ctk.CTkFont(family="Space Grotesk", size=42, weight="bold"),
                         text_color=C("ink"), **kw)

    def update_progress(self, elapsed_seconds: float) -> None:
        e = int(max(0, elapsed_seconds))
        self.configure(text=f"{e // 3600:02d}:{(e % 3600) // 60:02d}:{e % 60:02d}")

    def reset(self) -> None:
        self.configure(text="00:00:00")


class ActivityRing(ctk.CTkFrame):
    """Compact DPI-aware activity gauge with the existing set(percent) API."""
    def __init__(self, master, size=118, thickness=6, **kw):
        super().__init__(master, fg_color="transparent", width=size, **kw)
        self._pct = 0.0
        self.val=ctk.CTkLabel(self,text="0%",font=font(25,"bold"),text_color=C("ink"))
        self.val.pack(anchor="e")
        self.sub=ctk.CTkLabel(self,text="ACTIVITY",font=font(10,"bold"),text_color=C("muted"))
        self.sub.pack(anchor="e",pady=(0,7))
        self.bar=ctk.CTkProgressBar(self,width=size,height=thickness,corner_radius=3,
                                   fg_color=C("surface3"),progress_color=C("accent"))
        self.bar.pack(fill="x")
        self.set(0)

    def set(self,pct):
        self._pct=max(0.0,min(100.0,float(pct)))
        self.val.configure(text=f"{int(round(self._pct))}%")
        self.bar.set(self._pct/100)

class ActionButton(ctk.CTkButton):
    """Status-colored actions with quiet disabled surfaces and readable labels."""
    def __init__(self, master, tone=None, **kwargs):
        self._action_tone=tone
        self._enabled_fill=kwargs.get('fg_color')
        super().__init__(master,**kwargs)
        self.configure(state=self.cget('state'))

    def configure(self, require_redraw=False, **kwargs):
        if 'fg_color' in kwargs:
            self._enabled_fill=kwargs['fg_color']
        state=kwargs.get('state',self.cget('state'))
        if self._action_tone and state=='disabled':
            kwargs['fg_color']=C(self._action_tone+'Weak')
            kwargs['border_color']=C(self._action_tone+'Weak')
        elif 'state' in kwargs and self._action_tone:
            kwargs['fg_color']=self._enabled_fill
            kwargs['border_color']=self._enabled_fill
        super().configure(require_redraw=require_redraw,**kwargs)


def metric_icon(kind):
    """Small monochrome line icons, rendered at high resolution for native DPI scaling."""
    from PIL import Image, ImageDraw
    image=Image.new('RGBA',(96,96))
    d=ImageDraw.Draw(image)
    color=hexof('accent')
    def line(points):d.line([(x*4,y*4) for x,y in points],fill=color,width=6,joint='curve')
    if kind==0:
        line([(2,12),(7,12),(10,5),(14,19),(17,12),(22,12)])
    elif kind==1:
        d.rounded_rectangle((8,20,88,76),radius=8,outline=color,width=6)
        for x in (6,10,14,18):line([(x,9),(x,10)])
        line([(7,15),(17,15)])
    elif kind==2:
        d.rounded_rectangle((24,8,72,88),radius=22,outline=color,width=6)
        line([(12,3),(12,10)])
    else:
        d.rounded_rectangle((8,12,88,76),radius=7,outline=color,width=6)
        line([(8,22),(16,22)]);line([(12,19),(12,22)])
    image=image.resize((48,48),Image.Resampling.LANCZOS)
    return ctk.CTkImage(light_image=image,dark_image=image,size=(18,18))
