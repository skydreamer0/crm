import os
import sys

def check_file():
    path = "logs/screenshots/form_filled.png"
    if os.path.exists(path):
        print(f"File exists: {path}")
    else:
        print(f"File not found: {path}")

if __name__ == "__main__":
    check_file()
