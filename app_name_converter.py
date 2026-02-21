# app_name_converter.py - Convert executable names to user-friendly names
"""
Application Name Converter

Converts Windows executable filenames into user-friendly display names.
Includes comprehensive mappings for common applications and intelligent
fallback mechanisms for unknown executables.

Examples:
    vscode.exe → Visual Studio Code
    photos.exe → Photos
    wordpad.exe → WordPad
    chrome.exe → Google Chrome
"""

from typing import Dict, Optional


class AppNameConverter:
    """Convert executable names to user-friendly application names"""
    
    # Comprehensive mapping of executable names to friendly names
    EXECUTABLE_MAPPING: Dict[str, str] = {
        # ━━━━━━ DEVELOPMENT TOOLS ━━━━━━
        "vscode.exe": "Visual Studio Code",
        "code.exe": "Visual Studio Code",
        "devenv.exe": "Visual Studio",
        "visualstudio.exe": "Visual Studio",
        "pythonw.exe": "Python",
        "python.exe": "Python",
        "node.exe": "Node.js",
        "npm.cmd": "npm",
        "git.exe": "Git",
        "github.exe": "GitHub Desktop",
        "docker.exe": "Docker",
        "slack.exe": "Slack",
        "teams.exe": "Microsoft Teams",
        "discord.exe": "Discord",
        "zoom.exe": "Zoom",
        "atom.exe": "Atom",
        "sublime.exe": "Sublime Text",
        "notepad.exe": "Notepad",
        "notepad++.exe": "Notepad++",
        "gedit.exe": "Text Editor",
        
        # ━━━━━━ WEB BROWSERS ━━━━━━
        "chrome.exe": "Google Chrome",
        "firefox.exe": "Mozilla Firefox",
        "iexplore.exe": "Internet Explorer",
        "msedge.exe": "Microsoft Edge",
        "opera.exe": "Opera",
        "safari.exe": "Safari",
        "brave.exe": "Brave Browser",
        "vivaldi.exe": "Vivaldi",
        
        # ━━━━━━ OFFICE & PRODUCTIVITY ━━━━━━
        "winword.exe": "Microsoft Word",
        "excel.exe": "Microsoft Excel",
        "powerpnt.exe": "Microsoft PowerPoint",
        "outlook.exe": "Microsoft Outlook",
        "onenote.exe": "Microsoft OneNote",
        "access.exe": "Microsoft Access",
        "publisher.exe": "Microsoft Publisher",
        "visio.exe": "Microsoft Visio",
        "soffice.exe": "LibreOffice",
        "writer.exe": "LibreOffice Writer",
        "calc.exe": "LibreOffice Calc",
        "impress.exe": "LibreOffice Impress",
        "wordpad.exe": "WordPad",
        "write.exe": "Write",
        
        # ━━━━━━ MEDIA & CREATIVE ━━━━━━
        "photoshop.exe": "Adobe Photoshop",
        "illustrator.exe": "Adobe Illustrator",
        "premiere.exe": "Adobe Premiere Pro",
        "audition.exe": "Adobe Audition",
        "aftereffects.exe": "Adobe After Effects",
        "indesign.exe": "Adobe InDesign",
        "xd.exe": "Adobe XD",
        "lightroom.exe": "Adobe Lightroom",
        "acrobat.exe": "Adobe Acrobat",
        "acrobatinfo.exe": "Adobe Acrobat",
        "vlc.exe": "VLC Media Player",
        "foobar2000.exe": "foobar2000",
        "spotify.exe": "Spotify",
        "itunes.exe": "iTunes",
        "mediaplayer.exe": "Windows Media Player",
        "wmplayer.exe": "Windows Media Player",
        "gimp.exe": "GIMP",
        "krita.exe": "Krita",
        "blender.exe": "Blender",
        "cinema4d.exe": "Cinema 4D",
        "maya.exe": "Autodesk Maya",
        "3dsmax.exe": "Autodesk 3ds Max",
        
        # ━━━━━━ SYSTEM & UTILITIES ━━━━━━
        "explorer.exe": "Windows Explorer",
        "cmd.exe": "Command Prompt",
        "powershell.exe": "PowerShell",
        "terminal.exe": "Windows Terminal",
        "putty.exe": "PuTTY",
        "7zfm.exe": "7-Zip",
        "winrar.exe": "WinRAR",
        "totcmd.exe": "Total Commander",
        "everything.exe": "Everything",
        "clover.exe": "Clover",
        "wintree.exe": "WinTree",
        
        # ━━━━━━ WINDOWS APPS ━━━━━━
        "photos.exe": "Photos",
        "windowsphoto.exe": "Photos",
        "calculator.exe": "Calculator",
        "calc.exe": "Calculator",
        "mspaint.exe": "Paint",
        "paint.exe": "Paint 3D",
        "snipping-tool.exe": "Snipping Tool",
        "snippingtool.exe": "Snipping Tool",
        "screensketch.exe": "Snip & Sketch",
        "clipchamp.exe": "Clipchamp",
        "mail.exe": "Mail",
        "windowsmail.exe": "Mail",
        "calendar.exe": "Calendar",
        "maps.exe": "Maps",
        "weather.exe": "Weather",
        "store.exe": "Microsoft Store",
        "wsreset.exe": "Microsoft Store",
        "settings.exe": "Settings",
        "systemsettings.exe": "Settings",
        "controlpanel.exe": "Control Panel",
        "taskmgr.exe": "Task Manager",
        "devmgr.exe": "Device Manager",
        "perfmon.exe": "Performance Monitor",
        "eventvwr.exe": "Event Viewer",
        "services.msc": "Services",
        
        # ━━━━━━ COMMUNICATION ━━━━━━
        "skype.exe": "Skype",
        "telegram.exe": "Telegram",
        "whatsapp.exe": "WhatsApp",
        "signal.exe": "Signal",
        "wire.exe": "Wire",
        "discord.exe": "Discord",
        "twitch.exe": "Twitch",
        "zoom.exe": "Zoom",
        "webex.exe": "Cisco Webex",
        "googledrive.exe": "Google Drive",
        "dropbox.exe": "Dropbox",
        "onedrive.exe": "OneDrive",
        "nextcloud.exe": "Nextcloud",
        
        # ━━━━━━ DEVELOPMENT UTILITIES ━━━━━━
        "sourcetree.exe": "Sourcetree",
        "tortoisegit.exe": "TortoiseGit",
        "gitkraken.exe": "GitKraken",
        "bitbucket.exe": "Bitbucket",
        "jira.exe": "Jira",
        "confluence.exe": "Confluence",
        "slack.exe": "Slack",
        "tower.exe": "Tower",
        "intellijidea.exe": "IntelliJ IDEA",
        "rider.exe": "JetBrains Rider",
        "pycharm.exe": "PyCharm",
        "clion.exe": "CLion",
        "android-studio.exe": "Android Studio",
        "xcode.exe": "Xcode",
        
        # ━━━━━━ CONTENT CREATION ━━━━━━
        "obs.exe": "OBS Studio",
        "obs64.exe": "OBS Studio",
        "handbrake.exe": "HandBrake",
        "shotcut.exe": "Shotcut",
        "kdenlive.exe": "Kdenlive",
        "ffmpeg.exe": "FFmpeg",
        "audacity.exe": "Audacity",
        
        # ━━━━━━ SYSTEM PROCESSES ━━━━━━
        "dwm.exe": "Desktop Window Manager",
        "svchost.exe": "Service Host",
        "rundll32.exe": "Windows System",
        "lsass.exe": "Local Security Authority",
        "csrss.exe": "Client/Server Runtime System",
        "wininit.exe": "Windows Initialization",
        "system.exe": "System Process",
        "spoolsv.exe": "Print Spooler",
    }
    
    @staticmethod
    def convert(exe_name: str) -> str:
        """
        Convert executable name to user-friendly name
        
        Args:
            exe_name: Executable filename (e.g., 'vscode.exe')
            
        Returns:
            User-friendly application name
            
        Examples:
            >>> AppNameConverter.convert('vscode.exe')
            'Visual Studio Code'
            >>> AppNameConverter.convert('photos.exe')
            'Photos'
            >>> AppNameConverter.convert('unknown_app.exe')
            'Unknown App'
        """
        if not exe_name:
            return "Unknown"
        
        # Normalize to lowercase for comparison
        normalized = exe_name.lower().strip()
        
        # Check exact match first
        if normalized in AppNameConverter.EXECUTABLE_MAPPING:
            return AppNameConverter.EXECUTABLE_MAPPING[normalized]
        
        # Fallback: clean up the executable name
        return AppNameConverter._cleanup_name(exe_name)
    
    @staticmethod
    def _cleanup_name(exe_name: str) -> str:
        """
        Clean up executable name to make it more user-friendly
        
        Args:
            exe_name: Raw executable name
            
        Returns:
            Cleaned up name
            
        Examples:
            >>> AppNameConverter._cleanup_name('myapp.exe')
            'MyApp'
            >>> AppNameConverter._cleanup_name('my_application.exe')
            'My Application'
        """
        # Remove .exe extension
        name = exe_name.replace('.exe', '').replace('.cmd', '').replace('.bat', '')
        
        # Handle underscores and hyphens
        name = name.replace('_', ' ').replace('-', ' ')
        
        # Capitalize each word
        words = name.split()
        capitalized_words = []
        
        for word in words:
            if word:
                # Capitalize first letter, keep rest as is
                capitalized_words.append(word[0].upper() + word[1:])
        
        return ' '.join(capitalized_words) if capitalized_words else "Unknown"
    
    @staticmethod
    def is_system_process(exe_name: str) -> bool:
        """
        Check if executable is a system process
        
        Args:
            exe_name: Executable filename
            
        Returns:
            True if it's a known system process
        """
        system_processes = {
            'dwm.exe', 'svchost.exe', 'rundll32.exe', 'lsass.exe',
            'csrss.exe', 'wininit.exe', 'system.exe', 'spoolsv.exe',
            'explorer.exe', 'cmd.exe', 'powershell.exe'
        }
        return exe_name.lower() in system_processes
    
    @staticmethod
    def batch_convert(exe_names: list) -> dict:
        """
        Convert multiple executable names
        
        Args:
            exe_names: List of executable names
            
        Returns:
            Dictionary mapping exe_name -> friendly_name
        """
        return {name: AppNameConverter.convert(name) for name in exe_names}
    
    @staticmethod
    def get_icon_emoji(app_name: str) -> str:
        """
        Get emoji icon for application name
        
        Args:
            app_name: User-friendly application name
            
        Returns:
            Appropriate emoji icon
        """
        icon_mapping = {
            # Development
            "Visual Studio Code": "🔵",
            "Python": "🐍",
            "Git": "🧠",
            "Docker": "🐳",
            "Node.js": "📦",
            
            # Browsers
            "Google Chrome": "🌐",
            "Mozilla Firefox": "🦊",
            "Microsoft Edge": "🔷",
            
            # Office
            "Microsoft Word": "📝",
            "Microsoft Excel": "📊",
            "Microsoft PowerPoint": "🎯",
            "Microsoft Outlook": "📧",
            
            # Media
            "Adobe Photoshop": "🎨",
            "VLC Media Player": "🎬",
            "Spotify": "🎵",
            
            # Communication
            "Slack": "💬",
            "Discord": "🎮",
            "Zoom": "📹",
            "Teams": "👥",
            
            # System
            "Windows Explorer": "📁",
            "Command Prompt": "⌨️",
            "Settings": "⚙️",
            "Pictures": "🖼️",
            "Photos": "📷",
            "Calculator": "🔢",
        }
        
        return icon_mapping.get(app_name, "📱")


