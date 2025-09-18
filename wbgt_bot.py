import os
import datetime
import requests
from collections import defaultdict
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from flask import Flask

# --- WBGT functions (same as before) ---
def fetch_wbgt(date_input):
    url = "https://api-open.data.gov.sg/v2/real-time/api/weather"
    params = {"api": "wbgt", "date": date_input}
    response = requests.get(url, params=params)
    if response.status_code != 200:
        raise RuntimeError(f"Error fetching data: HTTP {response.status_code}")
    return response.json()

def format_wbgt_by_station_split(data):
    records = data.get("data", {}).get("records", [])
    if not records:
        return ["No records found."]

    station_data = defaultdict(list)
    for record in records:
        dt = record.get("datetime")
        readings = record.get("item", {}).get("readings", [])
        for rd in readings:
            station = rd.get("station", {})
            town = station.get("townCenter", station.get("name", station.get("id")))
            wbgt = rd.get("wbgt")
            heat_stress = rd.get("heatStress")
            station_data[town].append((dt, wbgt, heat_stress))

    messages = []
    for station in sorted(station_data.keys()):
        lines = [f"Station: {station}"]
        readings_sorted = sorted(
            station_data[station],
            key=lambda x: datetime.datetime.fromisoformat(x[0].replace("Z", "+00:00"))
        )
        for dt, wbgt, heat_stress in readings_sorted:
            lines.append(f"  {dt}  WBGT: {wbgt}  HeatStress: {heat_stress}")
        messages.append("\n".join(lines))

    return messages

# --- Telegram bot handlers ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")  # From Render environment variables

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hi! Send me a date (YYYY-MM-DD) or datetime (YYYY-MM-DDTHH:MM:SS), "
        "and I'll reply with WBGT data."
    )

async def handle_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    date_input = update.message.text.strip()
    try:
        if "T" in date_input:
            datetime.datetime.fromisoformat(date_input)
        else:
            datetime.datetime.strptime(date_input, "%Y-%m-%d")
    except ValueError:
        await update.message.reply_text(
            "Invalid date format. Use YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS"
        )
        return

    try:
        data = fetch_wbgt(date_input)
        messages = format_wbgt_by_station_split(data)
        for msg in messages:
            await update.message.reply_text(msg)
    except Exception as e:
        await update.message.reply_text(f"Error fetching WBGT data: {e}")

# --- Run Telegram bot ---
from threading import Thread

def run_bot():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_date))
    print("Bot is running...")
    app.run_polling()

Thread(target=run_bot).start()

# --- Dummy Flask server to satisfy Render ---
flask_app = Flask("WBGT Telegram Bot")

@flask_app.route("/")
def home():
    return "WBGT Telegram Bot is running!"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))  # Render sets $PORT automatically
    flask_app.run(host="0.0.0.0", port=port)