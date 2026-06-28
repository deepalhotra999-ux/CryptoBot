import time, requests, math, logging, json, os
from datetime import datetime

# ─────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────
TOKEN     = "8628489665:AAF2-cmo6fYVA2YfYCWyZqGSSXH9dJoQhsE"
CHAT      = 508265847        # your private chat — for commands
CHANNEL   = -1004477081712   # your public channel — for signals
CHECK     = 3600
PAPER_BAL = 50.0
RISK_PCT  = 0.05       # 5% per trade max (was 15% — too aggressive)
MAX_OPEN  = 5          # max 5 trades open at once
SL_PCT    = 0.025
TP1_PCT   = 0.025
TP2_PCT   = 0.045
TP3_PCT   = 0.075

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
    handlers=[logging.FileHandler("bot.log"), logging.StreamHandler()])
log = logging.getLogger(__name__)

# ─────────────────────────────────────────
#  GLOBAL STATE — shared across all functions
# ─────────────────────────────────────────
STATE = {
    "balance": PAPER_BAL,
    "open_trades": {},      # coin_id -> trade dict
    "closed_trades": [],
    "total_pnl": 0.0,
    "wins": 0,
    "losses": 0,
    "scan_count": 0,
    "signals_total": 0,
    "start_time": datetime.now().strftime("%b %d %H:%M"),
}
FIRED = set()
LAST_UPDATE_ID = 0

# ─────────────────────────────────────────
#  COINS
# ─────────────────────────────────────────
COINS = [
    ("bitcoin","BTC/USDT"),("ethereum","ETH/USDT"),("solana","SOL/USDT"),
    ("binancecoin","BNB/USDT"),("ripple","XRP/USDT"),("dogecoin","DOGE/USDT"),
    ("cardano","ADA/USDT"),("avalanche-2","AVAX/USDT"),("chainlink","LINK/USDT"),
    ("polkadot","DOT/USDT"),("near","NEAR/USDT"),("uniswap","UNI/USDT"),
    ("litecoin","LTC/USDT"),("cosmos","ATOM/USDT"),("aptos","APT/USDT"),
    ("sui","SUI/USDT"),("arbitrum","ARB/USDT"),("optimism","OP/USDT"),
    ("injective-protocol","INJ/USDT"),("render-token","RENDER/USDT"),
    ("aave","AAVE/USDT"),("maker","MKR/USDT"),("pepe","PEPE/USDT"),
    ("shiba-inu","SHIB/USDT"),("tron","TRX/USDT"),("stellar","XLM/USDT"),
    ("filecoin","FIL/USDT"),("hedera","HBAR/USDT"),("fantom","FTM/USDT"),
    ("the-sandbox","SAND/USDT"),("decentraland","MANA/USDT"),("stacks","STX/USDT"),
    ("curve-dao-token","CRV/USDT"),("gala","GALA/USDT"),("vechain","VET/USDT"),
    ("internet-computer","ICP/USDT"),("the-graph","GRT/USDT"),
    ("algorand","ALGO/USDT"),("theta-token","THETA/USDT"),("tezos","XTZ/USDT"),
    ("monero","XMR/USDT"),("zcash","ZEC/USDT"),("1inch","1INCH/USDT"),
    ("ocean-protocol","OCEAN/USDT"),("band-protocol","BAND/USDT"),
    ("lido-dao","LDO/USDT"),("compound-governance-token","COMP/USDT"),
    ("synthetix-network-token","SNX/USDT"),("axie-infinity","AXS/USDT"),
    ("enjincoin","ENJ/USDT"),("sei-network","SEI/USDT"),("celestia","TIA/USDT"),
    ("dydx","DYDX/USDT"),("gmx","GMX/USDT"),("pendle","PENDLE/USDT"),
    ("ethena","ENA/USDT"),("bonk","BONK/USDT"),("dogwifcoin","WIF/USDT"),
    ("floki","FLOKI/USDT"),("kaspa","KAS/USDT"),("immutable-x","IMX/USDT"),
    ("ronin","RON/USDT"),("stepn","GMT/USDT"),("blur","BLUR/USDT"),
    ("fetch-ai","FET/USDT"),("singularitynet","AGIX/USDT"),
    ("helium","HNT/USDT"),("akash-network","AKT/USDT"),("arweave","AR/USDT"),
    ("terra-luna-2","LUNA/USDT"),("oasis-network","ROSE/USDT"),
    ("harmony","ONE/USDT"),("eos","EOS/USDT"),("neo","NEO/USDT"),
    ("waves","WAVES/USDT"),("ankr","ANKR/USDT"),("loopring","LRC/USDT"),
    ("celo","CELO/USDT"),("uma","UMA/USDT"),("balancer","BAL/USDT"),
    ("kyber-network","KNC/USDT"),("woo-network","WOO/USDT"),
    ("moonbeam","GLMR/USDT"),("skale","SKL/USDT"),("storj","STORJ/USDT"),
    ("request-network","REQ/USDT"),("civic","CVC/USDT"),
    ("quant-network","QNT/USDT"),("origintrail","TRAC/USDT"),
    ("power-ledger","POWR/USDT"),("nervos-network","CKB/USDT"),
    ("conflux-token","CFX/USDT"),("icon","ICX/USDT"),("ontology","ONT/USDT"),
    ("iotex","IOTX/USDT"),("ravencoin","RVN/USDT"),("horizen","ZEN/USDT"),
    ("band-protocol","BAND/USDT"),("numeraire","NMR/USDT"),
]

