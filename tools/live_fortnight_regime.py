"""The live fortnight, against the majors. Owner-requested reality check.

    railway run --service Futures-bot python tools/live_fortnight_regime.py

WHY. The owner distrusts the 190-day point-in-time replays: the bot's config
changed across trials 5-17 over that window, and the replay pool is chosen by
who is liquid TODAY. Both objections are correct. The replay answers "would
this change have helped", not "what did the bot do". So this looks at nothing
but the 36 REAL fills since 2026-08-14, with BTC/ETH/SOL overlaid at each
entry, to test the owner's own account of the fortnight: majors ran, the bot
caught TUT and ENA, then majors flattened and the book bled.

THE NARRATIVE IS CONFIRMED, and the discriminator is NOT the one the owner's
proposed rule used. Splitting the 36 fills on BTC's 72-HOUR move at entry:

    BTC72 >= 10%   n=17   $+44.29   $+2.605/trade   win 71%
    BTC72 <  10%   n=19   $-24.93   $-1.312/trade   win 21%

The 24h move does not separate them: TUT_USDT, the best trade of the fortnight
at +$17.94, entered with BTC24 at +0.1% and ETH24 at +1.7% -- a flat tape by
any 24h measure. What was true was BTC72 = +19.2%. A 2%/12h or 5%/24h rule
misses it entirely; only the 72h leg catches it.

AND IT INVERTS THE 190-DAY CALM-TILT RESULT. tools/pit_calm_tilt.py measured
+$41 size-neutral for sizing UP when the majors are calm. Applied to this
fortnight that tilt sizes 0.53x through the profitable run (mean calm score
2.90) and 0.88x through the bleed, turning +$19.36 into -$0.86. The inverse
returns +$39.59. On live fills the 190-day conclusion is exactly backwards.

WHAT THIS DOES NOT ESTABLISH, stated plainly because the numbers are seductive.
BTC72 >= 10% happened ONCE here, for three days. So this is n=17 trades but
n=1 EPISODE, and "BTC72 was high" is not separable from "it was 08-20 to
08-22". The 190-day study covers the same condition on 32 trades across
multiple episodes and finds surplus +$0.23 -- zero. Two small samples
disagree; neither settles it.

THE USE OF THIS FILE is therefore to justify INSTRUMENTING, not acting: record
BTC72 (and the calm score) at entry so future episodes accumulate. Four or five
episodes would answer what one cannot. Read-only; places nothing.
"""
import sys, json, datetime, time
sys.path.insert(0, r'C:/Users/Rocot/Claude session/futuresbot')
from futuresbot.config import FuturesConfig
from futuresbot.marketdata import MexcFuturesClient
SP = r'C:/Users/Rocot/AppData/Local/Temp/claude/C--Users-Rocot-Claude-session/8c93b1ba-3446-4dcb-9618-2245bc04ca42/scratchpad'
T = json.load(open(SP + '/live2w.json', encoding='utf-8'))
cl = MexcFuturesClient(FuturesConfig.from_env())
now = int(time.time()); MAJ = ('BTC_USDT','ETH_USDT','SOL_USDT')
px = {m: [(int(q.timestamp()), float(c)) for q, c in
          zip(cl.get_klines(m, interval='Min15', start=now-20*86400, end=now).index,
              cl.get_klines(m, interval='Min15', start=now-20*86400, end=now)['close'])]
      for m in MAJ}
def ret(m, ts, h):
    s = px[m]; lo = ts - h*3600; a = b = None
    for t, c in s:
        if t <= ts: b = c
        if t <= lo: a = c
    return (b/a - 1.0) if (a and b) else None
def ets(x):
    try: return datetime.datetime.fromisoformat(str(x)).timestamp()
    except Exception: return 0.0
rows = []
for t in T:
    ts = ets(t['entry_time'])
    if not ts: continue
    b72 = ret('BTC_USDT', ts, 72)
    # the SAME calm score the 190-day tilt study used
    sc = 0.0
    for m in MAJ:
        for h, thr in ((12,0.02),(24,0.05),(72,0.10)):
            v = ret(m, ts, h)
            if v is not None: sc = max(sc, abs(v)/thr)
    rows.append({'t': t, 'ts': ts, 'b72': b72, 'score': sc,
                 'p': float(t.get('pnl_usdt') or 0)})
rows.sort(key=lambda r: r['ts'])
tot = sum(r['p'] for r in rows)
print('LIVE FORTNIGHT: %d trades, realised $%+.2f\n' % (len(rows), tot))
print('SPLIT BY BTC 72h MOVE AT ENTRY')
for lbl, f in (('BTC72 >= 10%', lambda r: r['b72'] is not None and r['b72'] >= 0.10),
               ('BTC72 <  10%', lambda r: r['b72'] is not None and r['b72'] < 0.10)):
    g = [r for r in rows if f(r)]
    w = sum(1 for r in g if r['p'] > 0)
    print('  %-14s n=%2d  $%+8.2f  $%+6.3f/trade  win %3.0f%%'
          % (lbl, len(g), sum(r['p'] for r in g), sum(r['p'] for r in g)/max(1,len(g)),
             100*w/max(1,len(g))))
print('\nAPPLYING THE 190-DAY CALM TILT TO THIS FORTNIGHT')
print('(that study concluded: size UP when calm score <=1.0, DOWN when >=2.0)')
def mult(r, lo=0.5, hi=1.5):
    s = r['score']
    return hi if s <= 1.0 else (lo if s >= 2.0 else 1.0)
tilted = sum(mult(r) * r['p'] for r in rows)
inv = sum(mult(r, 1.5, 0.5) * r['p'] for r in rows)
print('  flat                       $%+8.2f' % tot)
print('  calm-tilt 1.5/0.5          $%+8.2f   (%+.2f vs flat)' % (tilted, tilted - tot))
print('  INVERSE tilt 0.5/1.5       $%+8.2f   (%+.2f vs flat)' % (inv, inv - tot))
print('\n  what the tilt did, by period:')
for lbl, f in (('profitable 08-20..22', lambda r: '2026-08-20' <= r['t']['entry_time'][:10] <= '2026-08-22'),
               ('the bleed 08-23..28', lambda r: r['t']['entry_time'][:10] >= '2026-08-23')):
    g = [r for r in rows if f(r)]
    if not g: continue
    am = sum(mult(r) for r in g)/len(g)
    print('    %-22s n=%2d  raw $%+7.2f  mean calm score %.2f  -> tilt sizes %.2fx'
          % (lbl, len(g), sum(r['p'] for r in g), sum(r['score'] for r in g)/len(g), am))
