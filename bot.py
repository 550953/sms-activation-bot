#!/usr/bin/env python3
"""
Minimal personal Telegram bot for SMS Gateway.
- Only allowed Telegram user IDs can use it
- Multiple concurrent orders (each waits up to 8 min)
- Menu "Мои коды" shows only numbers that already received SMS
- No database, everything in memory
- Safe for public GitHub (secrets only via env)
"""

import json
import logging
import os
import ssl
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, List, Optional, Tuple

import telebot
from telebot import types
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Config from environment
# ---------------------------------------------------------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
SMS_API_KEY = os.getenv("SMS_API_KEY", "").strip()
BASE_URL = os.getenv("SMS_BASE_URL", "https://89.124.118.5").rstrip("/")
ALLOWED_RAW = os.getenv("ALLOWED_USER_IDS", "").strip()
ALLOWED_IDS = {int(x.strip()) for x in ALLOWED_RAW.split(",") if x.strip().isdigit()}

POST_TIMEOUT = 90
MAX_WAIT = 480  # 8 minutes
PAGE_SIZE = 8

if not BOT_TOKEN or not SMS_API_KEY:
    raise SystemExit("BOT_TOKEN and SMS_API_KEY must be set")

if not ALLOWED_IDS:
    logging.warning("ALLOWED_USER_IDS is empty — bot will reject everyone")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("sms-bot")

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
ROUTES: List[Tuple[str, str, str, str, str]] = [
    ("Russia", "MTS", "drp", "0", ""),
    ("Russia", "Megafon", "oth", "0", ""),
    ("Russia", "Yota", "mt", "0", ""),
    ("Kyrgyzstan", "Nurtelecom", "oth", "11", "Wildberries, Telegram, Apple"),
    ("Kyrgyzstan", "Skymobile", "sdek", "11", ""),
    ("Tajikistan", "Tcell", "oth", "143", ""),
    ("Kazakhstan", "Tele2", "oth", "2", "Letoile запрет, любой RU-сервис не более 20 в час"),
    ("Uzbekistan", "UMS", "oth", "40", "Amazon, Telegram"),
    ("Ukraine", "3Mob + Intertelecom", "oth", "1", "Amazon, Telegram"),
    ("Pakistan", "Telenor", "oth", "66", "Amazon, Telegram"),
    ("Pakistan", "Ufone", "am", "66", "Amazon, Telegram"),
    ("Pakistan", "Jazz", "aor", "66", "Amazon, Telegram"),
    ("Honduras", "Tigo", "oth", "88", "Amazon, Telegram"),
    ("Bangladesh", "Grameenphone", "fb", "60", "Amazon, Telegram"),
    ("Bangladesh", "Banglalink", "am", "60", "Amazon, Telegram"),
    ("Bangladesh", "Robi", "oth", "60", "Amazon, Telegram"),
    ("Tanzania", "Halotel", "oth", "9", "Amazon, Telegram"),
    ("Mexico", "Telefonica + AT&T + Altan", "oth", "54", "Amazon, Telegram"),
    ("Philippines", "Globe", "oth", "4", "Amazon, Telegram"),
    ("Mauritania", "Moov", "oth", "114", "Amazon, Telegram"),
    ("Bulgaria", "A1", "oth", "83", "Amazon, Telegram"),
    ("Serbia", "A1", "oth", "29", "Amazon, Telegram"),
    ("Israel", "Telzar", "oth", "13", "Amazon, Telegram"),
    ("Venezuela", "Telefonica", "who", "70", "Amazon, Telegram"),
    ("Azerbaijan", "Azerphone + Bakcell + Azercell", "who", "35", "Amazon, Telegram"),
    ("Ethiopia", "Safaricom", "who", "71", "Amazon, Telegram"),
    ("Indonesia", "XL + Indosat + Telkomsel + Hutchison", "who", "6", "Amazon, Telegram"),
    ("Belarus", "A1 + BeST + MTS", "who", "51", "Amazon, Telegram"),
    ("Ukraine", "Vodafone + Kyivstar + Lifecell", "who", "1", "Amazon, Telegram"),
    ("Pakistan", "SCO + ZONG", "who", "66", "Amazon, Telegram"),
    ("Kenya", "Safaricom", "who", "8", "Amazon, Telegram"),
    ("Armenia", "Vivacell + Orange", "who", "148", "Amazon, Telegram"),
    ("Georgia", "Magticom + Silknet + VEON", "who", "128", "Amazon, Telegram"),
    ("Niger", "Telecel", "who", "139", "Amazon, Telegram"),
    ("Uzbekistan", "Ucell + Uzmobile + Humans", "who", "40", "Amazon, Telegram"),
    ("Philippines", "Dito + Smart", "who", "4", "Amazon, Telegram"),
    ("Kazakhstan", "Kcell + Altel + Tele2", "who", "2", "Amazon, Telegram"),
    ("Nigeria", "Airtel", "who", "19", "Amazon, Telegram"),
    ("Egypt", "Vodafone", "who", "21", "Amazon, Telegram"),
    ("Slovenia", "Telemach", "who", "59", "Amazon, Telegram"),
    ("United Arab Emirates", "Etisalat", "who", "95", "Amazon, Telegram"),
    ("Malaysia", "Maxis", "who", "7", "Amazon, Telegram"),
    ("Ghana", "MTN", "who", "38", "Amazon, Telegram"),
    ("Bulgaria", "Vivacom + Telenor", "who", "83", "Amazon, Telegram"),
    ("Ghana", "Scancom + Vodafone", "who", "38", "Amazon, Telegram"),
    ("Morocco", "MarocTelecom", "who", "37", "Amazon, Telegram"),
    ("Kyrgyzstan", "Beeline", "who", "11", "Amazon, Telegram"),
    ("Sudan", "Sudantel", "who", "98", "Amazon, Telegram"),
    ("Tajikistan", "Indigo North + Indigo South (Tcell)", "who", "143", "Amazon, Telegram"),
    ("Burundi", "Orascom", "who", "118", "Amazon, Telegram"),
    ("Cameroon", "Camtel", "who", "41", "Amazon, Telegram"),
    ("Laos", "BestTelecom", "who", "25", "Amazon, Telegram"),
    ("Myanmar", "P&T + Mytel", "who", "5", "Amazon, Telegram"),
    ("Bermuda", "Telecommunications", "who", "190", "Amazon, Telegram"),
    ("Lebanon", "Alfa", "who", "153", "Amazon, Telegram"),
    ("Tanzania", "MIC", "who", "9", "Amazon, Telegram"),
]
ROUTES.sort(key=lambda r: (r[0].lower(), r[2], r[1].lower()))