# ─────────────────────────────────────────
#  TELEGRAM
# ─────────────────────────────────────────
def tg(msg, target=None):
    """Send message. target=None sends to private chat. target=CHANNEL sends to channel."""
    chat_id = target if target else CHAT
    try:
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"}, timeout=10)
    except Exception as e:
        log.error(f"TG: {e}")

def tg_channel(msg):
    """Post to public channel."""
    tg(msg, target=CHANNEL)

def tg_both(msg):
    """Post to both channel and private chat."""
    tg(msg, target=CHANNEL)
    time.sleep(0.5)
    tg(msg, target=CHAT)

# ─────────────────────────────────────────
#  COINGECKO WITH RETRY
# ─────────────────────────────────────────
def cg_get(url, params, retries=3):
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=20)
            if r.status_code == 200:
                return r.json()
            elif r.status_code == 429:
                wait = 60 * (attempt + 1)
                log.warning(f"Rate limit — waiting {wait}s")
                time.sleep(wait)
            elif r.status_code == 404:
                return None
            else:
                time.sleep(10)
        except:
            time.sleep(5)
    return None

def get_ohlc(coin_id):
    d = cg_get(f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc",
               {"vs_currency": "usd", "days": 14})
    return d if d and len(d) >= 30 else None

def get_price(coin_id):
    d = cg_get("https://api.coingecko.com/api/v3/simple/price",
               {"ids": coin_id, "vs_currencies": "usd", "include_24hr_change": "true"})
    if d and coin_id in d:
        return d[coin_id].get("usd", 0), d[coin_id].get("usd_24h_change", 0)
    return 0, 0

# ─────────────────────────────────────────
#  INDICATORS
# ─────────────────────────────────────────
def ema(prices, n):
    k = 2/(n+1); e = [prices[0]]
    for p in prices[1:]: e.append(p*k + e[-1]*(1-k))
    return e

def rsi(prices, n=14):
    g = [max(prices[i]-prices[i-1], 0) for i in range(1, len(prices))]
    l = [max(prices[i-1]-prices[i], 0) for i in range(1, len(prices))]
    if len(g) < n: return 50
    ag = sum(g[-n:])/n; al = sum(l[-n:])/n
    return 100 if al == 0 else 100-(100/(1+ag/al))

def atr(highs, lows, closes, n=14):
    trs = [max(highs[i]-lows[i], abs(highs[i]-closes[i-1]),
               abs(lows[i]-closes[i-1])) for i in range(1, len(closes))]
    return sum(trs[-n:])/n if len(trs) >= n else 0

def rejection_candle(o, h, l, c):
    body = abs(c-o)
    if body == 0: return False, False
    lw = min(o,c)-l; uw = h-max(o,c)
    return lw >= 2*body and c > o, uw >= 2*body and c < o

