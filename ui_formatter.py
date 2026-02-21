# ui_formatter.py - Enhanced UI Design for Time Tracker
"""
Modern, Professional UI Formatter for Developer Tracker

Provides multiple design themes and formatting styles to create a professional,
user-friendly interface for the time tracking application.

Features:
    - Multiple design themes (modern, minimal, classic, dark)
    - Professional color scheme support
    - Responsive layout formatting
    - Enhanced typography with emoji icons
    - Card-based design components
    - Dashboard-style reports
"""

from enum import Enum
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


class Theme(Enum):
    """Available UI themes"""
    MODERN = "modern"      # Colorful, gradient-inspired
    MINIMAL = "minimal"    # Clean, minimalist design
    CLASSIC = "classic"    # Traditional boxes and tables
    DARK = "dark"          # Dark mode optimized
    NEON = "neon"          # Bold, vibrant colors


@dataclass
class UIStyle:
    """UI styling configuration"""
    theme: Theme
    width: int = 80
    use_unicode: bool = True
    use_colors: bool = False
    use_emojis: bool = True


class Color:
    """ANSI color codes for terminal output"""
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    
    # Foreground colors
    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'
    
    # Background colors
    BG_BLACK = '\033[40m'
    BG_RED = '\033[41m'
    BG_GREEN = '\033[42m'
    BG_YELLOW = '\033[43m'
    BG_BLUE = '\033[44m'
    BG_MAGENTA = '\033[45m'
    BG_CYAN = '\033[46m'
    BG_WHITE = '\033[47m'


class UIFormatter:
    """Professional UI formatting for time tracker"""
    
    # Theme configurations
    THEMES = {
        Theme.MODERN: {
            "header_char": "═",
            "border_char": "║",
            "corner_char": "╔╗╚╝",
            "divider": "─",
            "color": Color.CYAN,
        },
        Theme.MINIMAL: {
            "header_char": "─",
            "border_char": "|",
            "corner_char": "++++",
            "divider": "─",
            "color": Color.WHITE,
        },
        Theme.CLASSIC: {
            "header_char": "═",
            "border_char": "║",
            "corner_char": "╔╗╚╝",
            "divider": "─",
            "color": Color.BLUE,
        },
        Theme.DARK: {
            "header_char": "─",
            "border_char": "│",
            "corner_char": "┌┐└┘",
            "divider": "─",
            "color": Color.WHITE,
        },
        Theme.NEON: {
            "header_char": "═",
            "border_char": "║",
            "corner_char": "╔╗╚╝",
            "divider": "─",
            "color": Color.MAGENTA,
        },
    }
    
    STATUS_ICONS = {
        "running": "▶️",
        "paused": "⏸️",
        "stopped": "⏹️",
        "completed": "✅",
        "error": "❌",
        "warning": "⚠️",
    }
    
    CATEGORY_ICONS = {
        "applications": "📱",
        "keyboard": "⌨️",
        "mouse": "🖱️",
        "screenshots": "📸",
        "productivity": "📊",
        "time": "⏱️",
        "user": "👤",
        "statistics": "📈",
    }
    
    def __init__(self, theme: Theme = Theme.MODERN, width: int = 80, use_colors: bool = False):
        """Initialize UI formatter with theme"""
        self.theme = theme
        self.width = width
        self.use_colors = use_colors
        self.style = self.THEMES.get(theme, self.THEMES[Theme.MODERN])
    
    def header(self, title: str, icon: str = "📊") -> str:
        """Create a professional header"""
        return self._create_header(title, icon)
    
    def _create_header(self, title: str, icon: str) -> str:
        """Create header with theme styling"""
        if self.theme == Theme.MODERN:
            return self._modern_header(title, icon)
        elif self.theme == Theme.MINIMAL:
            return self._minimal_header(title, icon)
        elif self.theme == Theme.DARK:
            return self._dark_header(title, icon)
        else:
            return self._classic_header(title, icon)
    
    def _modern_header(self, title: str, icon: str) -> str:
        """Modern gradient-inspired header"""
        border = "╔" + "═" * (self.width - 2) + "╗"
        
        # Center the title
        title_text = f"{icon}  {title}"
        padding = (self.width - 2 - len(title_text)) // 2
        centered = " " * padding + title_text + " " * (self.width - 2 - len(title_text) - padding)
        
        footer = "╚" + "═" * (self.width - 2) + "╝"
        
        return f"{border}\n║{centered}║\n{footer}"
    
    def _minimal_header(self, title: str, icon: str) -> str:
        """Minimal clean header"""
        title_text = f"{icon} {title}"
        return f"\n{title_text}\n{'-' * len(title_text)}\n"
    
    def _dark_header(self, title: str, icon: str) -> str:
        """Dark mode optimized header"""
        border = "┌" + "─" * (self.width - 2) + "┐"
        title_text = f"{icon}  {title}"
        padding = (self.width - 2 - len(title_text)) // 2
        centered = " " * padding + title_text
        footer = "└" + "─" * (self.width - 2) + "┘"
        
        return f"{border}\n│{centered:<{self.width - 2}}│\n{footer}"
    
    def _classic_header(self, title: str, icon: str) -> str:
        """Classic ASCII header"""
        border = "╔" + "═" * (self.width - 2) + "╗"
        title_text = f"{icon}  {title}"
        padding = (self.width - 2 - len(title_text)) // 2
        centered = " " * padding + title_text
        footer = "╚" + "═" * (self.width - 2) + "╝"
        
        return f"{border}\n║{centered:<{self.width - 2}}║\n{footer}"
    
    def card(self, title: str, content: str, icon: str = "") -> str:
        """Create a card component"""
        if icon:
            title = f"{icon} {title}"
        
        lines = [f"┌─ {title} {'-' * (self.width - len(title) - 5)}"]
        
        for line in content.split('\n'):
            lines.append(f"│  {line}")
        
        lines.append("└" + "─" * (self.width - 1))
        
        return "\n".join(lines)
    
    def stat_box(self, label: str, value: str, icon: str = "") -> str:
        """Create a statistics box"""
        icon_part = f"{icon} " if icon else ""
        return f"{icon_part}{label:<25} {value:>20}"
    
    def progress_bar(self, current: float, total: float, width: int = 30) -> str:
        """Create a progress bar"""
        if total == 0:
            percentage = 0
        else:
            percentage = (current / total) * 100
        
        filled = int((current / max(total, 1)) * width)
        bar = "█" * filled + "░" * (width - filled)
        
        return f"[{bar}] {percentage:.1f}%"
    
    def table(self, headers: List[str], rows: List[List[str]]) -> str:
        """Create a formatted table"""
        col_widths = [max(len(h), max((len(str(r[i])) for r in rows), default=0)) 
                     for i, h in enumerate(headers)]
        
        lines = []
        
        # Header
        header_row = " │ ".join(f"{h:<{col_widths[i]}}" for i, h in enumerate(headers))
        lines.append(header_row)
        lines.append("─" * len(header_row))
        
        # Rows
        for row in rows:
            row_str = " │ ".join(f"{str(r):<{col_widths[i]}}" 
                                for i, r in enumerate(row))
            lines.append(row_str)
        
        return "\n".join(lines)
    
    def dashboard(self, metrics: Dict[str, str]) -> str:
        """Create a dashboard layout"""
        lines = []
        lines.append("╔" + "═" * (self.width - 2) + "╗")
        
        for label, value in metrics.items():
            icon = self.CATEGORY_ICONS.get(label, "•")
            lines.append(f"║ {icon} {label:<25} {value:>40} ║")
        
        lines.append("╚" + "═" * (self.width - 2) + "╝")
        
        return "\n".join(lines)
    
    @staticmethod
    def format_duration(seconds: float) -> str:
        """Format duration nicely"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        
        if hours > 0:
            return f"{hours:02d}h {minutes:02d}m {secs:02d}s"
        elif minutes > 0:
            return f"{minutes}m {secs:02d}s"
        else:
            return f"{secs}s"
    
    @staticmethod
    def format_percentage(value: float, decimals: int = 1) -> str:
        """Format percentage with color"""
        percentage = min(100, max(0, value))
        
        if percentage >= 80:
            color = Color.GREEN
        elif percentage >= 60:
            color = Color.YELLOW
        elif percentage >= 40:
            color = Color.YELLOW
        else:
            color = Color.RED
        
        return f"{percentage:.{decimals}f}%"
    
    def section_divider(self, title: Optional[str] = None) -> str:
        """Create a section divider"""
        if title:
            return f"\n─── {title} {'-' * (self.width - len(title) - 8)}\n"
        return "\n" + "─" * self.width + "\n"
    
    def status_indicator(self, status: str) -> str:
        """Get status indicator with icon"""
        icon = self.STATUS_ICONS.get(status, "•")
        return f"{icon} {status.upper()}"
    
    @staticmethod
    def color_text(text: str, color: str) -> str:
        """Add color to text (if enabled)"""
        return f"{color}{text}{Color.RESET}"


class DashboardDesign:
    """Dashboard layout design"""
    
    @staticmethod
    def main_dashboard(user_email: str, session_duration: str, 
                      app_count: int, productivity_score: float) -> str:
        """Create main dashboard layout"""
        
        design = f"""
