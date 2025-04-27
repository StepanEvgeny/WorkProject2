import sqlite3
from telegram import Update, ForceReply, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from pydub import AudioSegment
import wave
import os
from vosk import Model, KaldiRecognizer

# === Часто задаваемые вопросы (с короткими ключами) ===
FAQ = {
    "faq1": {
        "question": "как оформить заказ",
        "answer": "Выберите товар, нажмите 'Добавить в корзину', затем перейдите в корзину и следуйте инструкциям."
    },
    "faq2": {
        "question": "статус моего заказа",
        "answer": "Войдите в свой аккаунт и откройте раздел 'Мои заказы'. Там указан статус."
    },
    "faq3": {
        "question": "как отменить заказ",
        "answer": "Свяжитесь с нашей службой поддержки как можно скорее — мы постараемся отменить заказ до отправки."
    },
    "faq4": {
        "question": "товар пришел поврежденным",
        "answer": "Свяжитесь с поддержкой и отправьте фото повреждений. Мы поможем с возвратом или обменом."
    },
    "faq5": {
        "question": "как связаться с технической поддержкой",
        "answer": "Позвоните по номеру на сайте или напишите в чат-бот."
    },
    "faq6": {
        "question": "информация о доставке",
        "answer": "Информацию о доставке смотрите на странице оформления заказа."
    }
}

ADMIN_ID = 1234567  # Замените на ваш Telegram user ID

def init_db():
    conn = sqlite3.connect("messages.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            message TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_message(user_id, username, message):
    conn = sqlite3.connect("messages.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO messages (user_id, username, message) VALUES (?, ?, ?)",
                   (user_id, username, message))
    conn.commit()
    conn.close()

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_msg = update.message.text.lower()
    user_id = update.message.from_user.id
    username = update.message.from_user.username or "anonymous"

    save_message(user_id, username, user_msg)

    for item in FAQ.values():
        if item["question"] in user_msg:
            await update.message.reply_text(item["answer"])
            return

    await update.message.reply_text("Спасибо за обращение! Мы передадим ваш вопрос специалисту.")
    if user_id != ADMIN_ID:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"❗ Новый вопрос от @{username}:\n{user_msg}"
        )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_html(
        rf"Привет, {user.mention_html()}! Я бот поддержки. Напиши свой вопрос — я постараюсь помочь.",
        reply_markup=ForceReply(selective=True),
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/start – Начать диалог\n"
        "/help – Показать помощь\n"
        "/messages – Показать последние сообщения\n"
        "/faq – Часто задаваемые вопросы"
    )

async def messages_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Нет доступа.")
        return

    conn = sqlite3.connect("messages.db")
    cursor = conn.cursor()
    cursor.execute("SELECT username, message FROM messages ORDER BY id DESC LIMIT 5")
    rows = cursor.fetchall()
    conn.close()

    response = "\n\n".join([f"@{row[0]}: {row[1]}" for row in rows])
    await update.message.reply_text(response or "Сообщений нет.")

async def faq_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton(text=data["question"].capitalize(), callback_data=key)]
        for key, data in FAQ.items()
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите вопрос из списка:", reply_markup=reply_markup)

async def faq_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    key = query.data

    if key == "back_to_faq":
        keyboard = [
            [InlineKeyboardButton(text=data["question"].capitalize(), callback_data=k)]
            for k, data in FAQ.items()
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Выберите вопрос из списка:", reply_markup=reply_markup)
        return

    faq_item = FAQ.get(key)
    if faq_item:
        keyboard = [[InlineKeyboardButton("🔙 Назад в список", callback_data="back_to_faq")]]
        await query.edit_message_text(
            f"🧾 *{faq_item['question'].capitalize()}*\n\n{faq_item['answer']}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await query.edit_message_text("Ошибка: вопрос не найден.")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await context.bot.get_file(update.message.voice.file_id)
    await file.download_to_drive("voice.ogg")

    ogg = AudioSegment.from_file("voice.ogg")
    ogg.export("voice.wav", format="wav")

    wf = wave.open("voice.wav", "rb")
    model = Model("model")
    rec = KaldiRecognizer(model, wf.getframerate())

    text = ""
    while True:
        data = wf.readframes(4000)
        if len(data) == 0:
            break
        if rec.AcceptWaveform(data):
            result = eval(rec.Result())
            text += result.get("text", "") + " "

    os.remove("voice.ogg")
    os.remove("voice.wav")

    update.message.text = text.strip()
    await handle_message(update, context)

def main():
    init_db()
    app = Application.builder().token("Token_Bot").build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("messages", messages_command))
    app.add_handler(CommandHandler("faq", faq_command))
    app.add_handler(CallbackQueryHandler(faq_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    print("Бот запущен.")
    app.run_polling()

if __name__ == "__main__":
    main()