def swing_levels(highs, lows, lb=12):
    sh = max(highs[-lb:]); sl = min(lows[-lb:])
    psh = max(highs[-lb*2:-lb]) if len(highs) >= lb*2 else sh
    psl = min(lows[-lb*2:-lb])  if len(lows)  >= lb*2 else sl
    return sh, sl, psh, psl

# ─────────────────────────────────────────
#  LIQUIDITY GRAB DETECTION
# ─────────────────────────────────────────
def detect_grab(opens, highs, lows, closes):
    if len(closes) < 30: return None, 0, [], 0, 0, 0, 0
    o,h,l,c = opens[-1],highs[-1],lows[-1],closes[-1]
    vols = [(hi-lo)*cl for hi,lo,cl in zip(highs,lows,closes)]
    avg_vol = sum(vols[-11:-1])/10 if len(vols) > 10 else 1
    vol_spike = vols[-1] > avg_vol * 1.3
    sh, sl, psh, psl = swing_levels(highs[:-1], lows[:-1])
    bull_rej, bear_rej = rejection_candle(o,h,l,c)
    e21 = ema(closes,21); e50 = ema(closes,50)
    rsi_val = rsi(closes); atr_val = atr(highs,lows,closes)

    bs=0; bt=[]
    if l < sl and c > sl:             bs+=3; bt.append(f"Liq grab below {fmt(sl)}")
    if bull_rej:                       bs+=2; bt.append("Bullish pin bar")
    if vol_spike:                      bs+=1; bt.append("Volume spike")
    if rsi_val < 65:                   bs+=1; bt.append(f"RSI {rsi_val:.0f}")
    if c > e21[-1]*0.995:              bs+=1; bt.append("EMA21 support")
    if abs(l-psl)/max(psl,1) < 0.015: bs+=1; bt.append("Double bottom")

    ss=0; st=[]
    if h > sh and c < sh:             ss+=3; st.append(f"Liq grab above {fmt(sh)}")
    if bear_rej:                       ss+=2; st.append("Bearish pin bar")
    if vol_spike:                      ss+=1; st.append("Volume spike")
    if rsi_val > 35:                   ss+=1; st.append(f"RSI {rsi_val:.0f}")
    if c < e21[-1]*1.005:              ss+=1; st.append("EMA21 resistance")
    if abs(h-psh)/max(psh,1) < 0.015: ss+=1; st.append("Double top")

    if bs >= 4 and bs > ss: return "LONG",  bs, bt, rsi_val, atr_val, sl, sh
    if ss >= 4 and ss > bs: return "SHORT", ss, st, rsi_val, atr_val, sl, sh
    return None, 0, [], rsi_val, atr_val, sl, sh

# ─────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────
def fmt(v):
    if v >= 1000:    return f"{v:,.2f}"
    elif v >= 1:     return f"{v:.4f}"
    elif v >= 0.01:  return f"{v:.6f}"
    else:            return f"{v:.8f}"

def conf(score): return min(round(55+(score/8)*42, 1), 97.5)

def bar(pct, width=10):
    filled = int(abs(pct)/10 * width)
    filled = min(filled, width)
    return "█"*filled + "░"*(width-filled)

# ─────────────────────────────────────────
#  OPEN TRADE
# ─────────────────────────────────────────
def open_trade(coin_id, pair, direction, price, score, tags, sl_lvl, sh_lvl):
    if len(STATE["open_trades"]) >= MAX_OPEN:
        log.info(f"Max open trades reached — skipping {pair}")
        return None
    bal = STATE["balance"]
    size = round(bal * RISK_PCT, 4)
    if size < 0.5: return None
    p = price
    if direction == "LONG":
        sl  = round(min(p*(1-SL_PCT), sl_lvl*0.995), 8)
        tp1 = round(p*(1+TP1_PCT), 8)
        tp2 = round(p*(1+TP2_PCT), 8)
        tp3 = round(p*(1+TP3_PCT), 8)
    else:
        sl  = round(max(p*(1+SL_PCT), sh_lvl*1.005), 8)
        tp1 = round(p*(1-TP1_PCT), 8)
        tp2 = round(p*(1-TP2_PCT), 8)
        tp3 = round(p*(1-TP3_PCT), 8)
    STATE["open_trades"][coin_id] = {
        "pair": pair, "direction": direction,
        "entry": p, "size": size,
        "sl": sl, "tp1": tp1, "tp2": tp2, "tp3": tp3,
        "tph": 0, "score": score,
        "tags": tags[:2],
        "opened": datetime.now().strftime("%b %d %H:%M"),
        "coin_id": coin_id,
    }
    STATE["balance"] = round(bal - size, 4)
    STATE["signals_total"] += 1
    log.info(f"Trade opened: {direction} {pair} @ {p} size=${size}")
    return sl, tp1, tp2, tp3

