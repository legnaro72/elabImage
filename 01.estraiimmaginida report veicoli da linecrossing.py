import os
import requests
from bs4 import BeautifulSoup
from tkinter import Tk, filedialog, simpledialog 
from urllib.parse import urljoin
import base64
import re
from pathlib import Path
from datetime import datetime, timedelta

# Il registro viene inizializzato all'interno di estrai_immagini
# per garantire che sia pulito ad ogni esecuzione della funzione.
last_saved_timestamp = {} 

def parse_timestamp(timestamp_str):
    """
    Tenta di parsare la stringa del timestamp in un oggetto datetime.
    Ora include i formati più comuni, compreso il formato 'YYYY/MM/DD HH:MM:SS' che hai specificato.
    """
    formati_comuni = [
        "%Y/%m/%d %H:%M:%S",  # Es. 2025/11/05 17:41:05
        
        "%Y-%m-%d %H:%M:%S.%f", # Con millisecondi
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
        "%d-%m-%Y %H:%M:%S",
        "%m/%d/%Y %I:%M:%S %p", 
    ]
    
    cleaned_str = timestamp_str.strip()
    
    for fmt in formati_comuni:
        try:
            return datetime.strptime(cleaned_str, fmt)
        except ValueError:
            continue
            
    return None 

def scegli_file_e_cartella_e_colonne():
    root = Tk()
    root.withdraw()
    
    # 1. Selezione del file HTML
    file_path = filedialog.askopenfilename(
        title="Seleziona il file HTML del report",
        filetypes=[("File HTML", "*.html;*.htm")]
    )
    if not file_path: return None, None, None, None, None, None, None

    # 2. Input per il nome della cartella
    cartella_suffix = simpledialog.askstring(
        "Nome Cartella", 
        "Inserisci una stringa da aggiungere al nome della cartella (es. Data_01):"
    )
    if not cartella_suffix: return None, None, None, None, None, None, None
    
    # 3. Colonna Source
    colonna_source_str = simpledialog.askstring(
        "Colonna Source", 
        "NUMERO colonna (da 1) che contiene la SOURCE (es. ID Veicolo):"
    )
    if not colonna_source_str or not colonna_source_str.isdigit() or int(colonna_source_str) <= 0: return None, None, None, None, None, None, None
    colonna_source_index = int(colonna_source_str) - 1

    # 4. Colonna Timestamp
    colonna_timestamp_str = simpledialog.askstring(
        "Colonna Data/Ora (Timestamp)", 
        "NUMERO colonna (da 1) che contiene la DATA e ORA dell'evento:"
    )
    if not colonna_timestamp_str or not colonna_timestamp_str.isdigit() or int(colonna_timestamp_str) <= 0: return None, None, None, None, None, None, None
    colonna_timestamp_index = int(colonna_timestamp_str) - 1
    
    # 5. Colonna Immagine
    colonna_immagine_str = simpledialog.askstring(
        "Colonna Immagine", 
        "NUMERO colonna (da 1) che contiene l'IMMAGINE da estrarre:"
    )
    if not colonna_immagine_str or not colonna_immagine_str.isdigit() or int(colonna_immagine_str) <= 0: return None, None, None, None, None, None, None
    colonna_immagine_index = int(colonna_immagine_str) - 1

    # 6. NUOVO: Input per il Delta in Secondi
    delta_secondi_str = simpledialog.askstring(
        "Filtro Delta Temporale", 
        "Inserisci il DELTA MINIMO in SECONDI (es. 30):"
    )
    if not delta_secondi_str or not delta_secondi_str.isdigit() or int(delta_secondi_str) < 0:
        print("Operazione annullata. Devi fornire un valore di delta valido (>= 0).")
        return None, None, None, None, None, None, None
    delta_secondi = int(delta_secondi_str)

    html_dir = os.path.dirname(file_path)
    nome_cartella = f"V_{cartella_suffix}"
    cartella_path = os.path.join(html_dir, nome_cartella)
        
    # Restituisce anche i delta secondi
    return file_path, cartella_path, nome_cartella, colonna_source_index, colonna_timestamp_index, colonna_immagine_index, delta_secondi

