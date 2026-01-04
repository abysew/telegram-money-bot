import os
import json
import asyncio
from datetime import datetime, date
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ================= НАСТРОЙКИ =================

TOKEN = os.getenv("TOKEN")
REPORT_CHAT_ID = int(os.getenv("REPORT_CHAT_ID"))

DATA_FILE = "data.json"
MOSCOW_TZ = ZoneInfo("Europe/Moscow")
ANTI_DOUBLE_SECONDS = 3

# ================= BOT =================

bot = Bot(token=TOKEN)
dp = Dispatcher()

# ================= ДАННЫЕ =================

def load_data():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            data.setdefault("history", [])
            data.setdefault("last_action", None)
            return data
    except FileNotFoundError:
        data = {
            "double": 0,
            "triple": 0,
            "five": 0,
            "total": 0,
            "start_date": datetime.now(MOSCOW_TZ).strftime("%d.%m.%Y"),
            "history": [],
            "last_action": None
        }
        save_data(data)
        return data

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ================= КНОПКИ =================

keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Двойной"), KeyboardButton(text="Тройной")],
        [KeyboardButton(text="Пятерочка")],
        [KeyboardButton(text="Минус 1")],
        [KeyboardButton(text="История за сегодня")],
        [KeyboardButton(text="Отправить отчет")]
    ],
    resize_keyboard=True
)

# ================= START =================

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("Бот учета запущен ✅", reply_markup=keyboard)

# ================= АНТИДВОЙНОЕ НАЖАТИЕ =================

def is_double_click(data, action):
    last = data.get("last_action")
    if not last or last["type"] != action:
        return False

    last_time = datetime.fromisoformat(last["time"])
    now = datetime.now(MOSCOW_TZ)

    return (now - last_time).total_seconds() < ANTI_DOUBLE_SECONDS

# ================= ДОБАВЛЕНИЕ =================

@dp.message(lambda m: m.text in ["Двойной", "Тройной", "Пятерочка"])
async def add_item(message: types.Message):
    data = load_data()
    now = datetime.now(MOSCOW_TZ)

    mapping = {
        "Двойной": ("double", 150),
        "Тройной": ("triple", 300),
        "Пятерочка": ("five", 200)
    }

    key, amount = mapping[message.text]

    if is_double_click(data, key):
        await message.answer("⏳ Слишком быстро. Защита от двойного нажатия")
        return

    data[key] += 1
    data["total"] += amount

    data["history"].append({
        "type": key,
        "amount": amount,
        "time": now.isoformat()
    })

    data["last_action"] = {
        "type": key,
        "time": now.isoformat()
    }

    save_data(data)
    await message.answer(get_current_report(data))

# ================= МИНУС 1 =================

@dp.message(lambda m: m.text == "Минус 1")
async def minus_one(message: types.Message):
    data = load_data()

    if not data["history"]:
        await message.answer("❗ Нечего отменять")
        return

    last = data["history"].pop()
    data[last["type"]] -= 1
    data["total"] -= last["amount"]

    save_data(data)
    await message.answer("↩️ Последнее действие отменено\n\n" + get_current_report(data))

# ================= ИСТОРИЯ ЗА СЕГОДНЯ =================

@dp.message(lambda m: m.text == "История за сегодня")
async def today_history(message: types.Message):
    data = load_data()
    today = date.today()

    lines = []
    total = 0

    for h in data["history"]:
        t = datetime.fromisoformat(h["time"]).astimezone(MOSCOW_TZ)
        if t.date() == today:
            name = {
                "double": "Двойной",
                "triple": "Тройной",
                "five": "Пятерочка"
            }[h["type"]]

            lines.append(f"{t.strftime('%H:%M')} — {name} ({h['amount']} ₽)")
            total += h["amount"]

    if not lines:
        await message.answer("Сегодня записей пока нет")
        return

    text = (
        f"История за сегодня ({today.strftime('%d.%m')})\n\n"
        + "\n".join(lines)
        + f"\n\nИтого за день: {total} ₽"
    )

    await message.answer(text)

# ================= ТЕКУЩИЙ ОТЧЕТ =================

def get_current_report(data):
    now = datetime.now(MOSCOW_TZ).strftime("%d.%m.%Y")
    return (
        f"Текущий период {data['start_date']}–{now}\n\n"
        f"{data['double']} двойных = {data['double'] * 150} ₽\n"
        f"{data['triple']} тройных = {data['triple'] * 300} ₽\n"
        f"{data['five']} пятерочка = {data['five'] * 200} ₽\n\n"
        f"Итого: {data['total']} ₽"
    )

# ================= НАПОМИНАНИЕ =================

async def daily_reminder():
    data = load_data()
    today = date.today()

    for h in data["history"]:
        t = datetime.fromisoformat(h["time"]).astimezone(MOSCOW_TZ)
        if t.date() == today:
            return

    await bot.send_message(
        REPORT_CHAT_ID,
        "🔔 Напоминание\nСегодня пока нет записей. Не забудь внести данные."
    )

# ================= НЕДЕЛЬНЫЙ ОТЧЕТ =================

async def weekly_report():
    data = load_data()
    start = datetime.strptime(data["start_date"], "%d.%m.%Y")
    end = datetime.now(MOSCOW_TZ)

    text = (
        f"Сводная за неделю {start.strftime('%d.%m')}–{end.strftime('%d.%m')}\n\n"
        f"{data['double']} двойных = {data['double'] * 150} ₽\n"
        f"{data['triple']} тройных = {data['triple'] * 300} ₽\n"
        f"{data['five']} пятерочка = {data['five'] * 200} ₽\n\n"
        f"Итого: {data['total']} ₽"
    )

    await bot.send_message(REPORT_CHAT_ID, text)

    save_data({
        "double": 0,
        "triple": 0,
        "five": 0,
        "total": 0,
        "start_date": end.strftime("%d.%m.%Y"),
        "history": [],
        "last_action": None
    })

# ================= MAIN =================

async def main():
    scheduler = AsyncIOScheduler(timezone=MOSCOW_TZ)

    scheduler.add_job(weekly_report, "cron", day_of_week="sun", hour=23, minute=30)
    scheduler.add_job(daily_reminder, "cron", hour=21, minute=0)

    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
