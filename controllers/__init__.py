# app.py
import tkinter as tk
from models.database import TrafficDB
from views.main_window import MainWindow
from controllers.main_controller import MainController
from controllers.violation_controller import ViolationController
from controllers.accident_controller import AccidentController
from controllers.emergency_controller import EmergencyController

def main():
    # Initialize root window
    root = tk.Tk()
    root.title("OptiFlow - Traffic Management System")
    
    # Initialize database
    db = TrafficDB()
    
    # Initialize controllers
    controllers = {
        'violation': ViolationController(db),
        'accident': AccidentController(db),
        'emergency': EmergencyController(db)
    }
    
    # Initialize view
    view = MainWindow(root, controllers)
    
    # Initialize main controller (needs view reference)
    controllers['main'] = MainController(root, view, db)
    
    # Update view with controllers
    view.controllers = controllers
    
    # Make window responsive
    root.grid_rowconfigure(0, weight=1)
    root.grid_columnconfigure(0, weight=1)
    
    # Set window size and position
    root.geometry("1400x800")
    root.minsize(1200, 700)
    
    # Center window on screen
    root.update_idletasks()
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    window_width = root.winfo_width()
    window_height = root.winfo_height()
    x = (screen_width - window_width) // 2
    y = (screen_height - window_height) // 2
    root.geometry(f"+{x}+{y}")
    
    # Run application
    root.mainloop()

if __name__ == "__main__":
    main()