def estrai_immagini(file_html, cartella_path, nome_cartella, colonna_source_index, colonna_timestamp_index, colonna_immagine_index, delta_seconds):
    
    # 🔑 NUOVO: Definisce il delta minimo in base all'input utente
    MIN_DELTA = timedelta(seconds=delta_seconds) 
    
    last_saved_timestamp = {} 
    
    if not os.path.exists(cartella_path):
        os.makedirs(cartella_path)

    html_dir = os.path.dirname(file_html)
    
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
            
            # Controllo colonne
            if (len(celle) <= colonna_source_index or 
                len(celle) <= colonna_immagine_index or 
                len(celle) <= colonna_timestamp_index): 
                continue 
                
            # 1. Recupera i valori
            source_value_originale = celle[colonna_source_index].get_text(strip=True)
            timestamp_str = celle[colonna_timestamp_index].get_text(strip=True)
            colonna_immagine = celle[colonna_immagine_index] 
            
            # Chiave per il registro: Source pulita
            source_key = re.sub(r'[<>:"/\\|?*]', '_', source_value_originale)
            
            # 2. Parsing del Timestamp
            current_datetime = parse_timestamp(timestamp_str)
            
            # --- 3. LOGICA DELTA TEMPORALE CON VALORE ASSOLUTO ---
            salva_immagine = True
            
            if current_datetime:
                if source_key in last_saved_timestamp:
                    last_ts = last_saved_timestamp[source_key]
                    time_delta = current_datetime - last_ts
                    
                    # 🔑 NUOVO: Usa il valore assoluto del delta
                    abs_time_delta = abs(time_delta)
                    
                    # Filtra se la distanza temporale è minore del delta minimo impostato
                    if abs_time_delta < MIN_DELTA:
                        print(f"➖ Filtrata riga {idx_riga} ({source_key}): Delta ({abs_time_delta.total_seconds():.0f}s) < {delta_seconds}s.")
                        salva_immagine = False
                        
            else:
                # Se il parsing fallisce, salva l'immagine ma stampa l'avviso.
                print(f"⚠️ Avviso: Timestamp non valido '{timestamp_str}' in riga {idx_riga}. Salto il controllo delta.")
                salva_immagine = True

            if not salva_immagine:
                continue

            # --- 4. FORMATTAZIONE DEL NOME FILE E TENTATIVO DI SALVATAGGIO ---

            timestamp_nome_file = current_datetime.strftime("%Y%m%d_%H%M%S") if current_datetime else "NoTS"
            
            imgs = colonna_immagine.find_all("img")
            
            saved_something = False

            for idx_img, img in enumerate(imgs, start=1):
                src = img.get("src")
                if not src: continue 

                nome_file_base = f"{source_key}_{timestamp_nome_file}_{idx_img}"
                saved_path = None

                # 4a. GESTIONE BASE64
                if src.startswith("data:"):
                    match = re.match(r"data:(?P<mime>.*?);base64,(?P<data>.*)", src, re.DOTALL)
                    if match:
                        try:
                            data = match.groupdict()
                            mime_type = data['mime']
                            binary_content = base64.b64decode(data['data'])
                            ext = f'.{mime_type.split("/")[-1]}' if '/' in mime_type else '.bin'
                            
                            path_salvataggio = Path(cartella_path) / f"{nome_file_base}{ext}"
                            
                            counter = 1
                            while path_salvataggio.exists():
                                path_salvataggio = Path(cartella_path) / f"{nome_file_base}_{counter}{ext}"
                                counter += 1
                            
                            with open(path_salvataggio, "wb") as out:
                                out.write(binary_content)
                            saved_path = path_salvataggio
                            
                        except Exception as e:
                            print(f"Errore nella decodifica Base64 per l'immagine {idx_img} in riga {idx_riga}: {e}")

                # 4b. GESTIONE URL E PERCORSI LOCALI
                else:
                    img_url = urljoin("file:///" + os.path.abspath(file_html), src) 
                    ext = os.path.splitext(src)[1] or '.jpg'
                    
                    path_salvataggio = Path(cartella_path) / f"{nome_file_base}{ext}"

                    counter = 1
                    while path_salvataggio.exists():
                        path_salvataggio = Path(cartella_path) / f"{nome_file_base}_{counter}{ext}"
                        counter += 1
                    
                    try:
                        if img_url.startswith(("http", "https")):
                            r = requests.get(img_url, timeout=10)
                            r.raise_for_status() 
                            with open(path_salvataggio, "wb") as out:
                                out.write(r.content)
                        elif img_url.startswith("file:///"):
                            local_path = os.path.join(html_dir, src) 
                            if not os.path.exists(local_path):
                                print(f"Avviso: File locale non trovato a {local_path}")
                                continue
                            with open(local_path, "rb") as in_f, open(path_salvataggio, "wb") as out:
                                out.write(in_f.read())
                        else:
                            print(f"Avviso: Schema URL non supportato per {img_url}")
                            continue

                        saved_path = path_salvataggio
                            
                    except Exception as e:
                        print(f"Errore nel salvataggio di {src}: {e}")

                # --- 5. AGGIORNAMENTO DEL REGISTRO ---
                if saved_path:
                    immagini_salvate.append(str(saved_path))
                    saved_something = True
                    
            # Registra il timestamp solo se almeno un'immagine è stata salvata e abbiamo un timestamp valido.
            if saved_something and current_datetime:
                last_saved_timestamp[source_key] = current_datetime


    return immagini_salvate

def main():
    # NUOVO: Riceve anche delta_seconds
    file_html, cartella_path, nome_cartella, colonna_source_index, colonna_timestamp_index, colonna_immagine_index, delta_seconds = scegli_file_e_cartella_e_colonne()
    
    if not file_html:
        print("Operazione interrotta a causa di input mancanti o non validi.")
        return

    print(f"Inizio estrazione immagini e applicazione filtro delta di {delta_seconds} secondi...")
    
    # NUOVO: Passa delta_seconds alla funzione estrai_immagini
    immagini = estrai_immagini(file_html, cartella_path, nome_cartella, colonna_source_index, colonna_timestamp_index, colonna_immagine_index, delta_seconds)
    
    print("-" * 50)
    if immagini:
        print(f"✅ Completato! {len(immagini)} immagine/i salvate nella cartella '{cartella_path}':")
        # Mostra solo i nomi file relativi per chiarezza
        for img in immagini[-5:]:
            print(" -", os.path.basename(img))
        if len(immagini) > 5:
            print(f"   ... e altre {len(immagini) - 5} immagini.")
    else:
        print("Nessuna immagine trovata, errore di elaborazione o tutte filtrate dal delta di tempo.")
    print("-" * 50)


if __name__ == "__main__":
    main()