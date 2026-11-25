import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlencode
from urllib.request import urlopen

try:
    import serial
except ImportError:
    serial = None

# Настройки берутся из Environment Variables на Render (токен в коде не хранится).
token = os.environ.get("BOT_TOKEN", "")
owner = os.environ.get("OWNER_ID", "")  # ID личного чата; пусто при первом запуске.
port = os.environ.get("SERIAL_PORT", "COM3")
http_port = int(os.environ.get("PORT", "10000"))  # Render передаёт PORT сам.
board = None


class Ping(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass


def start_http():
    HTTPServer(("0.0.0.0", http_port), Ping).serve_forever()


def telegram(method, **params):
    url = f"https://api.telegram.org/bot{token}/{method}"
    with urlopen(url, urlencode(params).encode(), timeout=30) as response:
        return json.load(response)["result"]


def ask_board(command):
    global board
    try:
        if serial is None:
            raise OSError
        if board is None:
            board = serial.Serial(port, 9600, timeout=2, write_timeout=2)
            time.sleep(2)
        board.reset_input_buffer()
        board.write((command + "\n").encode("ascii"))
        raw = board.read_until(b"\n", size=32)
        if not raw.endswith(b"\n"):
            raise TimeoutError
        answer = raw.decode("ascii").strip()
        if answer not in ("ON", "OFF"):
            return "Неожиданный ответ Arduino."
        return "LED включён." if answer == "ON" else "LED выключен."
    except (OSError, UnicodeError, serial.SerialException if serial else OSError):
        if board is not None:
            board.close()
            board = None
        return "Нет подтверждения от Arduino. Проверьте USB и порт."


commands = {
    "/led_on": "LED ON",
    "/led_off": "LED OFF",
    "/status": "STATUS",
}

if not token:
    raise SystemExit("Не задана переменная окружения BOT_TOKEN.")

threading.Thread(target=start_http, daemon=True).start()
print("Бот запущен.", flush=True)

offset = 0
while True:
    try:
        updates = telegram("getUpdates", offset=offset, timeout=15,
                           allowed_updates='["message"]')
        for update in updates:
            offset = update["update_id"] + 1
            message = update.get("message", {})
            chat = message.get("chat", {})
            if chat.get("type") != "private":
                continue
            chat_id = str(chat["id"])
            if not owner:
                print("ID личного чата:", chat_id, flush=True)
                continue
            if chat_id != owner or time.time() - message.get("date", 0) > 60:
                continue
            command = commands.get(message.get("text", "").strip())
            reply = (ask_board(command) if command else
                     "Команды: /led_on, /led_off, /status")
            telegram("sendMessage", chat_id=chat_id, text=reply)
    except Exception as error:
        print("Ошибка Telegram:", error, flush=True)
        time.sleep(3)
