# 💰 Budget Bot Malaysia

Telegram bot untuk track budget + tax relief (LHDN-ready).

## 🚀 Setup

### 1. Create Bot (Telegram)
- Message @BotFather
- /newbot → name your bot
- Copy the token

### 2. Deploy

**Option A: Local Test**
```bash
pip install -r requirements.txt
# Edit bot.py, replace YOUR_BOT_TOKEN_HERE
python bot.py
```

**Option B: Railway/Render (Free)**
1. Push to GitHub
2. Connect Railway/Render
3. Set environment variable: `BOT_TOKEN=your_token`
4. Deploy

**Option C: VPS**
```bash
git clone <repo>
cd budget_bot
pip install -r requirements.txt
export BOT_TOKEN=your_token
nohup python bot.py &
```

## 📱 Commands

| Command | Function |
|---------|----------|
| /start | Start bot |
| /masuk | Record income |
| /keluar | Record expense |
| /baki | Check balance |
| /ringkasan | Monthly summary |
| /bajet | Set budget limit |
| /tax | Tax summary (LHDN) |
| /export | Export CSV |

## 🧾 Tax Features

- Auto-tag tax category
- Track relief limits (Medical RM8k, Education RM7k, etc.)
- Estimate tax payable
- Export for LHDN filing

## 💰 Monetization

Sell bot access:
- Basic: RM 15/month
- Tax Saver: RM 35/month  
- Family: RM 49/month

## 📞 Support

DM @yourhandle for help.
