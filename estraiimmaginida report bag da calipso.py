import os
import requests
from bs4 import BeautifulSoup
from tkinter import Tk, filedialog
from urllib.parse import urljoin
import base64 # Importiamo la libreria per la decodifica Base64
import re     # Importiamo re per l'analisi del formato data:

def scegli_file_html():
    root = Tk()
    root.withdraw()  # nasconde la finestra principale
    file_path = filedialog.askopenfilename(
        title="Seleziona il file HTML",
        filetypes=[("File HTML", "*.html;*.htm")]
    )
    return file_path

def estrai_immagini(file_html):
    # crea cartella bag se non esiste
    if not os.path.exists("bag"):
        os.makedirs("bag")

    # Ottiene la directory del file HTML per risolvere i percorsi relativi locali
    html_dir = os.path.dirname(file_html)
    
    # legge il contenuto dell'html
    try:
        with open(file_html, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f, "html.parser")
    except Exception as e:
        print(f"Errore durante la lettura del file HTML: {e}")
        return []

    immagini_salvate = []
    tabelle = soup.find_all("table")

    for idx_tabella, tabella in enumerate(tabelle, start=1):
        righe = tabella.find_all("tr")
        for idx_riga, riga in enumerate(righe, start=1):
            celle = riga.find_all(["td", "th"])
            if len(celle) >= 11:  # controlla se c'è l'11° colonna
                colonna11 = celle[10]  # indice 10 = 11° colonna
                imgs = colonna11.find_all("img")
                for idx_img, img in enumerate(imgs, start=1):
                    src = img.get("src")
                    
                    if not src:
                        continue # Salta se src è vuoto

                    # --- 1. GESTIONE BASE64 (Dati incorporati) ---
                    if src.startswith("data:"):
                        match = re.match(r"data:(?P<mime>.*?);base64,(?P<data>.*)", src, re.DOTALL)
                        if match:
                            data = match.groupdict()
                            mime_type = data['mime']
                            base64_data = data['data']
                            
                            try:
                                # Decodifica il dato Base64
                                binary_content = base64.b64decode(base64_data)
                                
                                # Estrae l'estensione (es. 'image/png' -> '.png')
                                ext = os.path.splitext(mime_type)[1] if '/' in mime_type else '.bin'
                                ext = f'.{mime_type.split("/")[-1]}' if '/' in mime_type else '.bin'

                                nome_file = f"tab{idx_tabella}_row{idx_riga}_img{idx_img}{ext}" 
                                path_salvataggio = os.path.join("bag", nome_file)
                                
                                with open(path_salvataggio, "wb") as out:
                                    out.write(binary_content)
                                    
                                immagini_salvate.append(path_salvataggio)
                                continue # Passa alla prossima immagine
                                
                            except base64.binascii.Error:
                                print(f"Avviso: Base64 non valido per l'immagine {idx_img} in riga {idx_riga}")
                                continue
                            except Exception as e:
                                print(f"Errore nella decodifica Base64 per l'immagine {idx_img}: {e}")
                                continue
                        else:
                            print(f"Avviso: Formato 'data:' non riconosciuto per l'immagine {idx_img}")
                            continue # Passa alla prossima immagine

                    # --- 2. GESTIONE URL E PERCORSI LOCALI (Logica precedente) ---
                    # Risolve l'URL relativo alla directory del file HTML
                    img_url = urljoin("file:///" + os.path.abspath(file_html), src) 
                    
                    # Usa l'estensione del file originale o .jpg come fallback
                    ext = os.path.splitext(src)[1] or '.jpg'
                    nome_file = f"tab{idx_tabella}_row{idx_riga}_img{idx_img}{ext}" 
                    path_salvataggio = os.path.join("bag", nome_file)
                    
                    try:
                        if img_url.startswith(("http", "https")):
                            # Scarica da internet
                            r = requests.get(img_url, timeout=10)
                            r.raise_for_status() # Lancia un errore per 4xx/5xx
                            with open(path_salvataggio, "wb") as out:
                                out.write(r.content)
                                
                        elif img_url.startswith("file:///"):
                            # Copia da file locale
                            local_path = os.path.join(html_dir, src) # Usa la directory di base + src originale
                            
                            if not os.path.exists(local_path):
                                print(f"Avviso: File locale non trovato a {local_path}")
                                continue
                            
                            with open(local_path, "rb") as in_f:
                                content = in_f.read()
                            with open(path_salvataggio, "wb") as out:
                                out.write(content)
                                
                        else:
                            # Gestisce altri schemi URL non previsti
                            print(f"Avviso: Schema URL non supportato per {img_url}")
                            continue

                        immagini_salvate.append(path_salvataggio)
                        
                    except requests.exceptions.RequestException as req_e:
                        print(f"Errore di rete/download con {img_url}: {req_e}")
                    except Exception as e:
                        print(f"Errore con {img_url} o salvataggio del file: {e}")

    return immagini_salvate

def main():
    file_html = scegli_file_html()
    if not file_html:
        print("Nessun file selezionato.")
        return

    immagini = estrai_immagini(file_html)
    if immagini:
        print("Immagini salvate nella cartella 'bag':")
        for img in immagini:
            print(" -", img)
    else:
        print("Nessuna immagine trovata nell'11ª colonna o errore di elaborazione.")

if __name__ == "__main__":
    main()

