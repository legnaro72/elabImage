import streamlit.web.cli as stcli
import os, sys
import time
import webbrowser
from threading import Timer

def resolve_path(path):
    # Funzione che trova i file sia sul tuo PC che dentro l'EXE
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, path)
    return os.path.join(os.getcwd(), path)

def open_browser():
    # Aspetta 2 secondi e apre il browser
    time.sleep(2)
    webbrowser.open_new("http://localhost:8501")

if __name__ == "__main__":
    # Nome del tuo script principale
    # Assicurati che questo file contenga le ultime modifiche fatte oggi!
    script_name = "viewerstatistiche3.py"
    app_path = resolve_path(script_name)

    # Configurazione comandi Streamlit
    sys.argv = [
        "streamlit",
        "run",
        app_path,
        "--global.developmentMode=false",
        "--server.headless=true",
        "--server.enableXsrfProtection=false",  # <--- FONDAMENTALE PER ERRORE 400
        "--server.enableCORS=false",            # <--- FONDAMENTALE PER ERRORE 400
        "--server.address=localhost",
        "--server.port=8501",
    ]

    print("--- AVVIO DASHBOARD LEONARDO ---")
    print("Attendere l'apertura del browser...")
    
    # Avvia il timer che apre Chrome/Edge
    t = Timer(2, open_browser)
    t.start()
    
    # Avvia il motore Streamlit
    sys.exit(stcli.main())