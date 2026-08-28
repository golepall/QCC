import os
import sys


def is_frozen_app() -> bool:
    return bool(getattr(sys, "frozen", False))


def get_resource_root(reference_file: str = "") -> str:
    if is_frozen_app():
        return os.path.abspath(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)))
    if reference_file:
        return os.path.abspath(os.path.join(os.path.dirname(reference_file), ".."))
    return os.path.abspath(os.getcwd())


def get_launcher_path(reference_file: str = "") -> str:
    if is_frozen_app():
        return os.path.abspath(sys.executable)
    if reference_file:
        return os.path.abspath(reference_file)
    return os.path.abspath(sys.argv[0])


def get_gui_launcher_path(reference_file: str = "") -> str:
    if is_frozen_app():
        return get_launcher_path(reference_file)
    current = os.path.abspath(sys.executable)
    if current.lower().endswith("python.exe"):
        pythonw = current[:-10] + "pythonw.exe"
        if os.path.exists(pythonw):
            return pythonw
    return current
