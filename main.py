import sys
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QSharedMemory
from ui.main_window import MainWindow

def main():
    app = QApplication(sys.argv)

    # Create a unique shared memory key for RYTWEAKS
    shared_memory = QSharedMemory("RYTWEAKS_Single_Instance_Key")
    
    # If the key already exists, another instance is running!
    if not shared_memory.create(1):
        # Optional: alert or just exit silently to prevent loops
        sys.exit(0)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()