# ─────────────────────────────────────────
#  CHECK EXITS
# ─────────────────────────────────────────
def check_exits():
    to_close = []
    for coin_id, t in list(STATE["open_trades"].items()):
        price, _ = get_price(coin_id)
        if price == 0: continue
        il = t["direction"] == "LONG"
        hit_sl = (price <= t["sl"]) if il else (price >= t["sl"])
        nth = t["tph"]
        for i, tp in enumerate([t["tp1"],t["tp2"],t["tp3"]]):
            if il and price >= tp and i >= t["tph"]: nth = i+1
            elif not il and price <= tp and i >= t["tph"]: nth = i+1

        if nth > t["tph"]:
            STATE["open_trades"][coin_id]["tph"] = nth
            pct = [TP1_PCT, TP2_PCT, TP3_PCT][nth-1]
            profit = round(t["size"]*pct*(1 if il else -1), 4)
            roi = round(pct*100, 2)
            tg_both(
                f"✅ <b>TP{nth} HIT!</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📌 <b>{t['pair']}</b> {t['direction']}\n"
                f"📥 Entry: {fmt(t['entry'])}\n"
                f"📤 Exit:  {fmt(price)}\n"
                f"📈 ROI: <b>+{roi}%</b>\n"
                f"💰 Profit: <b>+${profit}</b>\n\n"
                f"{'🏆 All 3 TPs hit! Close the trade!' if nth==3 else f'🛡 Move SL to breakeven! TP{nth+1} next target.'}\n"
                f"Congratulations! 🎉"
            )
            if nth == 3:
                final = round(t["size"]*TP3_PCT*(1 if il else -1), 4)
                STATE["balance"] = round(STATE["balance"]+t["size"]+final, 4)
                STATE["total_pnl"] = round(STATE["total_pnl"]+final, 4)
                STATE["wins"] += 1
                STATE["closed_trades"].append({
                    "pair": t["pair"], "direction": t["direction"],
                    "entry": t["entry"], "exit": price,
                    "pnl": final, "roi": round(TP3_PCT*100,2),
                    "result": "TP3", "size": t["size"],
                    "opened": t["opened"],
                    "closed": datetime.now().strftime("%b %d %H:%M")
                })
                to_close.append(coin_id)

        if hit_sl and coin_id not in to_close:
            loss = round(t["size"]*SL_PCT, 4)
            STATE["balance"] = round(STATE["balance"]+t["size"]-loss, 4)
            STATE["total_pnl"] = round(STATE["total_pnl"]-loss, 4)
            STATE["losses"] += 1
            STATE["closed_trades"].append({
                "pair": t["pair"], "direction": t["direction"],
                "entry": t["entry"], "exit": price,
                "pnl": -loss, "roi": -round(SL_PCT*100,2),
                "result": "SL", "size": t["size"],
                "opened": t["opened"],
                "closed": datetime.now().strftime("%b %d %H:%M")
            })
            tg_both(
                f"❌ <b>STOP LOSS HIT</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📌 <b>{t['pair']}</b> {t['direction']}\n"
                f"📥 Entry: {fmt(t['entry'])}\n"
                f"📤 Exit:  {fmt(price)}\n"
                f"📉 ROI: <b>-{round(SL_PCT*100,2)}%</b>\n"
                f"💸 Loss: <b>-${loss}</b>\n"
                f"💼 Balance: <b>${STATE['balance']:.4f}</b>"
            )
            to_close.append(coin_id)
        time.sleep(1.5)

    for c in to_close:
        if c in STATE["open_trades"]:
            del STATE["open_trades"][c]