ISO = {
    "Armenia": ("AM", "+374"), "Azerbaijan": ("AZ", "+994"), "Bangladesh": ("BD", "+880"),
    "Belarus": ("BY", "+375"), "Bermuda": ("BM", "+1"), "Bulgaria": ("BG", "+359"),
    "Burundi": ("BI", "+257"), "Cameroon": ("CM", "+237"), "Egypt": ("EG", "+20"),
    "Ethiopia": ("ET", "+251"), "Georgia": ("GE", "+995"), "Ghana": ("GH", "+233"),
    "Honduras": ("HN", "+504"), "Indonesia": ("ID", "+62"), "Israel": ("IL", "+972"),
    "Kazakhstan": ("KZ", "+7"), "Kenya": ("KE", "+254"), "Kyrgyzstan": ("KG", "+996"),
    "Laos": ("LA", "+856"), "Lebanon": ("LB", "+961"), "Malaysia": ("MY", "+60"),
    "Mauritania": ("MR", "+222"), "Mexico": ("MX", "+52"), "Morocco": ("MA", "+212"),
    "Myanmar": ("MM", "+95"), "Niger": ("NE", "+227"), "Nigeria": ("NG", "+234"),
    "Pakistan": ("PK", "+92"), "Philippines": ("PH", "+63"), "Russia": ("RU", "+7"),
    "Serbia": ("RS", "+381"), "Slovenia": ("SI", "+386"), "Sudan": ("SD", "+249"),
    "Tajikistan": ("TJ", "+992"), "Tanzania": ("TZ", "+255"), "Ukraine": ("UA", "+380"),
    "United Arab Emirates": ("AE", "+971"), "Uzbekistan": ("UZ", "+998"),
    "Venezuela": ("VE", "+58"),
}

COUNTRIES = sorted({r[0] for r in ROUTES})

# ---------------------------------------------------------------------------
# SSL
# ---------------------------------------------------------------------------
def _ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

SSL_CTX = _ssl_ctx()

# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
def api(method: str, path: str, body: Optional[dict] = None, timeout: int = 30):
    import urllib.request
    import urllib.error

    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(BASE_URL + path, data=data, method=method)
    req.add_header("Authorization", f"Bearer {SMS_API_KEY}")
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"raw": raw}


