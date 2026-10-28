# -*- coding: utf-8 -*-
import os, time, re
for k in ['HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy','ALL_PROXY','all_proxy']:
    os.environ.pop(k, None)
os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'
import requests
_orig = requests.Session.__init__
def _patched(self, *a, **k):
    _orig(self, *a, **k)
    self.trust_env = False
requests.Session.__init__ = _patched

import akshare as ak
import pandas as pd
import numpy as np
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 300)
pd.set_option('display.max_rows', 200)

def num(s): return pd.to_numeric(s, errors='coerce')
UA = {'User-Agent':'Mozilla/5.0'}

# 1) 中证A100 成分股（A股市值前100）
cons = ak.index_stock_cons_csindex(symbol="000903")
codes = cons['成分券代码'].astype(str).str.zfill(6).tolist()
print("中证A100 成分数:", len(codes))

# 2) 腾讯批量行情
def tprefix(c): return ('sh' if c[0]=='6' else 'sz') + c
r = requests.get("http://qt.gtimg.cn/q=" + ",".join(tprefix(c) for c in codes), timeout=25, headers=UA)
txt = r.text
rows = []
for m in re.finditer(r'v_(?:sh|sz)(\d{6})="([^"]*)"', txt):
    code = m.group(1); f = m.group(2).split('~')
    if len(f) < 69: continue
    rows.append({
        '代码': code, '名称': f[1], '最新价': f[3],
        '市盈率TTM': f[39], '市净率': f[46], '总市值亿': f[45],
        '今日涨跌幅': f[32], '52周最高': f[67], '52周最低': f[68],
    })
quote = pd.DataFrame(rows)
print("腾讯行情取到:", len(quote), "只")

# 3) 东财财务数据（datacenter，稳定）
fin = None
for attempt in range(5):
    try:
        fin = ak.stock_yjbb_em(date="20260930")
        if fin is not None and len(fin) > 0: break
    except Exception as e:
        time.sleep(3 + attempt*2)
print("财务数据:", None if fin is None else len(fin), "只")

fin = fin.copy()
fin['股票代码'] = fin['股票代码'].astype(str).str.zfill(6)
fin2 = fin.rename(columns={'股票代码':'代码','净资产收益率':'ROE%','营业总收入-同比增长':'营收同比%',
    '净利润-同比增长':'净利同比%','销售毛利率':'毛利率%','每股收益':'每股收益',
    '每股净资产':'每股净资产','所处行业':'行业'})[['代码','ROE%','营收同比%','净利同比%','毛利率%','每股收益','每股净资产','行业']]

# 合并
df = quote.merge(fin2, on='代码', how='left')
for c in ['最新价','市盈率TTM','市净率','总市值亿','今日涨跌幅','52周最高','52周最低','ROE%','营收同比%','净利同比%','毛利率%','每股收益','每股净资产']:
    df[c] = num(df[c])

# 剔除 ST
df = df[~df['名称'].astype(str).str.contains('ST|退', na=False)]

# 距离52周高低点位置
df['距高点回撤%'] = ((df['最新价']/df['52周最高'] - 1) * 100).round(2)
df['距低点涨幅%'] = ((df['最新价']/df['52周最低'] - 1) * 100).round(2)

# ---- 筛选 ----
m = df.copy()
conds = {
    'ROE>=8': m['ROE%'] >= 8,
    '净利同比>0': m['净利同比%'] > 0,
    '营收同比>0': m['营收同比%'] > 0,
    '0<PE<=20': (m['市盈率TTM'] > 0) & (m['市盈率TTM'] <= 20),
    '0<PB<=4': (m['市净率'] > 0) & (m['市净率'] <= 4),
}
print("\n各条件通过数 (中证A100):")
for k,v in conds.items():
    print(f"  {k}: {int(v.sum())}")

mask = np.ones(len(m), dtype=bool)
for v in conds.values(): mask &= v.fillna(False).values
cand = m[mask].copy()

if len(cand) > 0:
    q_n = cand['ROE%'].clip(0,20)/20
    g_n = cand['净利同比%'].clip(0,40)/40
    v_n = (20 - cand['市盈率TTM']).clip(0,20)/20
    l_n = ((-cand['距高点回撤%'])/40).clip(0,1)
    cand['评分'] = (100*(0.35*q_n + 0.25*g_n + 0.25*v_n + 0.15*l_n)).round(1)
    cand = cand.sort_values('评分', ascending=False).reset_index(drop=True)

out_cols = ['代码','名称','行业','最新价','总市值亿','市盈率TTM','市净率','ROE%','净利同比%','营收同比%','毛利率%','每股收益','每股净资产','距高点回撤%','距低点涨幅%','评分']
result = cand[out_cols].copy()
for c in out_cols[3:]:
    result[c] = result[c].round(2)

print(f"\n===== 筛选结果: {len(result)} 只 =====\n")
print(result.to_string(index=False))

result.to_csv(r"C:\Users\bfxhz\.openclaw\workspace\A股前100筛选结果.csv", index=False, encoding='utf-8-sig')
df[out_cols[:-1]].to_csv(r"C:\Users\bfxhz\.openclaw\workspace\A股前100全部.csv", index=False, encoding='utf-8-sig')
print(f"\n已保存: A股前100筛选结果.csv / A股前100全部.csv")
