
import logging
import sqlite3
import os
from datetime import datetime
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

# Setup
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN", "8604173888:AAFF8fh-qgDGQ2nlvqaJPz1kmb2qkCDv4_g")

# DB
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

# Tax data
TAX_INCOME = {
    "gaji": {"taxable": True, "note": "EA Form", "rate": "Progressive"},
    "side_hustle": {"taxable": True, "note": "Business", "rate": "Progressive"},
    "dividen_asb": {"taxable": False, "note": "Exempt", "rate": "0%"},
    "dividen_saham": {"taxable": True, "note": "Withholding 8%", "rate": "8%"},
    "rental": {"taxable": True, "note": "Rental", "rate": "Progressive"},
    "freelance": {"taxable": True, "note": "Business", "rate": "Progressive"},
    "epf": {"taxable": False, "note": "Exempt", "rate": "0%"},
    "zakat": {"taxable": False, "note": "Rebate", "rate": "Rebate"},
}

TAX_RELIEF = {
    "medical_parents": {"limit": 8000, "cat": "Medical"},
    "medical_self": {"limit": 8000, "cat": "Medical"},
    "education": {"limit": 7000, "cat": "Education"},
    "sports": {"limit": 1000, "cat": "Lifestyle"},
    "lifestyle": {"limit": 2500, "cat": "Lifestyle"},
    "breastfeeding": {"limit": 1000, "cat": "Child"},
    "childcare": {"limit": 3000, "cat": "Child"},
    "sspn": {"limit": 8000, "cat": "Education"},
    "prs": {"limit": 3000, "cat": "Retirement"},
    "life_insurance": {"limit": 3000, "cat": "Insurance"},
    "medical_insurance": {"limit": 3000, "cat": "Insurance"},
    "epf_self": {"limit": 4000, "cat": "Retirement"},
    "socso": {"limit": 350, "cat": "Social"},
    "zakat_exp": {"limit": 999999, "cat": "Rebate"},
    "donation": {"limit": 0.1, "cat": "Donation"},
}

TAX_BRACKETS = [
    (0, 5000, 0), (5000, 20000, 0.01), (20000, 35000, 0.03),
    (35000, 50000, 0.06), (50000, 70000, 0.11), (70000, 100000, 0.19),
    (100000, 400000, 0.25), (400000, 1000000, 0.26), (1000000, 999999999, 0.28),
]

BUDGET_CATS = ["Rumah", "Utiliti", "Kereta", "Makan", "Anak", "Kesihatan", "Hutang", "Simpanan", "Lifestyle"]

INCOME_TYPES = ["gaji", "side_hustle", "dividen_asb", "dividen_saham", "rental", "freelance", "epf", "zakat"]

# ============== COMMANDS ==============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"""💰 **BUDGET BOT MALAYSIA**

Hai {user.first_name}!

**Quick Commands:**
/income — Record income
/expense — Record expense  
/balance — Check balance
/summary — Monthly summary
/budget — Set budget
/tax — Tax summary
/export — Export data

**Format:**
/income gaji 5500 Gaji_Mei
/expense Makan 35 GrabFood personal
/expense Kesihatan 200 Panel medical_self

Type /help for full guide!""",
        parse_mode="Markdown"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        """📚 **FULL GUIDE**

**Income:**
/income [type] [amount] [name]
Types: gaji, side_hustle, dividen_asb, dividen_saham, rental, freelance, epf, zakat

**Expense:**
/expense [category] [amount] [name] [tax_tag]
Categories: Rumah, Utiliti, Kereta, Makan, Anak, Kesihatan, Hutang, Simpanan, Lifestyle

**Tax Tags (for expense):**
personal — Tak claim
medical_parents — Medical parents (RM8k)
medical_self — Medical self (RM8k)
education — Education (RM7k)
insurance — Insurance (RM3k)
childcare — Childcare (RM3k)
lifestyle — Lifestyle (RM2.5k)
sports — Sports (RM1k)
sspn — SSPN (RM8k)
prs — PRS (RM3k)
zakat_exp — Zakat (Rebate)
donation — Donation (10% income)

**Examples:**
/income gaji 5500 Gaji_Mei
/expense Makan 35 GrabFood personal
/expense Kesihatan 200 Panel medical_self
/expense Simpanan 500 ASB sspn