# ─────────────────────────────────────────
#  TELEGRAM COMMANDS
# ─────────────────────────────────────────
def get_updates():
    global LAST_UPDATE_ID
    try:
        r = requests.get(f"https://api.telegram.org/bot{TOKEN}/getUpdates",
            params={"offset": LAST_UPDATE_ID+1, "timeout": 2}, timeout=8)
        if r.status_code == 200:
            updates = r.json().get("result", [])
            if updates: LAST_UPDATE_ID = updates[-1]["update_id"]
            return updates
    except: pass
    return []

def handle_commands():
    for u in get_updates():
        msg = u.get("message", {})
        text = msg.get("text", "").strip().lower()
        cid = msg.get("chat", {}).get("id")
        if cid != CHAT: continue
        if text in ["/balance", "/bal"]:         cmd_balance()
        elif text in ["/trades", "/open"]:        cmd_trades()
        elif text in ["/closed", "/history"]:     cmd_closed()
        elif text in ["/stats"]:                  cmd_stats()
        elif text in ["/portfolio", "/p"]:        cmd_portfolio()
        elif text in ["/help", "/start"]:         cmd_help()
        elif text.startswith("/trade "):
            pair = text.replace("/trade ","").upper().strip()
            cmd_single_trade(pair)

def cmd_help():
    tg(
        "🤖 <b>BOT COMMANDS</b>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "/balance — Balance & growth\n"
        "/trades — All open trades with live PnL\n"
        "/trade BTC — Check specific trade (e.g. /trade ETH)\n"
        "/closed — Last 10 closed trades\n"
        "/stats — Win rate & performance\n"
        "/portfolio — Full report\n"
        "/help — This menu"
    )

def cmd_balance():
    bal = STATE["balance"]
    pnl = STATE["total_pnl"]
    growth = round((bal-PAPER_BAL)/PAPER_BAL*100, 2)
    em = "📈" if growth >= 0 else "📉"
    tg(
        f"💼 <b>BALANCE</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"💵 Available: <b>${bal:.4f}</b>\n"
        f"🚀 Started:   <b>${PAPER_BAL:.2f}</b>\n"
        f"{em} Growth: <b>{growth:+.2f}%</b>\n"
        f"{bar(growth)} {growth:+.2f}%\n"
        f"💰 Realized PnL: <b>${pnl:+.4f}</b>\n"
        f"🔄 Open Trades: <b>{len(STATE['open_trades'])}/{MAX_OPEN}</b>\n"
        f"⏰ {datetime.now().strftime('%H:%M:%S')}"
    )

def cmd_trades():
    open_t = STATE["open_trades"]
    if not open_t:
        tg("🔄 <b>No open trades right now.</b>\nBot is scanning for setups...")
        return
    lines = f"🔄 <b>OPEN TRADES ({len(open_t)}/{MAX_OPEN})</b>\n━━━━━━━━━━━━━━━━━━━\n"
    total_upnl = 0.0
    for cid, t in open_t.items():
        price, _ = get_price(cid)
        time.sleep(1.2)
        if price > 0:
            if t["direction"] == "LONG":
                upnl = round((price-t["entry"])/t["entry"]*t["size"], 4)
                roi  = round((price-t["entry"])/t["entry"]*100, 2)
            else:
                upnl = round((t["entry"]-price)/t["entry"]*t["size"], 4)
                roi  = round((t["entry"]-price)/t["entry"]*100, 2)
            total_upnl += upnl
            em = "📈" if upnl >= 0 else "📉"
            arrow = "🟢" if t["direction"]=="LONG" else "🔴"
            tph = t.get("tph", 0)
            tp_status = f"✅TP{tph} hit — move SL!" if tph > 0 else "⏳ Waiting for TP1"
            dist_tp1 = round((t["tp1"]-price)/price*100, 2) if t["direction"]=="LONG" else round((price-t["tp1"])/price*100, 2)
            lines += (
                f"\n{arrow} <b>{t['pair']}</b> {t['direction']}\n"
                f"   📥 Entry: {fmt(t['entry'])}\n"
                f"   💹 Now:   {fmt(price)}\n"
                f"   {em} uPnL: <b>${upnl:+.4f} ({roi:+.2f}%)</b>\n"
                f"   🎯 TP1: {fmt(t['tp1'])} ({dist_tp1:+.2f}% away)\n"
                f"   🛡 SL:  {fmt(t['sl'])}\n"
                f"   💼 Size: ${t['size']:.2f} | {tp_status}\n"
                f"   📅 Opened: {t['opened']}\n"
            )
    lines += f"\n━━━━━━━━━━━━━━━━━━━\n💰 Total uPnL: <b>${total_upnl:+.4f}</b>"
    tg(lines)