def error_text(status: int, data: dict) -> str:
    err = data.get("error") if isinstance(data, dict) else None
    if isinstance(err, dict):
        return f"{err.get('code')} — {err.get('message')}"
    return f"HTTP {status}: {data}"


# ---------------------------------------------------------------------------
# In-memory state
# order fields:
#   act_id, phone, country, ops, svc, started, chat_id, msg_id,
#   stop, code (None until received), finished
# ---------------------------------------------------------------------------
ACTIVE: Dict[int, List[dict]] = {}
ACTIVE_LOCK = threading.Lock()

# ---------------------------------------------------------------------------
# Bot
# ---------------------------------------------------------------------------
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")


def is_allowed(user_id: int) -> bool:
    return user_id in ALLOWED_IDS


def deny(message_or_call):
    try:
        if hasattr(message_or_call, "message"):
            bot.answer_callback_query(message_or_call.id, "Access denied", show_alert=True)
        else:
            bot.reply_to(message_or_call, "⛔ Access denied")
    except Exception:
        pass


# ---------- Keyboards ----------

def main_kb() -> types.ReplyKeyboardMarkup:
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("🌍 Номер", "📬 Мои коды")
    kb.add("📋 Ожидают", "ℹ️ Помощь")
    return kb


def countries_kb(page: int = 0) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    start = page * PAGE_SIZE
    chunk = COUNTRIES[start:start + PAGE_SIZE]

    buttons = []
    for c in chunk:
        iso = ISO.get(c, ("", ""))[0]
        flag = f"{iso} " if iso else ""
        buttons.append(types.InlineKeyboardButton(
            f"{flag}{c}", callback_data=f"c:{c}"
        ))
    kb.add(*buttons)

    nav = []
    if page > 0:
        nav.append(types.InlineKeyboardButton("⬅️", callback_data=f"p:{page-1}"))
    if start + PAGE_SIZE < len(COUNTRIES):
        nav.append(types.InlineKeyboardButton("➡️", callback_data=f"p:{page+1}"))
    if nav:
        kb.row(*nav)

    return kb


def operators_kb(country: str) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=1)
    ops = [r for r in ROUTES if r[0] == country]
    for idx, (_, name, svc, code, _) in enumerate(ops):
        kb.add(types.InlineKeyboardButton(
            f"{name}  ({svc})",
            callback_data=f"o:{country}:{idx}"
        ))
    kb.add(types.InlineKeyboardButton("« Назад", callback_data="p:0"))
    return kb


def order_kb(act_id: str) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("🔄 Проверить", callback_data=f"check:{act_id}"),
        types.InlineKeyboardButton("❌ Стоп", callback_data=f"stop:{act_id}"),
    )
    return kb


# ---------- Helpers for lists ----------

def get_orders(user_id: int) -> List[dict]:
    with ACTIVE_LOCK:
        return list(ACTIVE.get(user_id, []))


def received_orders(user_id: int) -> List[dict]:
    return [o for o in get_orders(user_id) if o.get("code")]


def waiting_orders(user_id: int) -> List[dict]:
    return [o for o in get_orders(user_id) if not o.get("finished") and not o.get("code")]


def format_received(orders: List[dict]) -> str:
    if not orders:
        return "Пока нет полученных кодов."
    lines = ["📬 <b>Полученные коды</b>\n"]
    for i, o in enumerate(reversed(orders[-20:]), 1):
        iso = ISO.get(o["country"], ("", ""))[0]
        lines.append(
            f"<b>{i}.</b> {iso} <code>+{o['phone']}</code>\n"
            f"Код: <code>{o['code']}</code>\n"
            f"{o['country']} · {o['ops']} · {o['svc']}\n"
            f"<code>{o['act_id']}</code>\n"
        )
    return "\n".join(lines)


def format_waiting(orders: List[dict]) -> str:
    if not orders:
        return "Сейчас ничего не ожидается."
    lines = ["📋 <b>Ожидают SMS</b>\n"]
    now = time.time()
    for i, o in enumerate(orders, 1):
        left = max(0, int(MAX_WAIT - (now - o["started"])))
        iso = ISO.get(o["country"], ("", ""))[0]
        lines.append(
            f"<b>{i}.</b> {iso} <code>+{o['phone']}</code>\n"
            f"{o['country']} · {o['ops']} · {o['svc']}\n"
            f"осталось ~{left // 60}м {left % 60}с\n"
            f"<code>{o['act_id']}</code>\n"
        )
    return "\n".join(lines)