**Other:**
/balance — Check baki
/summary — Monthly ringkasan
/budget Makan 1000 — Set bajet
/tax — Tax estimate
/export — Export CSV""",
        parse_mode="Markdown"
    )

async def income(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args

    if len(args) < 3:
        await update.message.reply_text(
            "❌ Format: /income [type] [amount] [name]\n\n"
            "Contoh: /income gaji 5500 Gaji_Mei\n"
            "Types: gaji, side_hustle, dividen_asb, dividen_saham, rental, freelance, epf, zakat"
        )
        return

    inc_type = args[0].lower()
    try:
        amount = float(args[1])
    except ValueError:
        await update.message.reply_text("❌ Amaun mesti nombor. Contoh: 5500")
        return

    name = "_".join(args[2:])

    if inc_type not in INCOME_TYPES:
        await update.message.reply_text(f"❌ Type tak sah. Pilih: {', '.join(INCOME_TYPES)}")
        return

    tax_info = TAX_INCOME.get(inc_type, {})
    now = datetime.now()
    month = now.strftime("%Y-%m")

    conn = sqlite3.connect("budget.db")
    c = conn.cursor()
    c.execute("""
        INSERT INTO transactions (user_id, type, category, item, amount, tax_category, tax_claimable, date, month)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, "income", inc_type, name, amount, inc_type, 0, now.isoformat(), month))
    conn.commit()
    conn.close()

    tax_msg = f"\n📊 Tax: {tax_info.get('note', 'N/A')} ({tax_info.get('rate', 'N/A')})"

    await update.message.reply_text(
        f"✅ **Income Recorded!**\n\n"
        f"💵 {name.replace('_', ' ')}\n"
        f"📁 {inc_type.replace('_', ' ').title()}\n"
        f"💰 RM {amount:,.2f}{tax_msg}"
    )

