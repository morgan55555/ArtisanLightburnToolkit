@echo off
pyinstaller main.py --onefile --noconsole --hidden-import=xml.parsers.expat