def cmd_single_trade(pair_search):
    found = False
    for cid, t in STATE["open_trades"].items():
        if pair_search in t["pair"].upper():
            price, _ = get_price(cid)
            if t["direction"] == "LONG":
                upnl = round((price-t["entry"])/t["entry"]*t["size"], 4)
                roi  = round((price-t["entry"])/t["entry"]*100, 2)
                dist_tp1 = round((t["tp1"]-price)/price*100, 2)
                dist_tp2 = round((t["tp2"]-price)/price*100, 2)
                dist_tp3 = round((t["tp3"]-price)/price*100, 2)
            else:
                upnl = round((t["entry"]-price)/t["entry"]*t["size"], 4)
                roi  = round((t["entry"]-price)/t["entry"]*100, 2)
                dist_tp1 = round((price-t["tp1"])/price*100, 2)
                dist_tp2 = round((price-t["tp2"])/price*100, 2)
                dist_tp3 = round((price-t["tp3"])/price*100, 2)
            em = "📈" if upnl >= 0 else "📉"
            arrow = "🟢" if t["direction"]=="LONG" else "🔴"
            tg(
                f"{arrow} <b>{t['pair']} — LIVE TRADE</b>\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"Direction: <b>{t['direction']}</b>\n"
                f"📥 Entry:  {fmt(t['entry'])}\n"
                f"💹 Current: {fmt(price)}\n"
                f"{em} uPnL: <b>${upnl:+.4f} ({roi:+.2f}%)</b>\n\n"
                f"🎯 TP1: {fmt(t['tp1'])} ({dist_tp1:+.2f}% away)\n"
                f"🎯 TP2: {fmt(t['tp2'])} ({dist_tp2:+.2f}% away)\n"
                f"🎯 TP3: {fmt(t['tp3'])} ({dist_tp3:+.2f}% away)\n"
                f"🛡 SL:  {fmt(t['sl'])}\n\n"
                f"✅ TPs Hit: {t.get('tph',0)}/3\n"
                f"💼 Size: ${t['size']:.2f}\n"
                f"📅 Opened: {t['opened']}\n"
                f"🧠 Confidence: {conf(t['score'])}%"
            )
            found = True
            break
    if not found:
        tg(f"❌ No open trade found for <b>{pair_search}</b>\nUse /trades to see all open trades.")

def cmd_closed():
    closed = STATE["closed_trades"]
    if not closed:
        tg("📋 <b>No closed trades yet.</b>")
        return
    recent = closed[-10:]
    wins = sum(1 for t in recent if t["result"] != "SL")
    total_pnl = sum(t["pnl"] for t in recent)
    lines = f"📋 <b>LAST {len(recent)} CLOSED TRADES</b>\n━━━━━━━━━━━━━━━━━━━\n"
    for ct in reversed(recent):
        em = "✅" if ct["result"] != "SL" else "❌"
        arrow = "🟢" if ct["direction"]=="LONG" else "🔴"
        lines += (
            f"\n{em} {arrow} <b>{ct['pair']}</b> {ct['direction']}\n"
            f"   Entry: {fmt(ct['entry'])} → Exit: {fmt(ct['exit'])}\n"
            f"   PnL: <b>${ct['pnl']:+.4f} ({ct['roi']:+.2f}%)</b> | {ct['result']}\n"
            f"   {ct['opened']} → {ct['closed']}\n"
        )
    lines += (
        f"\n━━━━━━━━━━━━━━━━━━━\n"
        f"✅ Wins: {wins} | ❌ Losses: {len(recent)-wins}\n"
        f"💰 Combined PnL: <b>${total_pnl:+.4f}</b>"
    )
    tg(lines)

