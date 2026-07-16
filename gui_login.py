"""
Developer Tracker — GUI entry point.

The interface is split into focused modules:
  - theme.py         design system (colour tokens + reusable widgets)
  - ui_login.py      LoginWindow (sign-in)
  - ui_dashboard.py  DashboardWindow (session tracking)

This module stays as the public entry so `from gui_login import main` keeps
working for main.py. LoginWindow / DashboardWindow are re-exported for any
callers that imported them from here previously.
"""
from ui_login import LoginWindow
from ui_dashboard import DashboardWindow  # re-export for backward compatibility

__all__ = ["main", "LoginWindow", "DashboardWindow"]


def main():
    """Launch the sign-in window (which opens the dashboard on success)."""
    LoginWindow().run()


if __name__ == "__main__":
    main()