async def expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args

    if len(args) < 4:
        await update.message.reply_text(
            "❌ Format: /expense [category] [amount] [name] [tax_tag]\n\n"
            "Contoh: /expense Makan 35 GrabFood personal\n"
            "Categories: Rumah, Utiliti, Kereta, Makan, Anak, Kesihatan, Hutang, Simpanan, Lifestyle\n\n"
            "Tax tags: personal, medical_parents, medical_self, education, insurance, childcare, lifestyle, sports, sspn, prs, zakat_exp, donation"
        )
        return

    category = args[0].capitalize()
    try:
        amount = float(args[1])
    except ValueError:
        await update.message.reply_text("❌ Amaun mesti nombor. Contoh: 35")
        return

    name = "_".join(args[2:-1])
    tax_tag = args[-1].lower()

    if category not in BUDGET_CATS:
        await update.message.reply_text(f"❌ Kategori tak sah. Pilih: {', '.join(BUDGET_CATS)}")
        return

    tax_claimable = 0 if tax_tag == "personal" else 1

    now = datetime.now()
    month = now.strftime("%Y-%m")

    conn = sqlite3.connect("budget.db")
    c = conn.cursor()
    c.execute("""
        INSERT INTO transactions (user_id, type, category, item, amount, tax_category, tax_claimable, date, month)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, "expense", category, name, amount, tax_tag, tax_claimable, now.isoformat(), month))
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

    tax_msg = ""
    if tax_claimable == 1:
        relief = TAX_RELIEF.get(tax_tag, {})
        limit = relief.get("limit", 0)
        if isinstance(limit, int):
            tax_msg = f"\n💼 **Tax Relief:** RM {amount:.0f} (Limit: RM {limit:,})"
        else:
            tax_msg = f"\n💼 **Tax Relief:** RM {amount:.0f} (Limit: 10% income)"
    else:
        tax_msg = "\n🔴 **Tax:** Personal (tak boleh claim)"

    await update.message.reply_text(
        f"✅ **Expense Recorded!**\n\n"
        f"💸 {name.replace('_', ' ')}\n"
        f"📁 {category}\n"
        f"💰 RM {amount:,.2f}{tax_msg}{budget_msg}"
    )

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    month = datetime.now().strftime("%Y-%m")

    conn = sqlite3.connect("budget.db")
    c = conn.cursor()

    c.execute("SELECT category, SUM(amount) FROM transactions WHERE user_id=? AND type='income' AND month=? GROUP BY category", (user_id, month))
    incomes = c.fetchall()

    c.execute("SELECT category, SUM(amount) FROM transactions WHERE user_id=? AND type='expense' AND month=? GROUP BY category ORDER BY SUM(amount) DESC", (user_id, month))
    expenses = c.fetchall()

    c.execute("SELECT SUM(amount) FROM transactions WHERE user_id=? AND type='income' AND month=?", (user_id, month))
    total_income = c.fetchone()[0] or 0
    c.execute("SELECT SUM(amount) FROM transactions WHERE user_id=? AND type='expense' AND month=?", (user_id, month))
    total_expense = c.fetchone()[0] or 0

    conn.close()

    baki = total_income - total_expense

    inc_text = "\n".join([f"• {cat.replace('_', ' ').title()}: RM {amt:,.2f}" for cat, amt in incomes]) or "Tiada"
    exp_text = "\n".join([f"• {cat}: RM {amt:,.2f}" for cat, amt in expenses]) or "Tiada"

    needs = sum([amt for cat, amt in expenses if cat in ["Rumah", "Utiliti", "Kereta", "Makan", "Anak", "Kesihatan"]])
    wants = sum([amt for cat, amt in expenses if cat == "Lifestyle"])
    save = sum([amt for cat, amt in expenses if cat in ["Simpanan", "Hutang"]])

    needs_pct = (needs / total_income * 100) if total_income > 0 else 0
    wants_pct = (wants / total_income * 100) if total_income > 0 else 0
    save_pct = (save / total_income * 100) if total_income > 0 else 0

    await update.message.reply_text(
        f"📊 **RINGKASAN {month}**\n\n"
        f"💵 **Income:**\n{inc_text}\n\n"
        f"💸 **Expense:**\n{exp_text}\n\n"
        f"📈 **Total:**\n"
        f"Masuk: RM {total_income:,.2f}\n"
        f"Keluar: RM {total_expense:,.2f}\n"
        f"Baki: RM {baki:,.2f}\n\n"
        f"📊 **50/30/20:**\n"
        f"Needs: {needs_pct:.0f}% {'🔴' if needs_pct > 55 else '🟡' if needs_pct > 50 else '🟢'}\n"
        f"Wants: {wants_pct:.0f}% {'🔴' if wants_pct > 35 else '🟡' if wants_pct > 30 else '🟢'}\n"
        f"Save: {save_pct:.0f}% {'🔴' if save_pct < 15 else '🟡' if save_pct < 20 else '🟢'}"
    )

async def budget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text(
            "📊 **Set Bajet**\n\n"
            "Format: /budget [category] [amount]\n"
            "Contoh: /budget Makan 1000"
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

    await update.message.reply_text(f"✅ Bajet **{category}** set ke RM {amount:,.2f}")

async def tax_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    year = datetime.now().year

    conn = sqlite3.connect("budget.db")
    c = conn.cursor()

    c.execute("SELECT SUM(amount) FROM transactions WHERE user_id=? AND type='income' AND tax_category NOT IN ('dividen_asb', 'epf')", (user_id,))
    taxable_income = c.fetchone()[0] or 0

    c.execute("SELECT tax_category, SUM(amount) FROM transactions WHERE user_id=? AND type='expense' AND tax_claimable=1 GROUP BY tax_category", (user_id,))
    reliefs = c.fetchall()

    c.execute("SELECT SUM(amount) FROM transactions WHERE user_id=? AND tax_category='zakat_exp'", (user_id,))
    zakat = c.fetchone()[0] or 0

    conn.close()

    total_relief = 0
    relief_text = ""
    for tax_cat, amt in reliefs:
        cat_key = tax_cat
        info = TAX_RELIEF.get(cat_key, {})
        limit = info.get("limit", 0)

        if isinstance(limit, float) and limit < 1:
            claimable = min(amt, taxable_income * limit)
        else:
            claimable = min(amt, limit)

        total_relief += claimable
        relief_text += f"• {cat_key.replace('_', ' ').title()}: RM {claimable:,.0f} / RM {limit:,}\n"

    chargeable = max(0, taxable_income - total_relief)
    tax = 0
    for low, high, rate in TAX_BRACKETS:
        if chargeable > low:
            taxable_at_bracket = min(chargeable, high) - low
            tax += taxable_at_bracket * rate

    tax = max(0, tax - zakat)

    await update.message.reply_text(
        f"🧾 **TAX SUMMARY {year}**\n\n"
        f"📊 **Taxable Income:** RM {taxable_income:,.2f}\n"
        f"💰 **Total Relief:** RM {total_relief:,.2f}\n"
        f"📉 **Chargeable:** RM {chargeable:,.2f}\n"
        f"💸 **Est. Tax:** RM {tax:,.2f}\n\n"
        f"📋 **Relief Breakdown:**\n{relief_text}\n"
        f"💡 **Tip:** Track lagi relief untuk kurangkan tax!"
    )

async def export_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    conn = sqlite3.connect("budget.db")
    c = conn.cursor()
    c.execute("SELECT type, category, item, amount, tax_category, tax_claimable, date FROM transactions WHERE user_id=? ORDER BY date DESC", (user_id,))
    data = c.fetchall()
    conn.close()

    if not data:
        await update.message.reply_text("📭 Tiada data lagi. Start dengan /income atau /expense")
        return

    import csv
    filename = f"/tmp/budget_export_{user_id}.csv"
    with open(filename, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["Type", "Category", "Item", "Amount", "Tax Category", "Tax Claimable", "Date"])
        writer.writerows(data)

    await update.message.reply_document(
        document=open(filename, 'rb'),
        caption="📎 **Export data anda**"
    )

# ============== MAIN ==============

def main():
    init_db()

    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(CommandHandler("income", income))
    application.add_handler(CommandHandler("expense", expense))
    application.add_handler(CommandHandler("balance", balance))
    application.add_handler(CommandHandler("summary", summary))
    application.add_handler(CommandHandler("budget", budget))
    application.add_handler(CommandHandler("tax", tax_summary))
    application.add_handler(CommandHandler("export", export_data))

    application.run_polling()

if __name__ == "__main__":
    main()