# Quick reference dictionary for common conversions
QUICK_CONVERTER = {
    'vscode.exe': 'Visual Studio Code',
    'photos.exe': 'Photos',
    'wordpad.exe': 'WordPad',
    'chrome.exe': 'Google Chrome',
    'firefox.exe': 'Mozilla Firefox',
    'winword.exe': 'Microsoft Word',
    'excel.exe': 'Microsoft Excel',
    'explorer.exe': 'Windows Explorer',
    'slack.exe': 'Slack',
    'spotify.exe': 'Spotify',
    'discord.exe': 'Discord',
}


def convert_app_name(exe_name: str) -> str:
    """
    Quick conversion function
    
    Args:
        exe_name: Executable filename
        
    Returns:
        User-friendly name
    """
    return AppNameConverter.convert(exe_name)


# Example usage
if __name__ == "__main__":
    # Test the converter
    test_cases = [
        'vscode.exe',
        'photos.exe',
        'wordpad.exe',
        'chrome.exe',
        'unknown_app.exe',
        'my_app_name.exe'
    ]
    
    print("Application Name Converter - Test Results\n")
    print("=" * 60)
    
    for exe in test_cases:
        friendly = AppNameConverter.convert(exe)
        emoji = AppNameConverter.get_icon_emoji(friendly)
        print(f"{exe:<25} → {emoji} {friendly}")
    
    print("=" * 60)
