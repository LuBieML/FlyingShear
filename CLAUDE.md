# FlyingShear - Claude Instructions

## Project Overview
This project is a Flet-based desktop application for simulating or controlling a **Flying Shear** industrial cutting system. It integrates with the `Trio_UnifiedApi` for control communications and kinematics calculations.

## Commands
- Run application: `venv\Scripts\python.exe main.py` or `python main.py`
- Setup / build: `build.bat` or `build.ps1`
- Install dependencies: `venv\Scripts\pip.exe install -r requirements.txt`

## Code Search & Symbol Navigation
- Symbol queries (e.g., find definitions, find references, call hierarchy, find usages of a function, class, or variable) **MUST** use LSP-based navigation tools (e.g., `goToDefinition`, `findReferences`). Do **NOT** run text-based `grep` or `rg` for these queries.
- Only use `grep` or `rg` for pure text-based searches, such as looking for log messages, comments, configuration keys, or specific error strings.
- If LSP tools are not working or the language server is not available for a specific file, you may fall back to `grep` after documenting the reason.