def cmd_stats():
    wins = STATE["wins"]; losses = STATE["losses"]
    total = wins+losses; wr = round(wins/total*100,1) if total > 0 else 0
    bal = STATE["balance"]
    growth = round((bal-PAPER_BAL)/PAPER_BAL*100, 2)
    rr = round(TP3_PCT/SL_PCT, 1)
    tg(
        f"📊 <b>PERFORMANCE STATS</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"💼 Balance: <b>${bal:.4f}</b>\n"
        f"📈 Growth: <b>{growth:+.2f}%</b>\n"
        f"💰 Realized PnL: <b>${STATE['total_pnl']:+.4f}</b>\n\n"
        f"🏆 Total Trades: <b>{total}</b>\n"
        f"✅ Wins: <b>{wins}</b> | ❌ Losses: <b>{losses}</b>\n"
        f"🎯 Win Rate: <b>{wr}%</b>\n"
        f"⚖️ Risk/Reward: <b>1:{rr}</b>\n\n"
        f"🔄 Open Now: <b>{len(STATE['open_trades'])}/{MAX_OPEN}</b>\n"
        f"📡 Scans Done: <b>{STATE['scan_count']}</b>\n"
        f"🚀 Signals Fired: <b>{STATE['signals_total']}</b>\n"
        f"🔍 Coins Watched: <b>{len(COINS)}</b>\n"
        f"⏰ Running since: {STATE['start_time']}"
    )

def cmd_portfolio():
    bal = STATE["balance"]
    pnl = STATE["total_pnl"]
    growth = round((bal-PAPER_BAL)/PAPER_BAL*100, 2)
    wins = STATE["wins"]; losses = STATE["losses"]
    total = wins+losses; wr = round(wins/total*100,1) if total > 0 else 0
    open_t = STATE["open_trades"]
    upnl = 0.0; open_lines = ""
    for cid, t in open_t.items():
        price, _ = get_price(cid)
        time.sleep(1)
        if price > 0:
            u = round((price-t["entry"])/t["entry"]*t["size"]*(1 if t["direction"]=="LONG" else -1), 4)
            upnl += u
            em = "📈" if u >= 0 else "📉"
            open_lines += f"  {em} {t['pair']} {t['direction']} | uPnL: ${u:+.4f}\n"
    recent = STATE["closed_trades"][-5:]
    closed_lines = ""
    for ct in reversed(recent):
        em = "✅" if ct["result"]!="SL" else "❌"
        closed_lines += f"  {em} {ct['pair']} {ct['direction']} {ct['result']} ${ct['pnl']:+.4f}\n"
    tg(
        f"📊 <b>FULL PORTFOLIO</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"💼 Balance: <b>${bal:.4f}</b>\n"
        f"🚀 Started: ${PAPER_BAL:.2f}\n"
        f"{'📈' if growth>=0 else '📉'} Growth: <b>{growth:+.2f}%</b>\n"
        f"💰 Realized PnL:   <b>${pnl:+.4f}</b>\n"
        f"📊 Unrealized PnL: <b>${upnl:+.4f}</b>\n"
        f"🏆 Total PnL: <b>${pnl+upnl:+.4f}</b>\n\n"
        f"✅ Wins: {wins} | ❌ Losses: {losses} | 🎯 WR: {wr}%\n\n"
        f"🔄 Open ({len(open_t)}):\n{open_lines if open_lines else '  None\n'}\n"
        f"📋 Last 5 Closed:\n{closed_lines if closed_lines else '  None\n'}\n"
        f"⏰ {datetime.now().strftime('%b %d %H:%M')}"
    )

