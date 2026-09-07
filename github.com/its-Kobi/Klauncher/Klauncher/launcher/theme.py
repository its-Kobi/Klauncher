from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict

DEFAULT_THEME = {
    "accent": "#2d7dff",
    "accent_hover": "#3a85ff",
    "bg_primary": "#0a0c10",
    "bg_secondary": "#14171e",
    "bg_panel": "#1a1f2b",
    "bg_card": "#1e2433",
    "bg_card_hover": "#252e42",
    "text_primary": "#eef2fb",
    "text_secondary": "#8a92a8",
    "text_muted": "#5c657a",
    "border": "#222a3a",
    "gradient_from": "#0f1420",
    "gradient_to": "#0a0c10",
    "use_gradient": True,
    "animations": True,
}

@dataclass
class Theme:
    accent: str = DEFAULT_THEME["accent"]
    accent_hover: str = DEFAULT_THEME["accent_hover"]
    bg_primary: str = DEFAULT_THEME["bg_primary"]
    bg_secondary: str = DEFAULT_THEME["bg_secondary"]
    bg_panel: str = DEFAULT_THEME["bg_panel"]
    bg_card: str = DEFAULT_THEME["bg_card"]
    bg_card_hover: str = DEFAULT_THEME["bg_card_hover"]
    text_primary: str = DEFAULT_THEME["text_primary"]
    text_secondary: str = DEFAULT_THEME["text_secondary"]
    text_muted: str = DEFAULT_THEME["text_muted"]
    border: str = DEFAULT_THEME["border"]
    gradient_from: str = DEFAULT_THEME["gradient_from"]
    gradient_to: str = DEFAULT_THEME["gradient_to"]
    use_gradient: bool = DEFAULT_THEME["use_gradient"]
    animations: bool = DEFAULT_THEME["animations"]

    @classmethod
    def from_dict(cls, d: dict) -> "Theme":
        base = DEFAULT_THEME.copy()
        base.update({k: v for k, v in d.items() if k in base})
        return cls(**base)

    def to_dict(self) -> dict:
        return asdict(self)

    # --- contrast helpers ---
    def _hex_to_rgb(self, h: str):
        h = h.lstrip("#")
        if len(h) == 3:
            h = "".join(c*2 for c in h)
        try:
            return int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
        except:
            return 10,12,16

    def _linear(self, c):
        c/=255.0
        return c/12.92 if c <= 0.04045 else ((c+0.055)/1.055)**2.4

    def luminance(self, hexcol: str) -> float:
        r,g,b = self._hex_to_rgb(hexcol)
        return 0.2126*self._linear(r) + 0.7152*self._linear(g) + 0.0722*self._linear(b)

    def is_dark(self, hexcol: str) -> bool:
        return self.luminance(hexcol) < 0.5

    def contrast_ratio(self, a: str, b: str) -> float:
        la = self.luminance(a); lb = self.luminance(b)
        l1, l2 = (la, lb) if la > lb else (lb, la)
        return (l1 + 0.05) / (l2 + 0.05)

    def effective_text(self, bg: str, preferred: str) -> str:
        # if contrast too low, auto-pick black/white for readability
        if self.contrast_ratio(bg, preferred) < 3.0:
            return "#eef2fb" if self.is_dark(bg) else "#0a0c10"
        return preferred

    def icon_color(self, bg: str) -> str:
        # keep accent separate, use luminance to pick light/dark icon
        return "#eef2fb" if self.is_dark(bg) else "#0a0c10"

    def _rgba(self, hexcol: str, alpha: float) -> str:
        r,g,b=self._hex_to_rgb(hexcol)
        a=int(max(0,min(1,alpha))*255)
        return f"rgba({r},{g},{b},{a})"

    def _font_family(self, config_minecraft: bool = True) -> str:
        # Always Minecraft — no toggle, default forever
        try:
            from launcher.fonts import body_family
            bf=body_family()
            return f"'{bf}', 'Segoe UI', 'Inter', sans-serif"
        except:
            return "'Monocraft', 'Segoe UI', 'Inter', sans-serif"
    def _title_font(self) -> str:
        try:
            from launcher.fonts import title_family
            tf=title_family()
            return f"'{tf}', 'Monocraft', sans-serif"
        except:
            return "'Monocraft', sans-serif"

    def qss(self) -> str:
        # Full-window gradient under everything, low opacity peeking through panels
        if self.use_gradient:
            # smooth vertical veil - will be behind all widgets
            bg = f"qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {self.gradient_from}, stop:1 {self.gradient_to})"
            # panels/cards slightly translucent so gradient shows with low opacity underneath
            panel_bg = self._rgba(self.bg_panel, 0.92)
            card_bg = self._rgba(self.bg_card, 0.88)
            card_hover = self._rgba(self.bg_card_hover, 0.94)
        else:
            bg = self.bg_primary
            panel_bg = self.bg_panel
            card_bg = self.bg_card
            card_hover = self.bg_card_hover
        # Clear tinted icon cache when theme changes so light/dark icons retint correctly
        try:
            from launcher.assets import clear_tinted_cache
            clear_tinted_cache()
        except:
            pass
        # per-surface effective text for visibility across custom light/dark combos
        eff_text = self.effective_text(self.bg_primary, self.text_primary)
        eff_sec = self.effective_text(self.bg_primary, self.text_secondary)
        eff_muted = self.effective_text(self.bg_primary, self.text_muted)
        eff_card_text = self.effective_text(self.bg_card, self.text_primary)
        eff_card_sec = self.effective_text(self.bg_card, self.text_secondary)
        eff_panel_text = self.effective_text(self.bg_panel, self.text_primary)
        eff_panel_sec = self.effective_text(self.bg_panel, self.text_secondary)
        eff_sidebar_text = self.effective_text(self.bg_secondary, self.text_primary)
        eff_sidebar_sec = self.effective_text(self.bg_secondary, self.text_secondary)
        eff_sidebar_muted = self.effective_text(self.bg_secondary, self.text_muted)
        # sidebar icon color based on sidebar bg
        # keep panel/card text same as effective
        ffam = self._font_family()
        tfam = self._title_font()
        # Adaptive colors for log and scrollbars
        log_bg = self.bg_panel if not self.is_dark(self.bg_primary) else "#0c0e14"
        log_fg = eff_panel_text if not self.is_dark(self.bg_primary) else "#aab4c8"
        scroll_handle = "#cbd5e1" if not self.is_dark(self.bg_primary) else "#2a344d"
        scroll_handle_hover = "#94a3b8" if not self.is_dark(self.bg_primary) else "#34425f"
        card_hover_border = self.border if not self.is_dark(self.bg_primary) else "#2a3550"
        # Accent text: off-white accent → black text for readability
        accent_text = self.effective_text(self.accent, "#ffffff")
        # if accent is very light, effective_text returns #0a0c10 (black)
        accent_hover_text = self.effective_text(self.accent_hover, "#ffffff")
        return f"""
QMainWindow {{ background: {bg}; }}
QWidget {{ background: transparent; color: {eff_text}; font-family: {ffam}; font-size: 13px; }}
QLabel#pageTitle, QLabel#brand {{ font-family: {tfam}; }}
QFrame#appBg {{ background: {bg}; }}
QFrame#sidebar {{ background: {self.bg_secondary}; border-right: 1px solid {self.border}; }}
QFrame#sidebarInner {{ background: transparent; }}
QLabel#brand {{ font-size: 17px; font-weight: 800; letter-spacing: 0.6px; color: {eff_sidebar_text}; }}
QLabel#brandSub {{ font-size: 10px; font-weight: 600; letter-spacing: 1.2px; color: {eff_sidebar_muted}; }}
QLabel#pageTitle {{ font-size: 22px; font-weight: 800; color: {eff_text}; letter-spacing: -0.3px; }}
QLabel#pageSub {{ font-size: 13px; color: {eff_sec}; }}
QLabel#cardTitle {{ font-size: 13px; font-weight: 700; color: {eff_card_text}; }}
QLabel#muted {{ color: {eff_sec}; font-size: 12px; }}
QLabel#caption {{ color: {eff_muted}; font-size: 11px; }}
QFrame#card {{ background: {card_bg}; border: 1px solid {self.border}; border-radius: 14px; }}
QFrame#card QLabel#cardTitle {{ color: {eff_card_text}; }}
QFrame#card QLabel#muted {{ color: {eff_card_sec}; }}
QFrame#card QLabel#caption {{ color: {self.effective_text(self.bg_card, self.text_muted)}; }}
QFrame#card:hover {{ background: {card_hover}; border: 1px solid {card_hover_border}; }}
QFrame#panel {{ background: {panel_bg}; border: 1px solid {self.border}; border-radius: 14px; }}
QFrame#panel QLabel#cardTitle {{ color: {eff_panel_text}; }}
QFrame#panel QLabel#caption {{ color: {self.effective_text(self.bg_panel, self.text_muted)}; }}
QPushButton#navButton {{ text-align: left; padding: 10px 12px; border-radius: 10px; color: {eff_sidebar_sec}; font-size: 13px; font-weight: 600; border: none; background: transparent; }}
QPushButton#navButton:hover {{ background: {self.bg_card}; color: {eff_sidebar_text}; }}
QPushButton#navButton:checked {{ background: {self.accent}; color: {accent_text}; }}
QPushButton#navButton:checked:hover {{ background: {self.accent_hover}; color: {accent_hover_text}; }}
QPushButton#playButton {{ background: {self.accent}; color: {accent_text}; font-size: 14px; font-weight: 800; padding: 14px 22px; border-radius: 12px; letter-spacing: 0.4px; border: none; }}
QPushButton#playButton:hover {{ background: {self.accent_hover}; color: {accent_hover_text}; }}
QPushButton#playButton:disabled {{ background: {self.bg_card}; color: {eff_muted}; }}
QPushButton#secondaryButton {{ background: {self.bg_card}; color: {eff_card_text}; padding: 8px 14px; border-radius: 10px; font-weight: 600; border: 1px solid {self.border}; }}
QPushButton#secondaryButton:hover {{ background: {self.bg_card_hover}; border: 1px solid {card_hover_border}; }}
QPushButton#ghostButton {{ background: transparent; color: {eff_sec}; padding: 7px 12px; border-radius: 9px; border: none; }}
QPushButton#ghostButton:hover {{ background: {self.bg_card}; color: {eff_text}; }}
QLineEdit, QSpinBox, QComboBox {{ background: {self.bg_panel}; border: 1px solid {self.border}; border-radius: 10px; padding: 8px 12px; color: {eff_panel_text}; selection-background-color: {self.accent}; selection-color: {accent_text}; }}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border: 1px solid {self.accent}; }}
QComboBox QAbstractItemView {{ background: {self.bg_panel}; border: 1px solid {self.border}; selection-background-color: {self.accent}; selection-color: {accent_text}; color: {eff_panel_text}; }}
QTextEdit#logView {{ background: {log_bg}; border: 1px solid {self.border}; border-radius: 10px; font-family: 'Consolas', monospace; font-size: 11px; color: {log_fg}; padding: 8px; }}
QProgressBar {{ background: {self.bg_panel}; border: none; border-radius: 6px; height: 6px; text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {self.accent}; border-radius: 6px; }}
QLabel#badge {{ font-size: 10px; font-weight: 700; padding: 4px 8px; border-radius: 8px; letter-spacing: 0.4px; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget {{ background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 4px; }}
QScrollBar::handle:vertical {{ background: {scroll_handle}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {scroll_handle_hover}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QMenu {{ background: {self.bg_panel}; border: 1px solid {self.border}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 7px 14px; border-radius: 7px; color: {eff_text}; }}
QMenu::item:selected {{ background: {self.bg_card_hover}; }}
QMenu::separator {{ height: 1px; background: {self.border}; margin: 6px 8px; }}
QStackedWidget {{ background: transparent; }}
"""

_theme_instance: Theme | None = None

def get_theme() -> Theme:
    global _theme_instance
    if _theme_instance is None:
        _theme_instance = load_theme()
    return _theme_instance

def load_theme() -> Theme:
    try:
        from launcher import paths
        cfg_path = paths.get_data_dir() / "config.json"
        if cfg_path.exists():
            import json
            with open(cfg_path, encoding="utf-8") as f:
                data = json.load(f)
            t = data.get("theme")
            if isinstance(t, dict):
                return Theme.from_dict(t)
    except:
        pass
    return Theme()

def save_theme(theme: Theme):
    global _theme_instance
    _theme_instance = theme
    try:
        from launcher import paths
        import json
        cfg_path = paths.get_data_dir() / "config.json"
        data = {}
        if cfg_path.exists():
            with open(cfg_path, encoding="utf-8") as f:
                data = json.load(f)
        data["theme"] = theme.to_dict()
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except:
        pass
