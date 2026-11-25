import json
import socket
import threading
import time
from urllib.parse import urlencode
from urllib.request import urlopen
import serial

token = "9261272174:AAFvh3_FNmOM4GB1mBMxuITHRUmtDFW66IU"
owner = ""  # После первого запуска вставьте ID, например "123456789".
port = "COM4"  # Замените на порт своей Uno из Arduino IDE.
control_port = 47831  # Локальный порт для переключателя запуск/стоп.
board = None
stop = threading.Event()

# Переключатель: если бот уже работает, повторный запуск останавливает его.
lock = socket.socket()
try:
    lock.bind(("127.0.0.1", control_port))
except OSError:
    try:
        with socket.create_connection(("127.0.0.1", control_port), timeout=3) as s:
            s.sendall(b"stop")
        print("Повторный запуск: бот остановлен (завершится в течение ~15 с).")
    except OSError:
        print("Порт", control_port, "занят другой программой. Смените control_port.")
    raise SystemExit
lock.listen(1)
lock.settimeout(1)


def listen_for_stop():
    while not stop.is_set():
        try:
            conn, _ = lock.accept()
        except socket.timeout:
            continue
        except OSError:
            break
        with conn:
            conn.settimeout(2)
            try:
                if conn.recv(16) == b"stop":
                    stop.set()
            except OSError:
                pass


threading.Thread(target=listen_for_stop, daemon=True).start()


def telegram(method, **params):
    url = f"https://api.telegram.org/bot{token}/{method}"
    with urlopen(url, urlencode(params).encode(), timeout=30) as response:
        return json.load(response)["result"]


def ask_board(command):
    global board
    try:
        if board is None:
            board = serial.Serial(port, 9600, timeout=2, write_timeout=2)
            time.sleep(2)  # Uno может перезапуститься при открытии порта.
        board.reset_input_buffer()
        board.write((command + "\n").encode("ascii"))
        raw = board.read_until(b"\n", size=32)
        if not raw.endswith(b"\n"):
            raise TimeoutError
        answer = raw.decode("ascii").strip()
        if answer not in ("ON", "OFF"):
            return "Неожиданный ответ Arduino."
        return "LED включён." if answer == "ON" else "LED выключен."
    except (OSError, UnicodeError, serial.SerialException):
        if board is not None:
            board.close()
            board = None
        return "Нет подтверждения от Arduino. Проверьте USB и порт."


commands = {
    "/led_on": "LED ON",
    "/led_off": "LED OFF",
    "/status": "STATUS",
}

print("Бот запущен и работает постоянно. Запустите bot.py ещё раз, чтобы остановить.",
      flush=True)
offset = 0
try:
    while not stop.is_set():
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
        except Exception:
            print("Ошибка Telegram. Проверьте сеть, токен и второй экземпляр.",
                  flush=True)
            stop.wait(3)
except KeyboardInterrupt:
    pass
finally:
    stop.set()
    lock.close()
    if board is not None:
        board.close()
    print("Бот остановлен.")