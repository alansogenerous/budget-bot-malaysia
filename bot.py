
import logging
import sqlite3
import json
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Database setup
def init_db():
    conn = sqlite3.connect("budget.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    c.execute("""
        CREATE TABLE IF NOT EXISTS tax_summary (
            user_id INTEGER PRIMARY KEY,
            year INTEGER,
            total_income REAL DEFAULT 0,
            total_relief REAL DEFAULT 0,
            tax_payable REAL DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

# Tax categories database
TAX_CATEGORIES = {
    "income": {
        "gaji": {"taxable": True, "note": "EA Form", "rate": "Progressive"},
        "side_hustle": {"taxable": True, "note": "Business income", "rate": "Progressive"},
        "dividen_asb": {"taxable": False, "note": "Tax exempt", "rate": "0%"},
        "dividen_saham": {"taxable": True, "note": "Withholding 8%", "rate": "8%"},
        "rental": {"taxable": True, "note": "Rental income", "rate": "Progressive"},
        "freelance": {"taxable": True, "note": "Business income", "rate": "Progressive"},
        "epf_withdrawal": {"taxable": False, "note": "Exempt", "rate": "0%"},
        "zakat_income": {"taxable": False, "note": "Tax rebate", "rate": "Rebate"},
    },
    "expense_relief": {
        "medical_parents": {"limit": 8000, "category": "Medical", "section": "Self + Parents"},
        "medical_self": {"limit": 8000, "category": "Medical", "section": "Self + Spouse + Child"},
        "education_self": {"limit": 7000, "category": "Education", "section": "Self"},
        "education_child": {"limit": 8000, "category": "Education", "section": "Child"},
        "sports": {"limit": 1000, "category": "Lifestyle", "section": "Sports"},
        "lifestyle": {"limit": 2500, "category": "Lifestyle", "section": "Books/Gadget"},
        "breastfeeding": {"limit": 1000, "category": "Child", "section": "Breastfeeding"},
        "childcare": {"limit": 3000, "category": "Child", "section": "Tadika/Taska"},
        "sspn": {"limit": 8000, "category": "Education", "section": "SSPN"},
        "prs": {"limit": 3000, "category": "Retirement", "section": "PRS"},
        "life_insurance": {"limit": 3000, "category": "Insurance", "section": "Life"},
        "medical_insurance": {"limit": 3000, "category": "Insurance", "section": "Medical"},
        "epf_self": {"limit": 4000, "category": "Retirement", "section": "EPF (Self-employed)"},
        "socso": {"limit": 350, "category": "Social", "section": "SOCSO"},
        "zakat_expense": {"limit": 999999, "category": "Rebate", "section": "Zakat"},
        "donation": {"limit": 0.1, "category": "Donation", "section": "Approved (10% income)"},
    },
    "expense_business": {
        "rental_business": {"claimable": True, "note": "Business rental"},
        "motor_business": {"claimable": True, "note": "Business % of vehicle"},
        "petrol_business": {"claimable": True, "note": "Business % of petrol"},
        "internet_business": {"claimable": True, "note": "Business % of internet"},
        "utility_business": {"claimable": True, "note": "Business % of utility"},
    }
}

# Malaysian tax brackets 2026
TAX_BRACKETS = [
    (0, 5000, 0),
    (5000, 20000, 0.01),
    (20000, 35000, 0.03),
    (35000, 50000, 0.06),
    (50000, 70000, 0.11),
    (70000, 100000, 0.19),
    (100000, 400000, 0.25),
    (400000, 1000000, 0.26),
    (1000000, 999999999, 0.28),
]

# Budget categories
BUDGET_CATS = ["Rumah", "Utiliti", "Kereta", "Makan", "Anak", "Kesihatan", "Hutang", "Simpanan", "Lifestyle"]

# Conversation states
(SELECTING_TYPE, SELECTING_CATEGORY, ENTERING_ITEM, ENTERING_AMOUNT, 
 SELECTING_TAX, CONFIRMING) = range(6)

# ============== COMMAND HANDLERS ==============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome_text = f"""
💰 **BUDGET BOT MALAYSIA**

Hai {user.first_name}! 

Bot ni boleh:
• Track income & expense
• Auto-kira baki
• Warning bila over bajet
• **Tax relief tracker** (LHDN-ready)

**Commands:**
/masuk — Record income
/keluar — Record expense
/baki — Check balance
/ringkasan — Monthly summary
/bajet — Set budget
/tax — Tax summary
/export — Export data

Type /masuk or /keluar to start!
    """
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
📚 **COMMANDS:**

**Basic:**
/masuk — Income
/keluar — Expense
/baki — Balance
/ringkasan — Summary

**Budget:**
/bajet — Set limit
/alert — Check status

**Tax (LHDN):**
/tax — Tax summary
/tax_relief — Relief tracker
/tax_export — Export for LHDN

**Data:**
/history — View records
/export — Export Excel
/delete — Delete record
    """
    await update.message.reply_text(help_text, parse_mode="Markdown")

# ============== INCOME FLOW ==============

async def masuk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💼 Gaji", callback_data="income_gaji")],
        [InlineKeyboardButton("💻 Side Hustle", callback_data="income_side_hustle")],
        [InlineKeyboardButton("📈 Dividen ASB", callback_data="income_dividen_asb")],
        [InlineKeyboardButton("📊 Dividen Saham", callback_data="income_dividen_saham")],
        [InlineKeyboardButton("🏠 Rental", callback_data="income_rental")],
        [InlineKeyboardButton("🎨 Freelance", callback_data="income_freelance")],
        [InlineKeyboardButton("💰 EPF Withdrawal", callback_data="income_epf_withdrawal")],
        [InlineKeyboardButton("🕌 Zakat", callback_data="income_zakat")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "💵 **PENDAPATAN**\n\nPilih sumber:", 
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    return SELECTING_TYPE

async def keluar(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "💸 **PERBELANJAAN**\n\nPilih kategori:", 
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    return SELECTING_TYPE

async def type_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    if data == "cancel":
        await query.edit_message_text("❌ Cancelled.")
        return ConversationHandler.END

    context.user_data["type"] = data

    if data.startswith("income_"):
        income_type = data.replace("income_", "")
        context.user_data["category"] = income_type
        tax_info = TAX_CATEGORIES["income"].get(income_type, {})
        context.user_data["tax_info"] = tax_info

        await query.edit_message_text(
            f"💵 **{income_type.replace('_', ' ').title()}**\n\n"
            f"Tax status: {tax_info.get('note', 'N/A')}\n"
            f"Rate: {tax_info.get('rate', 'N/A')}\n\n"
            f"Nama item? (contoh: Gaji Mei, Shopee sales)\n"
            f"Taip nama atau skip:"
        )
        return ENTERING_ITEM

    elif data.startswith("exp_"):
        category = data.replace("exp_", "")
        context.user_data["category"] = category

        await query.edit_message_text(
            f"💸 **{category}**\n\n"
            f"Nama item? (contoh: TNB, GrabFood)\n"
            f"Taip nama atau skip:"
        )
        return ENTERING_ITEM

    return ConversationHandler.END

async def item_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    item = update.message.text
    if item.lower() == "skip":
        item = context.user_data.get("category", "Unknown")

    context.user_data["item"] = item

    await update.message.reply_text(
        f"💵 **{item}**\n\nAmaun? (taip nombor sahaja, contoh: 1200)"
    )
    return ENTERING_AMOUNT

async def amount_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text.replace(",", "").replace("RM", ""))
    except ValueError:
        await update.message.reply_text("❌ Sila taip nombor sahaja. Contoh: 1200")
        return ENTERING_AMOUNT

    context.user_data["amount"] = amount
    trans_type = context.user_data.get("type", "")

    if trans_type.startswith("income_"):
        # For income, just confirm
        return await confirm_transaction(update, context)

    elif trans_type.startswith("exp_"):
        # For expense, ask tax category
        keyboard = [
            [InlineKeyboardButton("🟢 Medical (Parents)", callback_data="tax_medical_parents")],
            [InlineKeyboardButton("🟢 Medical (Self/Family)", callback_data="tax_medical_self")],
            [InlineKeyboardButton("🟢 Education", callback_data="tax_education")],
            [InlineKeyboardButton("🟢 Insurance/EPF", callback_data="tax_insurance")],
            [InlineKeyboardButton("🟢 Childcare", callback_data="tax_childcare")],
            [InlineKeyboardButton("🟢 Lifestyle/Sports", callback_data="tax_lifestyle")],
            [InlineKeyboardButton("🟢 Business Expense", callback_data="tax_business")],
            [InlineKeyboardButton("🔴 Personal (Tak Claim)", callback_data="tax_personal")],
            [InlineKeyboardButton("⚪ Skip", callback_data="tax_skip")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "💼 **Tax Category?**\n\n"
            "Boleh claim income tax?\n"
            "Pilih yang sesuai:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        return SELECTING_TAX

    return ConversationHandler.END

async def tax_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    tax_data = query.data
    context.user_data["tax_category"] = tax_data
    context.user_data["tax_claimable"] = 1 if tax_data.startswith("tax_") and tax_data != "tax_personal" and tax_data != "tax_skip" else 0

    return await confirm_transaction_query(update, context)

async def confirm_transaction_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = context.user_data

    user_id = update.effective_user.id
    trans_type = "income" if data["type"].startswith("income_") else "expense"
    category = data["category"]
    item = data["item"]
    amount = data["amount"]
    tax_cat = data.get("tax_category", "tax_skip")
    tax_claim = data.get("tax_claimable", 0)

    now = datetime.now()
    month = now.strftime("%Y-%m")

    # Save to DB
    conn = sqlite3.connect("budget.db")
    c = conn.cursor()
    c.execute("""
        INSERT INTO transactions 
        (user_id, type, category, item, amount, tax_category, tax_claimable, date, month)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, trans_type, category, item, amount, tax_cat, tax_claim, now.isoformat(), month))
    conn.commit()
    conn.close()

    # Budget check for expenses
    budget_msg = ""
    if trans_type == "expense":
        conn = sqlite3.connect("budget.db")
        c = conn.cursor()
        c.execute("SELECT limit_amount FROM budgets WHERE user_id=? AND category=?", (user_id, category))
        result = c.fetchone()
        conn.close()

        if result:
            budget_limit = result[0]
            # Get total spent this month
            conn = sqlite3.connect("budget.db")
            c = conn.cursor()
            c.execute("""
                SELECT SUM(amount) FROM transactions 
                WHERE user_id=? AND type='expense' AND category=? AND month=?
            """, (user_id, category, month))
            total_spent = c.fetchone()[0] or 0
            conn.close()

            pct = (total_spent / budget_limit) * 100 if budget_limit > 0 else 0
            status = "🟢" if pct < 75 else "🟡" if pct < 90 else "🔴"
            budget_msg = f"\n\n📊 Bajet {category}: {status} RM {total_spent:.0f} / RM {budget_limit:.0f} ({pct:.0f}%)"

    tax_msg = ""
    if tax_claim == 1:
        relief_info = TAX_CATEGORIES["expense_relief"].get(tax_cat.replace("tax_", ""), {})
        limit = relief_info.get("limit", 0)
        if isinstance(limit, int):
            tax_msg = f"\n💼 **Tax Relief:** RM {amount:.0f} (Limit: RM {limit:,})"
        else:
            tax_msg = f"\n💼 **Tax Relief:** RM {amount:.0f} (Limit: 10% income)"
    elif tax_cat == "tax_personal":
        tax_msg = "\n🔴 **Tax:** Personal (tak boleh claim)"

    emoji = "💵" if trans_type == "income" else "💸"
    await query.edit_message_text(
        f"✅ **Recorded!**\n\n"
        f"{emoji} {item}\n"
        f"📁 {category}\n"
        f"💰 RM {amount:,.2f}{tax_msg}{budget_msg}"
    )

    return ConversationHandler.END

async def confirm_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # For income (no tax selection needed)
    data = context.user_data

    user_id = update.effective_user.id
    trans_type = "income"
    category = data["category"]
    item = data["item"]
    amount = data["amount"]

    now = datetime.now()
    month = now.strftime("%Y-%m")

    conn = sqlite3.connect("budget.db")
    c = conn.cursor()
    c.execute("""
        INSERT INTO transactions 
        (user_id, type, category, item, amount, tax_category, tax_claimable, date, month)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, trans_type, category, item, amount, "income", 0, now.isoformat(), month))
    conn.commit()
    conn.close()

    tax_info = data.get("tax_info", {})
    tax_msg = f"\n📊 Tax: {tax_info.get('note', 'N/A')} ({tax_info.get('rate', 'N/A')})"

    await update.message.reply_text(
        f"✅ **Recorded!**\n\n"
        f"💵 {item}\n"
        f"📁 {category.replace('_', ' ').title()}\n"
        f"💰 RM {amount:,.2f}{tax_msg}"
    )

    return ConversationHandler.END

# ============== OTHER COMMANDS ==============

async def baki(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
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

    await update.message.reply_text(
        f"🎯 **BAKI BULAN INI**\n\n"
        f"💵 Masuk: RM {income:,.2f}\n"
        f"💸 Keluar: RM {expense:,.2f}\n"
        f"🎯 Baki: RM {baki:,.2f}\n"
        f"{status}"
    )

async def ringkasan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    month = datetime.now().strftime("%Y-%m")

    conn = sqlite3.connect("budget.db")
    c = conn.cursor()

    # Income by category
    c.execute("""
        SELECT category, SUM(amount) FROM transactions 
        WHERE user_id=? AND type='income' AND month=?
        GROUP BY category
    """, (user_id, month))
    incomes = c.fetchall()

    # Expense by category
    c.execute("""
        SELECT category, SUM(amount) FROM transactions 
        WHERE user_id=? AND type='expense' AND month=?
        GROUP BY category ORDER BY SUM(amount) DESC
    """, (user_id, month))
    expenses = c.fetchall()

    # Total
    c.execute("SELECT SUM(amount) FROM transactions WHERE user_id=? AND type='income' AND month=?", (user_id, month))
    total_income = c.fetchone()[0] or 0
    c.execute("SELECT SUM(amount) FROM transactions WHERE user_id=? AND type='expense' AND month=?", (user_id, month))
    total_expense = c.fetchone()[0] or 0

    conn.close()

    baki = total_income - total_expense

    income_text = "\n".join([f"• {cat.replace('_', ' ').title()}: RM {amt:,.2f}" for cat, amt in incomes]) or "Tiada"
    expense_text = "\n".join([f"• {cat}: RM {amt:,.2f}" for cat, amt in expenses]) or "Tiada"

    # 50/30/20 check
    needs = sum([amt for cat, amt in expenses if cat in ["Rumah", "Utiliti", "Kereta", "Makan", "Anak", "Kesihatan"]])
    wants = sum([amt for cat, amt in expenses if cat == "Lifestyle"])
    save = sum([amt for cat, amt in expenses if cat in ["Simpanan", "Hutang"]])

    needs_pct = (needs / total_income * 100) if total_income > 0 else 0
    wants_pct = (wants / total_income * 100) if total_income > 0 else 0
    save_pct = (save / total_income * 100) if total_income > 0 else 0

    await update.message.reply_text(
        f"📊 **RINGKASAN {month}**\n\n"
        f"💵 **Income:**\n{income_text}\n"
        f"💸 **Expense:**\n{expense_text}\n\n"
        f"📈 **Total:**\n"
        f"Masuk: RM {total_income:,.2f}\n"
        f"Keluar: RM {total_expense:,.2f}\n"
        f"Baki: RM {baki:,.2f}\n\n"
        f"📊 **50/30/20:**\n"
        f"Needs: {needs_pct:.0f}% {'🔴' if needs_pct > 55 else '🟡' if needs_pct > 50 else '🟢'}\n"
        f"Wants: {wants_pct:.0f}% {'🔴' if wants_pct > 35 else '🟡' if wants_pct > 30 else '🟢'}\n"
        f"Save: {save_pct:.0f}% {'🔴' if save_pct < 15 else '🟡' if save_pct < 20 else '🟢'}"
    )

async def bajet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "📊 **Set Bajet**\n\n"
            "Cara guna: /bajet [kategori] [amaun]\n\n"
            "Contoh: /bajet Makan 1000\n"
            "Contoh: /bajet Lifestyle 500"
        )
        return

    category = context.args[0]
    try:
        amount = float(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Amaun mesti nombor. Contoh: /bajet Makan 1000")
        return

    user_id = update.effective_user.id

    conn = sqlite3.connect("budget.db")
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO budgets (user_id, category, limit_amount) VALUES (?, ?, ?)",
              (user_id, category, amount))
    conn.commit()
    conn.close()

    await update.message.reply_text(f"✅ Bajet **{category}** set ke RM {amount:,.2f}")

async def tax_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    year = datetime.now().year

    conn = sqlite3.connect("budget.db")
    c = conn.cursor()

    # Taxable income
    c.execute("""
        SELECT SUM(amount) FROM transactions 
        WHERE user_id=? AND type='income' AND tax_category != 'income_dividen_asb' 
        AND tax_category != 'income_epf_withdrawal'
    """, (user_id,))
    taxable_income = c.fetchone()[0] or 0

    # Tax reliefs
    c.execute("""
        SELECT tax_category, SUM(amount) FROM transactions 
        WHERE user_id=? AND type='expense' AND tax_claimable=1
        GROUP BY tax_category
    """, (user_id,))
    reliefs = c.fetchall()

    conn.close()

    # Calculate tax
    total_relief = 0
    relief_text = ""
    for tax_cat, amt in reliefs:
        cat_key = tax_cat.replace("tax_", "")
        info = TAX_CATEGORIES["expense_relief"].get(cat_key, {})
        limit = info.get("limit", 0)

        if isinstance(limit, float) and limit < 1:  # percentage limit
            claimable = min(amt, taxable_income * limit)
        else:
            claimable = min(amt, limit)

        total_relief += claimable
        relief_text += f"• {cat_key.replace('_', ' ').title()}: RM {claimable:,.0f} / RM {limit:,}\n"

    # Tax calculation
    chargeable = max(0, taxable_income - total_relief)
    tax = 0
    for low, high, rate in TAX_BRACKETS:
        if chargeable > low:
            taxable_at_bracket = min(chargeable, high) - low
            tax += taxable_at_bracket * rate

    # Rebate
    c.execute("SELECT SUM(amount) FROM transactions WHERE user_id=? AND tax_category='tax_zakat_expense'", (user_id,))
    zakat = c.fetchone()[0] or 0
    tax = max(0, tax - zakat)

    await update.message.reply_text(
        f"🧾 **TAX SUMMARY {year}**\n\n"
        f"📊 **Taxable Income:** RM {taxable_income:,.2f}\n"
        f"💰 **Total Relief:** RM {total_relief:,.2f}\n"
        f"📉 **Chargeable Income:** RM {chargeable:,.2f}\n"
        f"💸 **Est. Tax Payable:** RM {tax:,.2f}\n\n"
        f"📋 **Relief Breakdown:**\n{relief_text}\n"
        f"💡 **Tip:** Track lagi relief untuk kurangkan tax!"
    )

async def export_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    conn = sqlite3.connect("budget.db")
    c = conn.cursor()
    c.execute("""
        SELECT type, category, item, amount, tax_category, tax_claimable, date 
        FROM transactions WHERE user_id=? ORDER BY date DESC
    """, (user_id,))
    data = c.fetchall()
    conn.close()

    if not data:
        await update.message.reply_text("📭 Tiada data lagi. Start dengan /masuk atau /keluar")
        return

    # Create CSV
    import csv
    filename = f"/mnt/agents/output/budget_export_{user_id}.csv"
    with open(filename, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["Type", "Category", "Item", "Amount", "Tax Category", "Tax Claimable", "Date"])
        writer.writerows(data)

    await update.message.reply_document(
        document=open(filename, 'rb'),
        caption="📎 **Export data anda**\nBoleh buka dalam Excel/Google Sheets"
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END

# ============== MAIN ==============

def main():
    init_db()

    # Replace with your bot token
    TOKEN = "8604173888:AAFF8fh-qgDGQ2nlvqaJPz1kmb2qkCDv4_g"

    application = Application.builder().token(TOKEN).build()

    # Conversation handler for income/expense
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("masuk", masuk),
            CommandHandler("keluar", keluar),
        ],
        states={
            SELECTING_TYPE: [CallbackQueryHandler(type_selected, pattern="^(income_|exp_|cancel)$")],
            ENTERING_ITEM: [MessageHandler(filters.TEXT & ~filters.COMMAND, item_entered)],
            ENTERING_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, amount_entered)],
            SELECTING_TAX: [CallbackQueryHandler(tax_selected, pattern="^tax_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(CommandHandler("baki", baki))
    application.add_handler(CommandHandler("ringkasan", ringkasan))
    application.add_handler(CommandHandler("bajet", bajet))
    application.add_handler(CommandHandler("tax", tax_summary))
    application.add_handler(CommandHandler("export", export_data))
    application.add_handler(conv_handler)

    application.run_polling()

if __name__ == "__main__":
    main()
