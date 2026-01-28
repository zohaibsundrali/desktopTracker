# screenshot_viewer.py - Simple screenshot viewer
import os
import json
from PIL import Image, ImageTk
import tkinter as tk
from tkinter import ttk, filedialog
from datetime import datetime
import glob

class ScreenshotViewer:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Screenshot Viewer - Productivity Tracker")
        self.root.geometry("1000x700")
        
        self.current_image = None
        self.current_index = 0
        self.screenshots = []
        self.metadata = {}
        
        self.setup_ui()
        
    def setup_ui(self):
        # Title
        title = tk.Label(self.root, text="📸 Screenshot Viewer", 
                        font=("Arial", 20, "bold"))
        title.pack(pady=10)
        
        # Control Frame
        control_frame = tk.Frame(self.root)
        control_frame.pack(pady=10)
        
        tk.Button(control_frame, text="Load Folder", 
                 command=self.load_folder, width=15).pack(side=tk.LEFT, padx=5)
        tk.Button(control_frame, text="Previous", 
                 command=self.previous_image, width=15).pack(side=tk.LEFT, padx=5)
        tk.Button(control_frame, text="Next", 
                 command=self.next_image, width=15).pack(side=tk.LEFT, padx=5)
        tk.Button(control_frame, text="Refresh", 
                 command=self.refresh_list, width=15).pack(side=tk.LEFT, padx=5)
        
        # Main content frame
        content_frame = tk.Frame(self.root)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # Left panel - Screenshot list
        left_frame = tk.Frame(content_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        
        tk.Label(left_frame, text="Screenshots", 
                font=("Arial", 12, "bold")).pack()
        
        self.listbox = tk.Listbox(left_frame, width=30, height=20)
        self.listbox.pack(fill=tk.Y, expand=True)
        self.listbox.bind('<<ListboxSelect>>', self.on_list_select)
        
        # Right panel - Image display
        right_frame = tk.Frame(content_frame)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        # Image display
        self.image_label = tk.Label(right_frame, text="No image loaded", 
                                  bg="gray", relief=tk.SUNKEN)
        self.image_label.pack(fill=tk.BOTH, expand=True)
        
        # Info panel
        info_frame = tk.Frame(right_frame)
        info_frame.pack(fill=tk.X, pady=10)
        
        self.info_text = tk.Text(info_frame, height=6, width=60)
        self.info_text.pack(fill=tk.X)
        
        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = tk.Label(self.root, textvariable=self.status_var, 
                            relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
    def load_folder(self):
        folder = filedialog.askdirectory(title="Select Screenshots Folder")
        if folder:
            self.load_screenshots(folder)
            
    def load_screenshots(self, folder_path):
        self.screenshots = []
        
        # Look for image files
        image_extensions = ['*.jpg', '*.jpeg', '*.png', '*.bmp', '*.gif']
        for ext in image_extensions:
            self.screenshots.extend(glob.glob(os.path.join(folder_path, ext)))
        
        # Sort by modification time (newest first)
        self.screenshots.sort(key=os.path.getmtime, reverse=True)
        
        # Update listbox
        self.listbox.delete(0, tk.END)
        for screenshot in self.screenshots:
            filename = os.path.basename(screenshot)
            mod_time = datetime.fromtimestamp(os.path.getmtime(screenshot))
            display_text = f"{mod_time.strftime('%H:%M:%S')} - {filename[:20]}..."
            self.listbox.insert(tk.END, display_text)
        
        # Try to load metadata
        metadata_file = os.path.join(folder_path, "screenshots_metadata.json")
        if os.path.exists(metadata_file):
            with open(metadata_file, 'r') as f:
                self.metadata = json.load(f)
        
        self.status_var.set(f"Loaded {len(self.screenshots)} screenshots from {folder_path}")
        
        # Select first image if available
        if self.screenshots:
            self.listbox.selection_set(0)
            self.display_image(0)
            
    def display_image(self, index):
        if 0 <= index < len(self.screenshots):
            try:
                image_path = self.screenshots[index]
                
                # Load and resize image
                img = Image.open(image_path)
                
                # Resize to fit display (max 600x400)
                display_width, display_height = 600, 400
                img_width, img_height = img.size
                
                if img_width > display_width or img_height > display_height:
                    ratio = min(display_width/img_width, display_height/img_height)
                    new_size = (int(img_width * ratio), int(img_height * ratio))
                    img = img.resize(new_size, Image.Resampling.LANCZOS)
                
                # Convert to PhotoImage
                self.current_image = ImageTk.PhotoImage(img)
                self.image_label.config(image=self.current_image, text="")
                
                # Update info
                self.update_info(image_path, index)
                
                self.current_index = index
                self.listbox.selection_clear(0, tk.END)
                self.listbox.selection_set(index)
                self.listbox.see(index)
                
            except Exception as e:
                self.image_label.config(image="", text=f"Error loading image: {e}")
                
    def update_info(self, image_path, index):
        filename = os.path.basename(image_path)
        file_size = os.path.getsize(image_path) / 1024  # KB
        mod_time = datetime.fromtimestamp(os.path.getmtime(image_path))
        
        info = f"📄 File: {filename}\n"
        info += f"📅 Date: {mod_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        info += f"💾 Size: {file_size:.1f} KB\n"
        info += f"📊 Position: {index + 1} of {len(self.screenshots)}\n"
        
        # Try to get additional info from metadata
        for screenshot_info in self.metadata.get('screenshots', []):
            if screenshot_info.get('filename') == filename:
                info += f"🖥️  App: {screenshot_info.get('app_active', 'Unknown')}\n"
                info += f"📏 Resolution: {screenshot_info.get('width', '?')}x{screenshot_info.get('height', '?')}\n"
                break
        
        self.info_text.delete(1.0, tk.END)
        self.info_text.insert(1.0, info)
        
    def on_list_select(self, event):
        selection = self.listbox.curselection()
        if selection:
            self.display_image(selection[0])
            
    def previous_image(self):
        if self.screenshots:
            new_index = (self.current_index - 1) % len(self.screenshots)
            self.display_image(new_index)
            
    def next_image(self):
        if self.screenshots:
            new_index = (self.current_index + 1) % len(self.screenshots)
            self.display_image(new_index)
            
    def refresh_list(self):
        if self.screenshots:
            current_folder = os.path.dirname(self.screenshots[0])
            self.load_screenshots(current_folder)
            
    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    viewer = ScreenshotViewer()
    
    # Auto-load screenshots from default folder if exists
    default_folders = ["screenshots", "enhanced_demo/screenshots", "test_screenshots"]
    for folder in default_folders:
        if os.path.exists(folder) and os.path.isdir(folder):
            viewer.load_screenshots(folder)
            break
    
    viewer.run()