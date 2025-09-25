import os
import datetime
import requests
from collections import defaultdict
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler
from flask import Flask
import threading

# --- WBGT functions ---
def fetch_wbgt(date_input):
    url = "https://api-open.data.gov.sg/v2/real-time/api/weather"
    params = {"api": "wbgt", "date": date_input}
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json()

def group_wbgt_by_station(data):
    """Return dict: {station_name: [(datetime, wbgt, heat_stress), ...]}"""
    records = data.get("data", {}).get("records", [])
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
    return station_data

def format_station_data(station, readings):
    lines = [f"Station: {station}"]
    readings_sorted = sorted(
        readings,
        key=lambda x: datetime.datetime.fromisoformat(x[0].replace("Z", "+00:00"))
    )
    for dt, wbgt, heat_stress in readings_sorted:
        lines.append(f"  {dt}  WBGT: {wbgt}  HeatStress: {heat_stress}")
    return "\n".join(lines)

# --- Telegram bot handlers ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable not set!")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hi! Send me a date (YYYY-MM-DD) or datetime (YYYY-MM-DDTHH:MM:SS), "
        "and I'll show you WBGT data by station."
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
        station_data = group_wbgt_by_station(data)

        if not station_data:
            await update.message.reply_text("No records found.")
            return

        # Save station data for this user
        context.user_data["station_data"] = station_data

        # Build inline keyboard (1 button per station)
        keyboard = [
            [InlineKeyboardButton(station, callback_data=station)]
            for station in sorted(station_data.keys())
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text("Choose a station:", reply_markup=reply_markup)

    except Exception as e:
        await update.message.reply_text(f"Error fetching WBGT data: {e}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    station = query.data
    station_data = context.user_data.get("station_data", {})

    if station in station_data:
        text = format_station_data(station, station_data[station])
        await query.message.reply_text(text)
    else:
        await query.message.reply_text("Station data not found. Please send the date again.")

# --- Minimal Flask server in background thread ---
def run_flask():
    flask_app = Flask("WBGT Telegram Bot")

    @flask_app.route("/")
    def home():
        return "WBGT Telegram Bot is running!"

    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_flask, daemon=True).start()

# --- Run Telegram bot in main thread ---
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_date))
app.add_handler(CallbackQueryHandler(button_handler))
print("Telegram bot with station selection is running...")
app.run_polling()