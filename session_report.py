# session_report.py - PROFESSIONAL SESSION REPORT FORMATTER
"""
Session Report Generator for Time-Tracking Application

This module generates comprehensive, user-friendly session reports that summarize:
- Application usage with detailed timing
- Keyboard and mouse activity metrics
- Screenshot capture statistics
- Overall productivity scoring

Features:
- Formatted time display (HH:MM:SS)
- Organized sections with visual hierarchy
- Color-coded console output (optional)
- JSON export capability
- Collapsible section support for UI integration
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import json

try:
    from app_name_converter import AppNameConverter
except ImportError:
    # Fallback if app_name_converter not available
    class AppNameConverter:
        @staticmethod
        def convert(name):
            return name.replace('.exe', '').replace('_', ' ').title()
        
        @staticmethod
        def get_icon_emoji(app_name):
            return "📱"


def seconds_to_hms(seconds: float) -> str:
    """Convert seconds to HH:MM:SS format"""
    try:
        seconds = max(0, float(seconds))
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    except (ValueError, TypeError):
        return "00:00:00"


@dataclass
class AppUsageDetail:
    """Individual application usage record"""
    app_name: str
    usage_seconds: float
    sessions: int = 1  # Number of separate usage sessions
    window_title: Optional[str] = None
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    def get_friendly_name(self) -> str:
        """Get user-friendly application name"""
        return AppNameConverter.convert(self.app_name)
    
    def get_icon(self) -> str:
        """Get emoji icon for application"""
        friendly_name = self.get_friendly_name()
        return AppNameConverter.get_icon_emoji(friendly_name)
    
    def formatted_time(self) -> str:
        """Return usage time as HH:MM:SS"""
        return seconds_to_hms(self.usage_seconds)
    
    def formatted_display(self) -> str:
        """Return formatted display string for reports"""
        time_str = self.formatted_time()
        friendly_name = self.get_friendly_name()
        icon = self.get_icon()
        sessions_str = f"({self.sessions} session{'s' if self.sessions != 1 else ''})"
        return f"{icon} {friendly_name:<45} {time_str}  {sessions_str}"


@dataclass
class ApplicationSummary:
    """Summary of all application usage during session"""
    total_apps: int = 0
    total_app_time_seconds: float = 0.0
    apps: List[AppUsageDetail] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "total_apps": self.total_apps,
            "total_app_time_seconds": self.total_app_time_seconds,
            "total_app_time_formatted": self.formatted_total_time(),
            "apps": [app.to_dict() for app in self.apps]
        }
    
    def formatted_total_time(self) -> str:
        """Return total application time as HH:MM:SS"""
        return seconds_to_hms(self.total_app_time_seconds)
    
    @staticmethod
    def from_app_monitor_summary(app_monitor_data: dict) -> "ApplicationSummary":
        """Create ApplicationSummary from AppMonitor.get_summary() output"""
        summary = ApplicationSummary()
        
        if not app_monitor_data:
            return summary
        
        summary.total_apps = app_monitor_data.get("total_apps", 0)
        
        # Calculate total time from top_apps list
        top_apps = app_monitor_data.get("top_apps", [])
        total_seconds = 0.0
        
        for app_data in top_apps:
            app_name = app_data.get("app", "unknown")
            minutes = float(app_data.get("minutes", 0))
            sessions = int(app_data.get("sessions", 1))
            
            seconds = minutes * 60
            total_seconds += seconds
            
            detail = AppUsageDetail(
                app_name=app_name,
                usage_seconds=seconds,
                sessions=sessions
            )
            summary.apps.append(detail)
        
        summary.total_app_time_seconds = total_seconds
        return summary


@dataclass
class KeyboardActivitySummary:
    """Summary of keyboard activity during session"""
    total_keys: int = 0
    unique_keys: int = 0
    words_per_minute: float = 0.0
    active_time_minutes: float = 0.0
    activity_percentage: float = 0.0
    key_events_recorded: int = 0
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class MouseActivitySummary:
    """Summary of mouse activity during session"""
    total_events: int = 0
    move_events: int = 0
    click_events: int = 0
    scroll_events: int = 0
    distance_pixels: float = 0.0
    activity_percentage: float = 0.0
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ScreenshotDetail:
    """Individual screenshot record"""
    filename: str
    timestamp: Optional[str] = None
    size_kb: float = 0.0
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ScreenshotSummary:
    """Summary of screenshots captured during session"""
    total_captured: int = 0
    total_size_kb: float = 0.0
    last_capture_time: Optional[str] = None
    screenshots: List[ScreenshotDetail] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "total_captured": self.total_captured,
            "total_size_kb": self.total_size_kb,
            "last_capture_time": self.last_capture_time,
            "screenshots": [s.to_dict() for s in self.screenshots]
        }
    
    def add_screenshot(self, filename: str, timestamp: Optional[str] = None, size_kb: float = 0.0):
        """Add a screenshot to the summary"""
        detail = ScreenshotDetail(
            filename=filename,
            timestamp=timestamp,
            size_kb=size_kb
        )
        self.screenshots.append(detail)
    
    def get_filenames(self) -> List[str]:
        """Get list of all screenshot filenames"""
        return [s.filename for s in self.screenshots]
    
    def formatted_files_list(self) -> str:
        """Return formatted list of screenshot files"""
        if not self.screenshots:
            return "No screenshots captured"
        
        lines = [f"Total Screenshots: {self.total_captured}"]
        lines.append("")
        
        for idx, screenshot in enumerate(self.screenshots, 1):
            lines.append(f"  {idx:2d}. {screenshot.filename}")
            if screenshot.size_kb > 0:
                lines.append(f"       📊 Size: {screenshot.size_kb:.1f} KB")
        
        return "\n".join(lines)


@dataclass
class SessionReport:
    """Comprehensive session report combining all activity summaries"""
    session_id: str
    user_email: str
    start_time: str
    end_time: str
    total_duration_seconds: float
    
    # Activity summaries
    applications: ApplicationSummary = field(default_factory=ApplicationSummary)
    keyboard: KeyboardActivitySummary = field(default_factory=KeyboardActivitySummary)
    mouse: MouseActivitySummary = field(default_factory=MouseActivitySummary)
    screenshots: ScreenshotSummary = field(default_factory=ScreenshotSummary)
    
    # Productivity metrics
    productivity_score: float = 0.0
    status: str = "completed"
    
    # Collapsible sections state (for UI)
    expanded_sections: Dict[str, bool] = field(default_factory=lambda: {
        "applications": True,
        "keyboard": True,
        "mouse": True,
        "screenshots": True
    })
    
    def to_dict(self) -> dict:
        """Convert report to JSON-serializable dictionary"""
        return {
            "session_id": self.session_id,
            "user_email": self.user_email,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "total_duration_seconds": self.total_duration_seconds,
            "total_duration_formatted": self.formatted_total_duration(),
            "applications": self.applications.to_dict(),
            "keyboard": self.keyboard.to_dict(),
            "mouse": self.mouse.to_dict(),
            "screenshots": self.screenshots.to_dict(),
            "productivity_score": round(self.productivity_score, 2),
            "status": self.status
        }
    
    def to_json(self) -> str:
        """Return report as JSON string"""
        return json.dumps(self.to_dict(), indent=2)
    
    def formatted_total_duration(self) -> str:
        """Return total session duration as HH:MM:SS"""
        return seconds_to_hms(self.total_duration_seconds)
    
    def generate_text_report(self, include_details: bool = True) -> str:
        """Generate formatted text report for console/file output"""
        lines = []
        
        # Header
        lines.append("╔" + "═" * 78 + "╗")
        lines.append("║" + " " * 20 + "📊 SESSION ACTIVITY REPORT" + " " * 32 + "║")
        lines.append("╚" + "═" * 78 + "╝")
        lines.append("")
        
        # Session metadata
        lines.append("📋 SESSION INFORMATION")
        lines.append("─" * 80)
        lines.append(f"  Session ID:     {self.session_id}")
        lines.append(f"  User:           {self.user_email}")
        lines.append(f"  Start Time:     {self.start_time}")
        lines.append(f"  End Time:       {self.end_time}")
        lines.append(f"  Total Duration: {self.formatted_total_duration()}")
        lines.append(f"  Status:         {self.status.upper()}")
        lines.append("")
        
        # Application Usage Summary
        lines.append("📱 APPLICATION USAGE SUMMARY")
        lines.append("─" * 80)
        lines.append(f"  Total Applications Tracked: {self.applications.total_apps}")
        lines.append(f"  Total App Time:             {self.applications.formatted_total_time()}")
        lines.append("")
        
        if self.applications.apps:
            lines.append("  Detailed Application Usage:")
            lines.append("  " + "─" * 76)
            
            # Sort by usage time (descending)
            sorted_apps = sorted(
                self.applications.apps,
                key=lambda x: x.usage_seconds,
                reverse=True
            )
            
            for idx, app in enumerate(sorted_apps, 1):
                time_str = app.formatted_time()
                sessions_str = f"({app.sessions} session{'s' if app.sessions != 1 else ''})"
                
                # Calculate percentage of total session time
                if self.total_duration_seconds > 0:
                    percentage = (app.usage_seconds / self.total_duration_seconds) * 100
                    percent_str = f"{percentage:.1f}%"
                else:
                    percent_str = "0.0%"
                
                lines.append(
                    f"    {idx:2d}. {app.app_name:<45} "
                    f"{time_str}  [{percent_str:>5s}]  {sessions_str}"
                )
            
            lines.append("")
        
        # Keyboard Activity
        lines.append("⌨️  KEYBOARD ACTIVITY")
        lines.append("─" * 80)
        lines.append(f"  Total Keys Pressed:        {self.keyboard.total_keys:>10d}")
        lines.append(f"  Unique Keys Used:          {self.keyboard.unique_keys:>10d}")
        lines.append(f"  Words Per Minute (WPM):    {self.keyboard.words_per_minute:>10.2f}")
        lines.append(f"  Active Time:               {self._format_minutes(self.keyboard.active_time_minutes):>10s}")
        lines.append(f"  Activity Percentage:       {self.keyboard.activity_percentage:>10.1f}%")
        lines.append(f"  Key Events Recorded:       {self.keyboard.key_events_recorded:>10d}")
        lines.append("")
        
        # Mouse Activity
        lines.append("🖱️  MOUSE ACTIVITY")
        lines.append("─" * 80)
        lines.append(f"  Total Mouse Events:        {self.mouse.total_events:>10d}")
        lines.append(f"    • Move Events:           {self.mouse.move_events:>10d}")
        lines.append(f"    • Click Events:          {self.mouse.click_events:>10d}")
        lines.append(f"    • Scroll Events:         {self.mouse.scroll_events:>10d}")
        lines.append(f"  Distance Traveled:         {self.mouse.distance_pixels:>10.0f} px")
        lines.append(f"  Mouse Activity:            {self.mouse.activity_percentage:>10.1f}%")
        lines.append("")
        
        # Screenshots
        lines.append("📸 SCREENSHOT CAPTURE")
        lines.append("─" * 80)
        lines.append(f"  Total Screenshots:        {self.screenshots.total_captured:>10d}")
        lines.append(f"  Total Storage:            {self.screenshots.total_size_kb:>10.2f} KB")
        if self.screenshots.last_capture_time:
            lines.append(f"  Last Capture:             {self.screenshots.last_capture_time:>10s}")
        lines.append("")
        
        # Screenshot file list
        if self.screenshots.screenshots:
            lines.append("  Screenshot Files Captured:")
            lines.append("  " + "─" * 76)
            
            for idx, screenshot in enumerate(self.screenshots.screenshots, 1):
                file_display = screenshot.filename
                if len(file_display) > 50:
                    file_display = "..." + file_display[-47:]
                
                size_str = f"({screenshot.size_kb:.1f} KB)" if screenshot.size_kb > 0 else ""
                lines.append(f"    {idx:3d}. {file_display:<50} {size_str}")
            
            lines.append("")
        
        # Productivity Score
        lines.append("📊 PRODUCTIVITY METRICS")
        lines.append("─" * 80)
        lines.append(f"  Overall Productivity Score: {self.productivity_score:>9.2f}/100.0")
        
        # Score interpretation
        if self.productivity_score >= 80:
            rating = "Excellent 🌟"
        elif self.productivity_score >= 60:
            rating = "Good ✓"
        elif self.productivity_score >= 40:
            rating = "Fair ≈"
        else:
            rating = "Low !"
        
        lines.append(f"  Rating:                    {rating:>19s}")
        lines.append("")
        
        # Footer
        lines.append("╔" + "═" * 78 + "╗")
        lines.append("║" + " " * 15 + "End of Session Report - " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " " * 18 + "║")
        lines.append("╚" + "═" * 78 + "╝")
        
        return "\n".join(lines)
    
    def generate_compact_report(self) -> str:
        """Generate a compact single-paragraph report"""
        duration = self.formatted_total_duration()
        
        report = f"""
