import json
import os
import subprocess
import sys
import threading
import time
from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
import requests

API_URL = "https://icq-v2-api.onrender.com"
CONTACTS_FILE = "contacts.json"
LOGIN_FILE = "login.json"

# Sdílený stav aplikace pro aktivního příjemce
app_state = {"active_recipient": None}


def is_frozen():
  """Vrátí True, pokud aplikace běží zkompilovaná jako .exe (PyInstaller)."""
  return getattr(sys, "frozen", False)


def load_contacts():
  if os.path.exists(CONTACTS_FILE):
    try:
      with open(CONTACTS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)
    except Exception:
      return {}
  return {}


def save_contacts(contacts):
  with open(CONTACTS_FILE, "w", encoding="utf-8") as f:
    json.dump(contacts, f, ensure_ascii=False, indent=4)


def background_worker(my_username):
  """Vlákno na pozadí stahuje zprávy a při nové zprávě pípne a vypíše notifikaci."""
  checked_message_ids = set()
  first_run = True

  while True:
    try:
      response = requests.get(f"{API_URL}/check_messages/{my_username}")
      if response.status_code == 200:
        data = response.json()
        messages = data.get("messages", [])

        for msg in messages:
          msg_id = msg.get("id")
          if msg_id:
            if first_run:
              checked_message_ids.add(msg_id)
            elif msg_id not in checked_message_ids:
              checked_message_ids.add(msg_id)
              sender = msg.get("from", "Neznámý")
              text = msg.get("text", "")

              if app_state["active_recipient"] == sender:
                # Zvukové pípnutí + výpis do otevřeného chatu
                print(f"\a[{sender} -> {my_username}]: {text}")
              else:
                # Zvukové pípnutí + notifikace v hlavním menu
                print(f"\n\aNová zpráva od {sender}!")

        first_run = False
    except Exception:
      pass
    time.sleep(2)


def open_chat_window(my_username, recipient):
  """Spustí novou instanci aplikace pro daný chat v novém okně (podporuje .py i .exe)."""
  if is_frozen():
    # Pokud běží jako zkompilované .exe
    exe_path = sys.executable
    if sys.platform.startswith("win"):
      # Prázdné uvozovky "" zabrání tomu, aby CMD bral cestu k exe jako titulky okna
      cmd = f'start "" "{exe_path}" --chat "{recipient}"'
      os.system(cmd)
    else:
      subprocess.Popen([exe_path, "--chat", recipient])
  else:
    # Pokud běží jako klasický .py skript
    script_path = os.path.abspath(__file__)
    python_exe = sys.executable

    if sys.platform.startswith("win"):
      cmd = f'start "" "{python_exe}" "{script_path}" --chat "{recipient}"'
      os.system(cmd)
    else:
      terminals = ["gnome-terminal", "xfce4-terminal", "konsole", "xterm"]
      opened = False
      for term in terminals:
        if (
            subprocess.call(
                ["which", term],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            == 0
        ):
          if term == "gnome-terminal":
            subprocess.Popen(
                [term, "--", python_exe, script_path, "--chat", recipient]
            )
          elif term == "xfce4-terminal":
            subprocess.Popen([
                term,
                "-e",
                f'"{python_exe}" "{script_path}" --chat "{recipient}"',
            ])
          else:
            subprocess.Popen(
                [term, "-e", python_exe, script_path, "--chat", recipient]
            )
          opened = True
          break

      if not opened:
        print(
            "Nenalezen žádný podporovaný emulátor terminálu. Chat bude otevřen"
            " v tomto okně."
        )
        run_chat_loop(my_username, recipient)


def run_chat_loop(my_username, recipient):
  """Smyčka samotného chatu s načtením historie."""
  app_state["active_recipient"] = recipient

  # Načtení celé historie před vstupem do chatu
  print(f"Načítám historii chatu s uživatelem {recipient}...")
  try:
    res = requests.get(f"{API_URL}/history/{my_username}/{recipient}")
    if res.status_code == 200:
      history_data = res.json()
      history_messages = history_data.get("messages", [])
      print(f"\n--- Historie chatu s: {recipient} ---")
      for msg in history_messages:
        sender = msg.get("from")
        receiver = msg.get("to")
        text = msg.get("text")
        print(f"[{sender} -> {receiver}]: {text}")
    else:
      print("(Nepodařilo se načíst historii)")
  except Exception as e:
    print(f"(Chyba při načítání historie: {e})")

  print(f"\n--- Chat otevřen s: {recipient} ---")
  print("Napište zprávu a odešlete Enterem. Napište 'exit' pro návrat.\n")

  session = PromptSession()
  with patch_stdout():
    while True:
      text = session.prompt(f"[{my_username} -> {recipient}] > ").strip()
      if text.lower() == "exit":
        break
      if not text:
        continue

      try:
        payload = {
            "from_user": my_username,
            "to_user": recipient,
            "text": text,
        }
        res = requests.post(f"{API_URL}/send_message/", json=payload)
        if res.status_code != 200:
          print(f" (Chyba při odesílání: {res.status_code} - {res.text})")
      except Exception as e:
        print(f" (Chyba připojení: {e})")

  app_state["active_recipient"] = None


def main():
  contacts = load_contacts()

  my_username = ""
  if os.path.exists(LOGIN_FILE):
    try:
      with open(LOGIN_FILE, "r", encoding="utf-8") as f:
        login_data = json.load(f)
        my_username = login_data.get("username", "").strip()
    except Exception:
      pass

  if not my_username:
    print("=== ICQ Klient ===")
    my_username = input("Zadejte svoji přezdívku: ").strip()
    if my_username:
      try:
        with open(LOGIN_FILE, "w", encoding="utf-8") as f:
          json.dump({"username": my_username}, f, ensure_ascii=False, indent=4)
      except Exception:
        pass

  if not my_username:
    print("Přezdívka nemůže být prázdná!")
    return

  # Pokud byl skript spuštěn jako nové okno pro konkrétní chat (přes parametr --chat)
  if len(sys.argv) >= 3 and sys.argv[1] == "--chat":
    recipient = sys.argv[2]
    # Spustíme hlídací vlákno i pro toto okno
    t = threading.Thread(
        target=background_worker, args=(my_username,), daemon=True
    )
    t.start()
    run_chat_loop(my_username, recipient)
    return

  print(f"=== ICQ Klient (Uživatel: {my_username}) ===")

  # Spuštění hlídacího vlákna na pozadí pro hlavní menu
  t = threading.Thread(
      target=background_worker, args=(my_username,), daemon=True
  )
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
          recipient = session.prompt(
              "Zadejte přezdívku příjemce (nebo Enter pro návrat): "
          ).strip()
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

        # Otevře chat v novém okně
        open_chat_window(my_username, recipient)


if __name__ == "__main__":
  try:
    main()
  except (KeyboardInterrupt, EOFError):
    print("\nUkončuji aplikaci.")