# ---------- Handlers ----------

@bot.message_handler(commands=["start", "menu"])
def cmd_start(message: types.Message):
    if not is_allowed(message.from_user.id):
        return deny(message)
    bot.send_message(
        message.chat.id,
        "Личный SMS-бот.\nВыбери действие:",
        reply_markup=main_kb(),
    )


@bot.message_handler(commands=["help"])
def cmd_help(message: types.Message):
    if not is_allowed(message.from_user.id):
        return deny(message)
    bot.reply_to(
        message,
        "🌍 <b>Номер</b> — выбрать страну и заказать\n"
        "📬 <b>Мои коды</b> — только те, куда SMS уже пришла\n"
        "📋 <b>Ожидают</b> — текущая очередь (до 8 мин каждый)\n\n"
        "Можно заказывать несколько номеров параллельно.",
        reply_markup=main_kb(),
    )


@bot.message_handler(func=lambda m: m.text == "🌍 Номер")
def btn_number(message: types.Message):
    if not is_allowed(message.from_user.id):
        return deny(message)
    bot.send_message(
        message.chat.id,
        "Выбери страну:",
        reply_markup=countries_kb(0),
    )


@bot.message_handler(func=lambda m: m.text == "📬 Мои коды")
def btn_codes(message: types.Message):
    if not is_allowed(message.from_user.id):
        return deny(message)
    orders = received_orders(message.from_user.id)
    bot.send_message(message.chat.id, format_received(orders), reply_markup=main_kb())


@bot.message_handler(func=lambda m: m.text == "📋 Ожидают")
def btn_waiting(message: types.Message):
    if not is_allowed(message.from_user.id):
        return deny(message)
    orders = waiting_orders(message.from_user.id)
    bot.send_message(message.chat.id, format_waiting(orders), reply_markup=main_kb())


@bot.message_handler(func=lambda m: m.text == "ℹ️ Помощь")
def btn_help(message: types.Message):
    cmd_help(message)


@bot.callback_query_handler(func=lambda c: True)
def on_callback(call: types.CallbackQuery):
    if not is_allowed(call.from_user.id):
        return deny(call)

    data = call.data or ""
    bot.answer_callback_query(call.id)

    if data.startswith("p:"):
        page = int(data.split(":")[1])
        bot.edit_message_text(
            "Выбери страну:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=countries_kb(page),
        )
        return

    if data.startswith("c:"):
        country = data[2:]
        ops = [r for r in ROUTES if r[0] == country]
        if len(ops) == 1:
            order_number(call, ops[0])
        else:
            bot.edit_message_text(
                f"<b>{country}</b>\nВыбери оператора:",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=operators_kb(country),
            )
        return

    if data.startswith("o:"):
        parts = data.split(":")
        country = parts[1]
        idx = int(parts[2])
        ops = [r for r in ROUTES if r[0] == country]
        if 0 <= idx < len(ops):
            order_number(call, ops[idx])
        return

    if data.startswith("check:"):
        act_id = data[6:]
        check_sms(call, act_id)
        return

    if data.startswith("stop:"):
        act_id = data[5:]
        stop_order(call.from_user.id, act_id)
        try:
            bot.edit_message_reply_markup(
                call.message.chat.id,
                call.message.message_id,
                reply_markup=None,
            )
        except Exception:
            pass
        bot.send_message(call.message.chat.id, f"Ожидание остановлено.\nID: <code>{act_id}</code>")
        return