# ─────────────────────────────────────────
#  MAIN LOOP
# ─────────────────────────────────────────
def main():
    global LAST_UPDATE_ID
    log.info("Bot starting — Liquidity Grab Strategy")
    tg_both(
        f"🤖 <b>AI CRYPTO BOT STARTED</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📌 Coins: <b>{len(COINS)}</b> | Timeframe: <b>1H</b>\n"
        f"💼 Balance: <b>${PAPER_BAL:.2f}</b>\n"
        f"⚖️ Risk: <b>{int(RISK_PCT*100)}% per trade</b> (max {MAX_OPEN} open)\n"
        f"📡 Strategy: Liquidity Grab + Price Action\n"
        f"⚠️ <i>PAPER TRADING MODE</i>\n\n"
        f"Commands: /balance /trades /closed /stats /portfolio /help"
    )

    last_report = time.time()
    last_cmd    = time.time()

    while True:
        try:
            # ── Check Telegram commands every 30s ──
            if time.time()-last_cmd > 30:
                handle_commands()
                last_cmd = time.time()

            # ── Check exits on open trades ──
            if STATE["open_trades"]:
                check_exits()

            # ── Scan coins ──
            STATE["scan_count"] += 1
            scan = STATE["scan_count"]
            log.info(f"Scan #{scan} — {len(COINS)} coins — {datetime.now().strftime('%H:%M:%S')}")
            signals = 0

            for coin_id, pair in COINS:
                # Check commands during long scan
                if time.time()-last_cmd > 30:
                    handle_commands()
                    last_cmd = time.time()

                try:
                    data = get_ohlc(coin_id)
                    if not data: time.sleep(4); continue

                    opens  = [c[1] for c in data]
                    highs  = [c[2] for c in data]
                    lows   = [c[3] for c in data]
                    closes = [c[4] for c in data]

                    direction,score,tags,rsi_val,atr_val,sl_lvl,sh_lvl = detect_grab(opens,highs,lows,closes)

                    if direction:
                        hkey = datetime.now().strftime('%Y%m%d%H')
                        fkey = f"{coin_id}_{direction}_{hkey}"
                        if fkey not in FIRED and coin_id not in STATE["open_trades"]:
                            price, chg24 = get_price(coin_id)
                            if price == 0: time.sleep(1); continue
                            result = open_trade(coin_id,pair,direction,price,score,tags,sl_lvl,sh_lvl)
                            if result:
                                sl,tp1,tp2,tp3 = result
                                t = STATE["open_trades"][coin_id]
                                c = conf(score)
                                arrow = "🟢" if direction=="LONG" else "🔴"
                                tg_channel(
                                    f"🚀 <b>AI SIGNAL IS READY</b>\n\n"
                                    f"📊 <b>Pair:</b> {pair}\n"
                                    f"{arrow} <b>Direction:</b> {direction}\n"
                                    f"🎯 <b>Entry Zone:</b> {fmt(price*0.999)} – {fmt(price*1.002)}\n"
                                    f"🛡 <b>Stop Loss:</b> {fmt(sl)}\n\n"
                                    f"🎯 <b>Take Profits:</b>\n"
                                    f"1️⃣  {fmt(tp1)}\n"
                                    f"2️⃣  {fmt(tp2)}\n"
                                    f"3️⃣  {fmt(tp3)}\n\n"
                                    f"🧠 <b>Confidence:</b> {c}%\n"
                                    f"{tags[0] if tags else 'Liquidity Grab'}\n\n"
                                    f"📈 <b>24h Change:</b> {chg24:+.2f}%\n"
                                    f"RSI: {rsi_val:.1f} | Confirmations: {score}/8\n"
                                    f"💼 Size: ${t['size']:.2f} | Balance: ${STATE['balance']:.2f}\n"
                                    f"⏰ {datetime.now().strftime('%b %d, %Y, %I:%M %p')}"
                                )
                                FIRED.add(fkey)
                                signals += 1
                                log.info(f"Signal: {direction} {pair} score={score}")
                                time.sleep(4)

                    time.sleep(4)

                except Exception as e:
                    log.error(f"{pair}: {e}")
                    time.sleep(3)

            log.info(f"Scan #{scan} done — {signals} signals — {len(STATE['open_trades'])} open")

            # Portfolio report every 4 hours
            if time.time()-last_report > 4*3600:
                cmd_portfolio()
                last_report = time.time()

            if len(FIRED) > 600:
                old = list(FIRED)[:250]
                for k in old: FIRED.discard(k)

        except KeyboardInterrupt:
            tg("🛑 <b>Bot stopped.</b>")
            cmd_portfolio()
            break
        except Exception as e:
            log.error(f"Loop: {e}"); tg(f"⚠️ Error: {e}")

        log.info(f"Sleeping {CHECK//60} min...")
        time.sleep(CHECK)

if __name__ == "__main__":
    main()
