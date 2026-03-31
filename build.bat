@echo off
pyinstaller main.py --onefile --noconsole --clean --hidden-import=xml.parsers.expat