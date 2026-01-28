# dashboard.py - Simple Tkinter GUI
import tkinter as tk
from tkinter import ttk, messagebox
import json
import pandas as pd
from datetime import datetime

class Dashboard:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Developer Productivity Tracker")
        self.root.geometry("800x600")
        
        self.setup_ui()
        
    def setup_ui(self):
        # Title
        title = tk.Label(self.root, text="📊 Productivity Dashboard", 
                        font=("Arial", 20, "bold"))
        title.pack(pady=20)
        
        # Stats Frame
        stats_frame = tk.Frame(self.root)
        stats_frame.pack(pady=10)
        
        # Stats labels
        self.score_label = tk.Label(stats_frame, text="Score: --/100", 
                                   font=("Arial", 16))
        self.score_label.grid(row=0, column=0, padx=20)
        
        self.grade_label = tk.Label(stats_frame, text="Grade: --", 
                                   font=("Arial", 16))
        self.grade_label.grid(row=0, column=1, padx=20)
        
        self.duration_label = tk.Label(stats_frame, text="Duration: -- min", 
                                      font=("Arial", 16))
        self.duration_label.grid(row=0, column=2, padx=20)
        
        # Buttons Frame
        button_frame = tk.Frame(self.root)
        button_frame.pack(pady=20)
        
        tk.Button(button_frame, text="Start Tracking", 
                 command=self.start_tracking, width=20).grid(row=0, column=0, padx=10)
        tk.Button(button_frame, text="Stop Tracking", 
                 command=self.stop_tracking, width=20).grid(row=0, column=1, padx=10)
        tk.Button(button_frame, text="View Reports", 
                 command=self.view_reports, width=20).grid(row=0, column=2, padx=10)
        
        # Log Text
        self.log_text = tk.Text(self.root, height=15, width=80)
        self.log_text.pack(pady=20)
        
        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = tk.Label(self.root, textvariable=self.status_var, 
                            relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
    def start_tracking(self):
        self.log("Starting tracking session...")
        # Here you would start the actual tracker
        self.status_var.set("Tracking active...")
        
    def stop_tracking(self):
        self.log("Stopping tracking session...")
        self.status_var.set("Tracking stopped")
        
    def view_reports(self):
        self.log("Loading reports...")
        try:
            # Load latest report
            import glob
            reports = glob.glob("tracking_sessions/*.json")
            if reports:
                latest = max(reports, key=os.path.getctime)
                with open(latest, 'r') as f:
                    report = json.load(f)
                    
                # Update UI
                score = report['overall_productivity']['score']
                grade = report['overall_productivity']['grade']
                duration = report['session_info']['duration_minutes']
                
                self.score_label.config(text=f"Score: {score}/100")
                self.grade_label.config(text=f"Grade: {grade}")
                self.duration_label.config(text=f"Duration: {duration} min")
                
                self.log(f"Loaded report: {report['session_info']['session_id']}")
                messagebox.showinfo("Success", f"Loaded report with score: {score}/100")
            else:
                messagebox.showwarning("No Reports", "No tracking reports found.")
                
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load reports: {e}")
            
    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        
    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    import os
    app = Dashboard()
    app.run()