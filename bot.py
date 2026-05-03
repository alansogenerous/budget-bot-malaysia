
import logging
import sqlite3
import os
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN", "8604173888:AAFF8fh-qgDGQ2nlvqaJPz1kmb2qkCDv4_g")

# States
MENU, AMOUNT_IN, AMOUNT_OUT, CATEGORY_IN, CATEGORY_OUT, ITEM_OUT, TAX_OUT, CONFIRM = range(8)

def init_db():
    conn = sqlite3.connect("budget.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            type TEXT,
            category TEXT,
            item TEXT,
            amount REAL,
            tax_category TEXT,
            tax_claimable INTEGER DEFAULT 0,
            date TEXT,
            month TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS budgets (
            user_id INTEGER,
            category TEXT,
            limit_amount REAL,
            PRIMARY KEY (user_id, category)
        )
    """)
    conn.commit()
    conn.close()

# AUTO TAX DETECTION — User tak perlu decide!
# Category → (tax_claimable, tax_name, message)
AUTO_TAX = {
    "Rumah": (0, "personal", "🔴 Personal — tak boleh claim tax"),
    "Utiliti": (0, "personal", "🔴 Personal — tak boleh claim tax"),
    "Kereta": (0, "personal", "🔴 Personal — tak boleh claim tax"),
    "Makan": (0, "personal", "🔴 Personal — tak boleh claim tax"),
    "Anak": (1, "childcare", "🟢 Boleh claim! Childcare relief (RM3k limit)"),
    "Kesihatan": (1, "medical_self", "🟢 Boleh claim! Medical relief (RM8k limit)"),
    "Hutang": (0, "personal", "🔴 Personal — tak boleh claim tax"),
    "Simpanan": (1, "sspn", "🟢 Boleh claim! SSPN/PRS relief"),
    "Lifestyle": (0, "personal", "🔴 Personal — tak boleh claim tax"),
}

# ============== START ==============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Clear any previous state
    context.user_data.clear()

    keyboard = [
        [InlineKeyboardButton("💵 MASUK DUIT", callback_data="menu_income"),
         InlineKeyboardButton("💸 KELUAR DUIT", callback_data="menu_expense")],
        [InlineKeyboardButton("📊 TENGOK BAKI", callback_data="menu_balance"),
         InlineKeyboardButton("📈 RINGKASAN", callback_data="menu_summary")],
        [InlineKeyboardButton("⚙️ SET BAJET", callback_data="menu_budget"),
         InlineKeyboardButton("🧾 TAX INFO", callback_data="menu_tax")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "💰 **BUDGET BOT MUDAH**\n\n"
        "Hai! Bot ni senang je.\n"
        "Tap button bawah ni:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    return MENU

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "menu_income":
        keyboard = [
            [InlineKeyboardButton("RM 1,000", callback_data="in_1000"),
             InlineKeyboardButton("RM 2,000", callback_data="in_2000")],
            [InlineKeyboardButton("RM 3,000", callback_data="in_3000"),
             InlineKeyboardButton("RM 4,000", callback_data="in_4000")],
            [InlineKeyboardButton("RM 5,000", callback_data="in_5000"),
             InlineKeyboardButton("RM 6,000", callback_data="in_6000")],
            [InlineKeyboardButton("Taip sendiri ✏️", callback_data="in_custom")],
            [InlineKeyboardButton("🔙 Menu Utama", callback_data="back_menu")],
        ]
        await query.edit_message_text(
            "💵 **MASUK DUIT**\n\nBerapa duit masuk?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return AMOUNT_IN

    elif data == "menu_expense":
        keyboard = [
            [InlineKeyboardButton("RM 10", callback_data="out_10"),
             InlineKeyboardButton("RM 20", callback_data="out_20")],
            [InlineKeyboardButton("RM 50", callback_data="out_50"),
             InlineKeyboardButton("RM 100", callback_data="out_100")],
            [InlineKeyboardButton("RM 200", callback_data="out_200"),
             InlineKeyboardButton("RM 500", callback_data="out_500")],
            [InlineKeyboardButton("Taip sendiri ✏️", callback_data="out_custom")],
            [InlineKeyboardButton("🔙 Menu Utama", callback_data="back_menu")],
        ]
        await query.edit_message_text(
            "💸 **KELUAR DUIT**\n\nBerapa duit keluar?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return AMOUNT_OUT

    elif data == "menu_balance":
        return await show_balance(query, context)

    elif data == "menu_summary":
        return await show_summary(query, context)

    elif data == "menu_budget":
        await query.edit_message_text(
            "⚙️ **SET BAJET**\n\n"
            "Taip command ni:\n"
            "/budget Makan 1000\n\n"
            "Kategori: Rumah, Utiliti, Kereta, Makan, Anak, Kesihatan, Hutang, Simpanan, Lifestyle"
        )
        return MENU

    elif data == "menu_tax":
        return await show_tax(query, context)

    elif data == "back_menu":
        return await back_to_menu(query)

    return MENU

# ============== INCOME FLOW ==============

async def income_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "back_menu":
        return await back_to_menu(query)

    if data == "in_custom":
        await query.edit_message_text("💵 Taip amaun (nombor je):\nContoh: 5500")
        return CATEGORY_IN

    amount = int(data.replace("in_", ""))
    context.user_data["amount"] = amount
    context.user_data["type"] = "income"

    keyboard = [
        [InlineKeyboardButton("💼 Gaji", callback_data="cat_gaji")],
        [InlineKeyboardButton("💻 Side Hustle", callback_data="cat_side")],
        [InlineKeyboardButton("📈 Dividen", callback_data="cat_dividen")],
        [InlineKeyboardButton("🏠 Rental", callback_data="cat_rental")],
        [InlineKeyboardButton("🎨 Freelance", callback_data="cat_freelance")],
        [InlineKeyboardButton("Lain-lain", callback_data="cat_lain")],
        [InlineKeyboardButton("🔙 Menu Utama", callback_data="back_menu")],
    ]
    await query.edit_message_text(
        f"💵 **RM {amount:,}**\n\nDuit apa ni?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CATEGORY_IN

async def income_custom_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text.replace(",", "").replace("RM", "").strip())
    except ValueError:
        await update.message.reply_text("❌ Taip nombor je. Contoh: 5500")
        return CATEGORY_IN

    context.user_data["amount"] = amount
    context.user_data["type"] = "income"

    keyboard = [
        [InlineKeyboardButton("💼 Gaji", callback_data="cat_gaji")],
        [InlineKeyboardButton("💻 Side Hustle", callback_data="cat_side")],
        [InlineKeyboardButton("📈 Dividen", callback_data="cat_dividen")],
        [InlineKeyboardButton("🏠 Rental", callback_data="cat_rental")],
        [InlineKeyboardButton("🎨 Freelance", callback_data="cat_freelance")],
        [InlineKeyboardButton("Lain-lain", callback_data="cat_lain")],
        [InlineKeyboardButton("🔙 Menu Utama", callback_data="back_menu")],
    ]
    await update.message.reply_text(
        f"💵 **RM {amount:,.0f}**\n\nDuit apa ni?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CATEGORY_IN

async def income_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "back_menu":
        return await back_to_menu(query)

    cat_map = {
        "cat_gaji": "Gaji",
        "cat_side": "Side Hustle",
        "cat_dividen": "Dividen",
        "cat_rental": "Rental",
        "cat_freelance": "Freelance",
        "cat_lain": "Lain-lain",
    }

    category = cat_map.get(data, "Lain-lain")
    amount = context.user_data.get("amount", 0)
    user_id = update.effective_user.id

    now = datetime.now()
    month = now.strftime("%Y-%m")

    conn = sqlite3.connect("budget.db")
    c = conn.cursor()
    c.execute("""
        INSERT INTO transactions (user_id, type, category, item, amount, tax_category, tax_claimable, date, month)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, "income", category, category, amount, "income", 0, now.isoformat(), month))
    conn.commit()
    conn.close()

    keyboard = [[InlineKeyboardButton("🔙 Menu Utama", callback_data="back_menu")]]
    await query.edit_message_text(
        f"✅ **Done!**\n\n"
        f"💵 {category}\n"
        f"💰 RM {amount:,.0f}\n\n"
        f"Duit dah masuk! ✅",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return MENU

# ============== EXPENSE FLOW ==============

async def expense_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "back_menu":
        return await back_to_menu(query)

    if data == "out_custom":
        await query.edit_message_text("💸 Taip amaun (nombor je):\nContoh: 35")
        return ITEM_OUT

    amount = int(data.replace("out_", ""))
    context.user_data["amount"] = amount
    context.user_data["type"] = "expense"

    keyboard = [
        [InlineKeyboardButton("🏠 Rumah", callback_data="exp_Rumah")],
        [InlineKeyboardButton("⚡ Utiliti", callback_data="exp_Utiliti")],
        [InlineKeyboardButton("🚗 Kereta", callback_data="exp_Kereta")],
        [InlineKeyboardButton("🍚 Makan", callback_data="exp_Makan")],
        [InlineKeyboardButton("👶 Anak", callback_data="exp_Anak")],
        [InlineKeyboardButton("🏥 Kesihatan", callback_data="exp_Kesihatan")],
        [InlineKeyboardButton("💸 Hutang", callback_data="exp_Hutang")],
        [InlineKeyboardButton("🎯 Simpanan", callback_data="exp_Simpanan")],
        [InlineKeyboardButton("🎉 Lifestyle", callback_data="exp_Lifestyle")],
        [InlineKeyboardButton("🔙 Menu Utama", callback_data="back_menu")],
    ]
    await query.edit_message_text(
        f"💸 **RM {amount}**\n\nBeli apa?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ITEM_OUT

async def expense_custom_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text.replace(",", "").replace("RM", "").strip())
    except ValueError:
        await update.message.reply_text("❌ Taip nombor je. Contoh: 35")
        return ITEM_OUT

    context.user_data["amount"] = amount
    context.user_data["type"] = "expense"

    keyboard = [
        [InlineKeyboardButton("🏠 Rumah", callback_data="exp_Rumah")],
        [InlineKeyboardButton("⚡ Utiliti", callback_data="exp_Utiliti")],
        [InlineKeyboardButton("🚗 Kereta", callback_data="exp_Kereta")],
        [InlineKeyboardButton("🍚 Makan", callback_data="exp_Makan")],
        [InlineKeyboardButton("👶 Anak", callback_data="exp_Anak")],
        [InlineKeyboardButton("🏥 Kesihatan", callback_data="exp_Kesihatan")],
        [InlineKeyboardButton("💸 Hutang", callback_data="exp_Hutang")],
        [InlineKeyboardButton("🎯 Simpanan", callback_data="exp_Simpanan")],
        [InlineKeyboardButton("🎉 Lifestyle", callback_data="exp_Lifestyle")],
        [InlineKeyboardButton("🔙 Menu Utama", callback_data="back_menu")],
    ]
    await update.message.reply_text(
        f"💸 **RM {amount:,.0f}**\n\nBeli apa?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ITEM_OUT

async def expense_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "back_menu":
        return await back_to_menu(query)

    category = data.replace("exp_", "")
    context.user_data["category"] = category
    amount = context.user_data.get("amount", 0)

    # AUTO DETECT TAX — user tak perlu decide!
    tax_info = AUTO_TAX.get(category, (0, "personal", "🔴 Personal — tak boleh claim tax"))
    tax_claimable, tax_tag, tax_msg = tax_info

    user_id = update.effective_user.id
    now = datetime.now()
    month = now.strftime("%Y-%m")

    conn = sqlite3.connect("budget.db")
    c = conn.cursor()
    c.execute("""
        INSERT INTO transactions (user_id, type, category, item, amount, tax_category, tax_claimable, date, month)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, "expense", category, category, amount, tax_tag, tax_claimable, now.isoformat(), month))
    conn.commit()
    conn.close()

    # Budget check
    conn = sqlite3.connect("budget.db")
    c = conn.cursor()
    c.execute("SELECT limit_amount FROM budgets WHERE user_id=? AND category=?", (user_id, category))
    result = c.fetchone()

    budget_msg = ""
    if result:
        limit = result[0]
        c.execute("SELECT SUM(amount) FROM transactions WHERE user_id=? AND type='expense' AND category=? AND month=?",
                  (user_id, category, month))
        total = c.fetchone()[0] or 0
        pct = (total / limit) * 100 if limit > 0 else 0
        status = "🟢" if pct < 75 else "🟡" if pct < 90 else "🔴"
        budget_msg = f"\n\n📊 Bajet {category}: {status} RM {total:.0f} / RM {limit:.0f} ({pct:.0f}%)"

    conn.close()

    keyboard = [[InlineKeyboardButton("🔙 Menu Utama", callback_data="back_menu")]]
    await query.edit_message_text(
        f"✅ **Done!**\n\n"
        f"💸 {category}\n"
        f"💰 RM {amount:,.0f}\n"
        f"{tax_msg}{budget_msg}\n\n"
        f"Duit dah record! ✅",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return MENU

# ============== BALANCE / SUMMARY / TAX ==============

async def show_balance(query, context):
    user_id = query.from_user.id
    month = datetime.now().strftime("%Y-%m")

    conn = sqlite3.connect("budget.db")
    c = conn.cursor()
    c.execute("SELECT SUM(amount) FROM transactions WHERE user_id=? AND type='income' AND month=?", (user_id, month))
    income = c.fetchone()[0] or 0
    c.execute("SELECT SUM(amount) FROM transactions WHERE user_id=? AND type='expense' AND month=?", (user_id, month))
    expense = c.fetchone()[0] or 0
    conn.close()

    baki = income - expense
    status = "🔴 DEFISIT" if baki < 0 else "🟢 SURPLUS"

    keyboard = [[InlineKeyboardButton("🔙 Menu Utama", callback_data="back_menu")]]
    await query.edit_message_text(
        f"🎯 **BAKI BULAN INI**\n\n"
        f"💵 Masuk: RM {income:,.0f}\n"
        f"💸 Keluar: RM {expense:,.0f}\n"
        f"🎯 Baki: RM {baki:,.0f}\n"
        f"{status}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return MENU

async def show_summary(query, context):
    user_id = query.from_user.id
    month = datetime.now().strftime("%Y-%m")

    conn = sqlite3.connect("budget.db")
    c = conn.cursor()
    c.execute("SELECT category, SUM(amount) FROM transactions WHERE user_id=? AND type='expense' AND month=? GROUP BY category ORDER BY SUM(amount) DESC", (user_id, month))
    expenses = c.fetchall()
    c.execute("SELECT SUM(amount) FROM transactions WHERE user_id=? AND type='income' AND month=?", (user_id, month))
    income = c.fetchone()[0] or 0
    c.execute("SELECT SUM(amount) FROM transactions WHERE user_id=? AND type='expense' AND month=?", (user_id, month))
    expense_total = c.fetchone()[0] or 0
    conn.close()

    baki = income - expense_total
    exp_text = "\n".join([f"• {cat}: RM {amt:,.0f}" for cat, amt in expenses]) or "Tiada"

    keyboard = [[InlineKeyboardButton("🔙 Menu Utama", callback_data="back_menu")]]
    await query.edit_message_text(
        f"📈 **RINGKASAN {month}**\n\n"
        f"💵 Masuk: RM {income:,.0f}\n"
        f"💸 Keluar: RM {expense_total:,.0f}\n"
        f"🎯 Baki: RM {baki:,.0f}\n\n"
        f"📊 **Perbelanjaan:**\n{exp_text}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return MENU

async def show_tax(query, context):
    user_id = query.from_user.id

    conn = sqlite3.connect("budget.db")
    c = conn.cursor()
    c.execute("SELECT SUM(amount) FROM transactions WHERE user_id=? AND type='income'", (user_id,))
    income = c.fetchone()[0] or 0
    c.execute("SELECT SUM(amount) FROM transactions WHERE user_id=? AND type='expense' AND tax_claimable=1", (user_id,))
    relief = c.fetchone()[0] or 0

    # Get relief breakdown
    c.execute("SELECT category, SUM(amount) FROM transactions WHERE user_id=? AND type='expense' AND tax_claimable=1 GROUP BY category", (user_id,))
    relief_breakdown = c.fetchall()
    conn.close()

    relief_text = "\n".join([f"• {cat}: RM {amt:,.0f}" for cat, amt in relief_breakdown]) or "Tiada"

    keyboard = [[InlineKeyboardButton("🔙 Menu Utama", callback_data="back_menu")]]
    await query.edit_message_text(
        f"🧾 **TAX INFO**\n\n"
        f"📊 Total Income: RM {income:,.0f}\n"
        f"💼 Total Relief: RM {relief:,.0f}\n\n"
        f"📋 **Relief Breakdown:**\n{relief_text}\n\n"
        f"💡 Bot auto-tag tax untuk setiap perbelanjaan:\n"
        f"🟢 Anak, Kesihatan, Simpanan = Boleh claim\n"
        f"🔴 Lain-lain = Personal",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return MENU

# ============== BACK TO MENU ==============

async def back_to_menu(query):
    keyboard = [
        [InlineKeyboardButton("💵 MASUK DUIT", callback_data="menu_income"),
         InlineKeyboardButton("💸 KELUAR DUIT", callback_data="menu_expense")],
        [InlineKeyboardButton("📊 TENGOK BAKI", callback_data="menu_balance"),
         InlineKeyboardButton("📈 RINGKASAN", callback_data="menu_summary")],
        [InlineKeyboardButton("⚙️ SET BAJET", callback_data="menu_budget"),
         InlineKeyboardButton("🧾 TAX INFO", callback_data="menu_tax")],
    ]
    await query.edit_message_text(
        "💰 **BUDGET BOT MUDAH**\n\n"
        "Pilih:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return MENU

# ============== BUDGET COMMAND ==============

async def budget_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text(
            "⚙️ **SET BAJET**\n\n"
            "Format: /budget [kategori] [amaun]\n"
            "Contoh: /budget Makan 1000\n\n"
            "Kategori: Rumah, Utiliti, Kereta, Makan, Anak, Kesihatan, Hutang, Simpanan, Lifestyle"
        )
        return

    category = context.args[0].capitalize()
    try:
        amount = float(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Amaun mesti nombor")
        return

    user_id = update.effective_user.id

    conn = sqlite3.connect("budget.db")
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO budgets (user_id, category, limit_amount) VALUES (?, ?, ?)",
              (user_id, category, amount))
    conn.commit()
    conn.close()

    await update.message.reply_text(f"✅ Bajet **{category}** set ke RM {amount:,.0f}")

# ============== MAIN ==============

def main():
    init_db()

    application = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MENU: [
                CallbackQueryHandler(menu_handler, pattern="^menu_"),
                CallbackQueryHandler(back_to_menu, pattern="^back_menu$")
            ],
            AMOUNT_IN: [
                CallbackQueryHandler(income_amount, pattern="^in_|back_menu"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, income_custom_amount)
            ],
            CATEGORY_IN: [
                CallbackQueryHandler(income_category, pattern="^cat_|back_menu"),
                CallbackQueryHandler(back_to_menu, pattern="^back_menu$")
            ],
            AMOUNT_OUT: [
                CallbackQueryHandler(expense_amount, pattern="^out_|back_menu"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, expense_custom_amount)
            ],
            ITEM_OUT: [
                CallbackQueryHandler(expense_category, pattern="^exp_|back_menu"),
                CallbackQueryHandler(back_to_menu, pattern="^back_menu$")
            ],
        },
        fallbacks=[
            CommandHandler("start", start),
            CallbackQueryHandler(back_to_menu, pattern="^back_menu$")
        ],
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("budget", budget_cmd))

    application.run_polling()

if __name__ == "__main__":
    main()