╔════════════════════════════════════════════════════════════════════════════════╗
║                    ⏱️  DEVELOPER TIME TRACKER DASHBOARD                       ║
╚════════════════════════════════════════════════════════════════════════════════╝

┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃  👤 User: {user_email:<65}                         ┃
┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫
┃                                                                                 ┃
┃  ⏱️  Session Duration        {session_duration:>50}  ┃
┃  📱 Applications Used        {str(app_count) + ' apps':>50}  ┃
┃  📊 Productivity Score       {str(round(productivity_score, 1)) + '/100.0':>50}  ┃
┃                                                                                 ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
"""
        return design.strip()
    
    @staticmethod
    def activity_summary(keyboard_events: int, mouse_events: int, 
                        screenshots: int) -> str:
        """Create activity summary design"""
        
        design = f"""
╔════════════════════════════════════════════════════════════════════════════════╗
║                          📊 ACTIVITY SUMMARY                                  ║
╠════════════════════════════════════════════════════════════════════════════════╣
║                                                                                 ║
║  ⌨️  Keyboard Events      {keyboard_events:>55}                 ║
║  🖱️  Mouse Events          {mouse_events:>55}                 ║
║  📸 Screenshots Captured   {screenshots:>55}                 ║
║                                                                                 ║
╚════════════════════════════════════════════════════════════════════════════════╝
"""
        return design.strip()


# Example usage and testing
if __name__ == "__main__":
    formatter = UIFormatter(Theme.MODERN)
    
    print(formatter.header("SESSION REPORT", "📊"))
    print()
    print(formatter.card(
        "Development Metrics",
        "Total Lines Changed: 1,250\nCommits Made: 5\nTests Passing: 48/50",
        "📈"
    ))
    print()
    print(DashboardDesign.main_dashboard(
        "developer@example.com",
        "02:45:30",
        5,
        85.5
    ))
    print()
    print(DashboardDesign.activity_summary(15420, 3847, 15))