def order_number(call: types.CallbackQuery, route: Tuple[str, str, str, str, str]):
    country, ops, svc, code, ban = route
    chat_id = call.message.chat.id
    user_id = call.from_user.id

    bot.edit_message_text(
        f"⏳ Запрашиваю номер…\n{country} / {ops}\n<code>{svc}</code> · country={code}",
        chat_id,
        call.message.message_id,
    )

    try:
        status, data = api(
            "POST",
            "/v1/activations",
            body={"service": svc, "country": str(code)},
            timeout=POST_TIMEOUT,
        )
    except Exception as e:
        bot.edit_message_text(
            f"❌ Сетевая ошибка: {e}\n"
            "Номер мог быть выдан. Не повторяй запрос автоматически.",
            chat_id,
            call.message.message_id,
        )
        log.error("ORDER network error: %s", e)
        return

    if status != 200:
        bot.edit_message_text(
            f"❌ {error_text(status, data)}",
            chat_id,
            call.message.message_id,
        )
        log.warning("ORDER fail: %s", error_text(status, data))
        return

    act_id = data.get("activation_id", "")
    phone = data.get("phone_number", "")

    text = (
        f"<b>{country}</b> / {ops}\n"
        f"<code>{svc}</code> · country={code}\n"
        f"ID: <code>{act_id}</code>\n\n"
        f"<code>+{phone}</code>\n"
        f"<code>{phone}</code>\n\n"
        f"⏳ Ожидаю SMS (до 8 мин)…"
    )

    msg = bot.edit_message_text(
        text,
        chat_id,
        call.message.message_id,
        reply_markup=order_kb(act_id),
    )

    order = {
        "act_id": act_id,
        "phone": phone,
        "country": country,
        "ops": ops,
        "svc": svc,
        "started": time.time(),
        "chat_id": chat_id,
        "msg_id": getattr(msg, "message_id", call.message.message_id),
        "stop": False,
        "code": None,
        "finished": False,
    }

    with ACTIVE_LOCK:
        ACTIVE.setdefault(user_id, []).append(order)

    threading.Thread(target=wait_sms, args=(user_id, order), daemon=True).start()
    log.info("ORDER ok user=%s phone=+%s id=%s", user_id, phone, act_id)


def check_sms(call: types.CallbackQuery, act_id: str):
    try:
        status, data = api("GET", f"/v1/activations/{act_id}")
    except Exception as e:
        bot.answer_callback_query(call.id, f"Ошибка сети: {e}", show_alert=True)
        return

    if status != 200:
        bot.answer_callback_query(call.id, error_text(status, data), show_alert=True)
        return

    st = data.get("status")
    code = data.get("sms_code")

    if st == "sms_received" and code:
        mark_received(call.from_user.id, act_id, code)
        bot.send_message(
            call.message.chat.id,
            f"✅ <b>КОД:</b> <code>{code}</code>\n"
            f"Номер: <code>+{data.get('phone_number', '')}</code>\n"
            f"ID: <code>{act_id}</code>",
        )
    else:
        bot.answer_callback_query(call.id, f"Статус: {st}", show_alert=False)


def mark_received(user_id: int, act_id: str, code: str):
    with ACTIVE_LOCK:
        for o in ACTIVE.get(user_id, []):
            if o["act_id"] == act_id:
                o["code"] = code
                o["finished"] = True
                o["stop"] = True
                break


def stop_order(user_id: int, act_id: str):
    with ACTIVE_LOCK:
        for o in ACTIVE.get(user_id, []):
            if o["act_id"] == act_id:
                o["stop"] = True
                o["finished"] = True
                break


def wait_sms(user_id: int, order: dict):
    act_id = order["act_id"]
    phone = order["phone"]
    started = order["started"]
    chat_id = order["chat_id"]

    poll = 5
    while time.time() - started < MAX_WAIT:
        if order.get("stop"):
            return
        time.sleep(poll)
        try:
            status, data = api("GET", f"/v1/activations/{act_id}")
        except Exception:
            continue

        if status != 200:
            if status in (401, 404):
                return
            continue

        st = data.get("status")
        code = data.get("sms_code")

        if st == "sms_received" and code:
            mark_received(user_id, act_id, code)
            bot.send_message(
                chat_id,
                f"✅ <b>КОД:</b> <code>{code}</code>\n"
                f"Номер: <code>+{phone}</code>\n"
                f"ID: <code>{act_id}</code>\n\n"
                f"(сохранён в «Мои коды»)",
            )
            log.info("CODE received id=%s code=%s", act_id, code)
            return

        if st in ("failed", "expired", "closed"):
            stop_order(user_id, act_id)
            bot.send_message(
                chat_id,
                f"⚠️ Заказ завершён без кода (status={st})\nID: <code>{act_id}</code>",
            )
            return

        poll = max(3, int(data.get("poll_after_seconds") or 5))

    stop_order(user_id, act_id)
    bot.send_message(
        chat_id,
        f"⏰ Время ожидания вышло (8 мин)\nID: <code>{act_id}</code>",
    )


# ---------------------------------------------------------------------------
# Health server for Render
# ---------------------------------------------------------------------------
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format, *args):
        pass


def run_health_server():
    port = int(os.getenv("PORT", "8080"))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    log.info("Health server on :%s", port)
    server.serve_forever()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    log.info("Starting bot… allowed users: %s", ALLOWED_IDS)
    threading.Thread(target=run_health_server, daemon=True).start()
    bot.infinity_polling(timeout=30, long_polling_timeout=25, skip_pending=True)
