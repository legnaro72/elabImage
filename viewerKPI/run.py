import streamlit.web.cli as stcli
import os, sys

def resolve_path(path):
    if getattr(sys, '_MEIPASS', False):
        return os.path.join(sys._MEIPASS, path)
    return os.path.join(os.getcwd(), path)

if __name__ == "__main__":
    # Imposta il percorso del tuo script principale
    sys.argv = [
        "streamlit",
        "run",
        resolve_path("Viewer_Pro_v6.py"), # <--- ASSICURATI CHE IL NOME SIA CORRETTO
        "--global.developmentMode=false",
    ]
    sys.exit(stcli.main())