✅ SESSION COMPLETED
   Session: {self.session_id}
   Duration: {duration}
   Apps Used: {self.applications.total_apps}
   Productivity: {self.productivity_score:.1f}/100
        """.strip()
        
        return report
    
    def generate_json_report(self) -> dict:
        """Generate report suitable for database storage"""
        return self.to_dict()
    
    @staticmethod
    def _format_minutes(minutes: float) -> str:
        """Format minutes as M:SS or HH:MM:SS"""
        total_seconds = int(minutes * 60)
        hours = total_seconds // 3600
        mins = (total_seconds % 3600) // 60
        secs = total_seconds % 60
        
        if hours > 0:
            return f"{hours}:{mins:02d}:{secs:02d}"
        else:
            return f"{mins}:{secs:02d}"
    
    def __str__(self) -> str:
        """String representation returns detailed text report"""
        return self.generate_text_report()
    
    def get_section(self, section_name: str) -> Optional[str]:
        """Get a specific report section for collapsible UI display"""
        sections = {
            "applications": self._get_applications_section,
            "keyboard": self._get_keyboard_section,
            "mouse": self._get_mouse_section,
            "screenshots": self._get_screenshots_section,
        }
        
        if section_name in sections:
            return sections[section_name]()
        return None
    
    def _get_applications_section(self) -> str:
        """Get formatted applications section"""
        lines = ["📱 APPLICATION USAGE"]
        lines.append(f"Total: {self.applications.total_apps} apps | "
                     f"Time: {self.applications.formatted_total_time()}")
        lines.append("")
        
        if self.applications.apps:
            sorted_apps = sorted(
                self.applications.apps,
                key=lambda x: x.usage_seconds,
                reverse=True
            )
            
            for app in sorted_apps:
                lines.append(f"  • {app.formatted_display()}")
        
        return "\n".join(lines)
    
    def _get_keyboard_section(self) -> str:
        """Get formatted keyboard section"""
        lines = ["⌨️  KEYBOARD ACTIVITY"]
        lines.append(f"Keys: {self.keyboard.total_keys} | "
                     f"WPM: {self.keyboard.words_per_minute:.1f} | "
                     f"Activity: {self.keyboard.activity_percentage:.0f}%")
        return "\n".join(lines)
    
    def _get_mouse_section(self) -> str:
        """Get formatted mouse section"""
        lines = ["🖱️  MOUSE ACTIVITY"]
        lines.append(f"Events: {self.mouse.total_events} | "
                     f"Distance: {self.mouse.distance_pixels:.0f}px | "
                     f"Activity: {self.mouse.activity_percentage:.0f}%")
        return "\n".join(lines)
    
    def _get_screenshots_section(self) -> str:
        """Get formatted screenshots section"""
        lines = ["📸 SCREENSHOTS"]
        lines.append(f"Captured: {self.screenshots.total_captured} | "
                     f"Size: {self.screenshots.total_size_kb:.1f}KB")
        return "\n".join(lines)


# Utility functions for report generation
def create_session_report(
    session_data: dict,
    app_monitor_data: Optional[dict] = None,
    mouse_stats: Optional[dict] = None,
    keyboard_stats: Optional[dict] = None,
    screenshot_stats: Optional[dict] = None,
    productivity_score: float = 0.0
) -> SessionReport:
    """
    Factory function to create a SessionReport from component data
    
    Args:
        session_data: Dictionary with session_id, user_email, start_time, end_time, total_duration
        app_monitor_data: Output from AppMonitor.get_summary()
        mouse_stats: Output from MouseTracker.get_stats()
        keyboard_stats: Output from KeyboardTracker.get_stats()
        screenshot_stats: Output from ScreenshotCapture.get_stats()
        productivity_score: Overall productivity score (0-100)
    """
    
    # Create report with session data
    report = SessionReport(
        session_id=session_data.get("session_id", "unknown"),
        user_email=session_data.get("user_email", "unknown@example.com"),
        start_time=session_data.get("start_time", datetime.now().isoformat()),
        end_time=session_data.get("end_time", datetime.now().isoformat()),
        total_duration_seconds=session_data.get("total_duration", 0.0),
        productivity_score=productivity_score,
        status=session_data.get("status", "completed")
    )
    
    # Add application summary
    if app_monitor_data:
        report.applications = ApplicationSummary.from_app_monitor_summary(app_monitor_data)
    
    # Add keyboard activity
    if keyboard_stats:
        report.keyboard = KeyboardActivitySummary(
            total_keys=keyboard_stats.get("total_keys_pressed", 0),
            unique_keys=keyboard_stats.get("unique_keys_used", 0),
            words_per_minute=keyboard_stats.get("words_per_minute", 0.0),
            active_time_minutes=keyboard_stats.get("active_time_minutes", 0.0),
            activity_percentage=keyboard_stats.get("keyboard_activity_percentage", 0.0),
            key_events_recorded=keyboard_stats.get("key_events_recorded", 0)
        )
    
    # Add mouse activity
    if mouse_stats:
        report.mouse = MouseActivitySummary(
            total_events=mouse_stats.get("total_events", 0),
            move_events=mouse_stats.get("move_events", 0),
            click_events=mouse_stats.get("click_events", 0),
            scroll_events=mouse_stats.get("scroll_events", 0),
            distance_pixels=mouse_stats.get("distance", 0.0),
            activity_percentage=mouse_stats.get("activity_percentage", 0.0)
        )
    
    # Add screenshot summary
    if screenshot_stats:
        report.screenshots = ScreenshotSummary(
            total_captured=screenshot_stats.get("total_captured", 0),
            total_size_kb=screenshot_stats.get("total_size_kb", 0.0),
            last_capture_time=screenshot_stats.get("last_capture")
        )
    
    return report
