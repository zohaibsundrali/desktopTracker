"""
site_detector.py - detect which website a browser is showing.

Two-stage detection (title first, URL fallback):
  1. site_from_title(title)  - fast, no dependencies. Matches known services
     (ChatGPT, Claude, Gemini, ...) by keywords in the browser tab title.
  2. site_from_url_label()   - reads the browser's address bar via Windows UI
     Automation (optional `uiautomation` dependency) and maps the domain to a
     friendly label. Slower and Windows-only; used only when the title is
     inconclusive.

Everything is best-effort and defensive: any failure returns None so tracking
never breaks.
"""
from typing import Optional
from urllib.parse import urlparse

# Browser process names (lowercased, as returned by psutil Process.name()).
_BROWSERS = {
    "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe",
    "opera_gx.exe", "vivaldi.exe", "iexplore.exe", "arc.exe", "chromium.exe",
    "browser.exe",
}

# Keyword (in lowercased tab title) -> canonical site label. First match wins,
# so order more specific keywords before generic ones.
_TITLE_KEYWORDS = [
    ("chatgpt", "ChatGPT"), ("openai", "ChatGPT"),
    ("claude", "Claude"),
    ("gemini", "Gemini"), (" bard", "Gemini"),
    ("copilot", "Microsoft Copilot"),
    ("perplexity", "Perplexity"),
    ("deepseek", "DeepSeek"),
    ("grok", "Grok"),
    ("youtube", "YouTube"),
    ("stack overflow", "Stack Overflow"), ("stackoverflow", "Stack Overflow"),
    ("github", "GitHub"),
    ("gitlab", "GitLab"),
    ("google docs", "Google Docs"), ("google sheets", "Google Sheets"),
    ("google slides", "Google Slides"),
    ("gmail", "Gmail"),
    ("figma", "Figma"),
    ("notion", "Notion"),
    ("slack", "Slack"),
    ("linkedin", "LinkedIn"),
    ("reddit", "Reddit"),
    ("facebook", "Facebook"),
    ("instagram", "Instagram"),
    ("whatsapp", "WhatsApp"),
    ("jira", "Jira"),
    ("trello", "Trello"),
    ("vercel", "Vercel"),
    ("supabase", "Supabase"),
    ("netflix", "Netflix"),
    (" / x", "X (Twitter)"), ("twitter", "X (Twitter)"),
]

# Domain -> friendly label, for the URL-based fallback.
_DOMAIN_MAP = {
    "chat.openai.com": "ChatGPT", "chatgpt.com": "ChatGPT",
    "claude.ai": "Claude",
    "gemini.google.com": "Gemini", "bard.google.com": "Gemini",
    "copilot.microsoft.com": "Microsoft Copilot",
    "perplexity.ai": "Perplexity",
    "chat.deepseek.com": "DeepSeek",
    "grok.com": "Grok", "x.ai": "Grok",
    "youtube.com": "YouTube",
    "stackoverflow.com": "Stack Overflow",
    "github.com": "GitHub", "gitlab.com": "GitLab",
    "docs.google.com": "Google Docs",
    "mail.google.com": "Gmail",
    "figma.com": "Figma", "notion.so": "Notion",
    "linkedin.com": "LinkedIn", "reddit.com": "Reddit",
    "facebook.com": "Facebook", "instagram.com": "Instagram",
    "x.com": "X (Twitter)", "twitter.com": "X (Twitter)",
    "vercel.com": "Vercel", "supabase.com": "Supabase",
    "netflix.com": "Netflix",
}


def is_browser(app_name_raw: Optional[str]) -> bool:
    return (app_name_raw or "").strip().lower() in _BROWSERS


def site_from_title(title: Optional[str]) -> Optional[str]:
    """Return a known site label if the tab title matches one, else None."""
    if not title:
        return None
    t = title.lower()
    for keyword, label in _TITLE_KEYWORDS:
        if keyword in t:
            return label
    return None


def _domain(url: str) -> str:
    try:
        u = url if "://" in url else "http://" + url
        host = (urlparse(u).netloc or "").lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def label_from_domain(domain: str) -> Optional[str]:
    """Map a domain to a friendly label, else return the domain itself."""
    if not domain:
        return None
    if domain in _DOMAIN_MAP:
        return _DOMAIN_MAP[domain]
    # Try the registrable-ish part (last two labels) for subdomains.
    parts = domain.split(".")
    if len(parts) >= 2:
        base = ".".join(parts[-2:])
        if base in _DOMAIN_MAP:
            return _DOMAIN_MAP[base]
    return domain


def read_active_url() -> Optional[str]:
    """Best-effort read of the foreground browser's address bar (Windows only).

    Requires the optional `uiautomation` package. Returns None on any failure,
    off-Windows, or if the package is missing.
    """
    try:
        import uiautomation as auto
    except Exception:
        return None
    try:
        win = auto.GetForegroundControl()
        if not win:
            return None
        edit = win.EditControl(searchDepth=16)
        if edit and edit.Exists(0, 0):
            value = edit.GetValuePattern().Value
            return value or None
    except Exception:
        return None
    return None


def site_from_url_label() -> Optional[str]:
    """Read the active URL and return a friendly site label (or None)."""
    url = read_active_url()
    if not url:
        return None
    return label_from_domain(_domain(url))
