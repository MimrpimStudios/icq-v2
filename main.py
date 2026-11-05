import requests
import json
import os
import threading
import time
from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout

API_URL = "https://icq-v2-api.onrender.com"
CONTACTS_FILE = "contacts.json"

def load_contacts():
    if os.path.exists(CONTACTS_FILE):
        try:
            with open(CONTACTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_contacts(contacts):
    with open(CONTACTS_FILE, "w", encoding="utf-8") as f:
        json.dump(contacts, f, ensure_ascii=False, indent=4)

def background_worker(my_username):
    """Vlákno na pozadí stahuje nové zprávy pro danou přezdívku."""
    checked_message_ids = set()
    while True:
        try:
            response = requests.get(f"{API_URL}/check_messages/{my_username}")
            if response.status_code == 200:
                data = response.json()
                messages = data.get("messages", [])
                for msg in messages:
                    msg_id = msg.get("id")
                    if msg_id and msg_id not in checked_message_ids:
                        checked_message_ids.add(msg_id)
                        sender = msg.get("from", "Neznámý")
                        text = msg.get("text", "")
                        print(f"\n[{sender}]: {text}")
        except Exception:
            pass
        time.sleep(3)

def main():
    contacts = load_contacts()
    
    print("=== ICQ Klient ===")
    my_username = input("Zadejte svoji přezdívku: ").strip()
    if not my_username:
        print("Přezdívka nemůže být prázdná!")
        return

    # Spuštění vlákna pro příchozí zprávy
    t = threading.Thread(target=background_worker, args=(my_username,), daemon=True)
    t.start()

    session = PromptSession()

    with patch_stdout():
        while True:
            print("\n--- Hlavní nabídka ---")
            print("1. Vybrat kontakt a chatovat")
            print("2. Přidat nový kontakt")
            print("3. Konec")
            
            choice = session.prompt("Zvolte možnost (1-3): ").strip()
            
            if choice == "3" or choice.lower() == "konec":
                break
                
            elif choice == "2":
                name = session.prompt("Zadejte jméno/přezdívku kontaktu: ").strip()
                if name:
                    contacts[name] = name
                    save_contacts(contacts)
                    print(f"Kontakt {name} byl úspěšně uložen!")
                    
            elif choice == "1" or not choice:
                if not contacts:
                    print("Zatím nemáte žádné uložené kontakty.")
                    recipient = session.prompt("Zadejte přezdívku příjemce (nebo Enter pro návrat): ").strip()
                    if not recipient:
                        continue
                else:
                    print("\nUložené kontakty:")
                    contact_names = list(contacts.keys())
                    for idx, name in enumerate(contact_names, 1):
                        print(f"{idx}. {name}")
                    print(f"{len(contact_names) + 1}. Zadat přezdívku ručně")
                    
                    sel = session.prompt("Vyberte číslo kontaktu: ").strip()
                    if not sel:
                        continue
                    try:
                        sel_idx = int(sel)
                        if sel_idx == len(contact_names) + 1:
                            recipient = session.prompt("Zadejte přezdívku příjemce: ").strip()
                        elif 1 <= sel_idx <= len(contact_names):
                            recipient = contact_names[sel_idx - 1]
                        else:
                            print("Neplatná volba.")
                            continue
                    except ValueError:
                        print("Neplatný vstup.")
                        continue

                if not recipient:
                    continue

                # Otevření chatovacího okna
                print(f"\n--- Chat otevřen s: {recipient} ---")
                print("Napište zprávu a odešlete Enterem. Napište 'exit' pro návrat do menu.\n")
                
                while True:
                    text = session.prompt(f"[{recipient}] > ").strip()
                    if text.lower() == "exit":
                        break
                    if not text:
                        continue
                        
                    # Odeslání zprávy včetně odesílatele (from_user)
                    try:
                        payload = {
                            "from_user": my_username,
                            "to_user": recipient,
                            "text": text
                        }
                        res = requests.post(f"{API_URL}/send_message/", json=payload)
                        if res.status_code == 200:
                            print(" (odesláno)")
                        else:
                            print(f" (Chyba při odesílání: {res.status_code} - {res.text})")
                    except Exception as e:
                        print(f" (Chyba připojení: {e})")

if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nUkončuji aplikaci.")