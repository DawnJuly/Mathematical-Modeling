# 公共求解模块：微网购电调度 LP 建模与数据读取
# 供 求解/问题X/*.py 通过 `from _models import *` 使用
import os
import numpy as np
import pandas as pd
from scipy.optimize import linprog

# ---- 常量 ----
DT = 1.0 / 6.0          # 10分钟 = 1/6 小时
ETA = 0.9               # 充/放电效率 90%
EMIN, EMAX = 1200.0, 10800.0   # 储电量上下界 (kWh)
PMAX = 5000.0           # 最大充放电功率 (kW)
E0_INIT = 6000.0        # 2025-01-01 0:00 初始储电量 (kWh)
N_INT = 144             # 一天 144 个 10 分钟间隔

# ---- 数据读取 ----
def _data_dir():
    return os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '数据'))

def read_附件1():
    """返回 (price[144], load[144], pv[144])，附件1 单日电价/负载/光伏预测"""
    p = os.path.join(_data_dir(), '附件1.xlsx')
    df = pd.read_excel(p, sheet_name='Sheet1')
    price = pd.to_numeric(df['电价'], errors='coerce').to_numpy(dtype=float)
    load = pd.to_numeric(df['小区负载'], errors='coerce').to_numpy(dtype=float)
    pv = pd.to_numeric(df['光伏发电预测功率'], errors='coerce').to_numpy(dtype=float)
    assert len(price) == N_INT, f'附件1 行数 {len(price)} != 144'
    return price, load, pv

def read_附件2():
    """返回 (dates[365], load[365,144], pv[365,144]) 附件2 实际负载与光伏"""
    p = os.path.join(_data_dir(), '附件2.xlsx')
    load_df = pd.read_excel(p, sheet_name='小区负载')
    pv_df = pd.read_excel(p, sheet_name='光伏发电实际功率')
    dates = pd.to_datetime(load_df.iloc[:, 0]).dt.to_pydatetime()
    load = load_df.iloc[:, 1:145].to_numpy(dtype=float)
    pv = pv_df.iloc[:, 1:145].to_numpy(dtype=float)
    return dates, load, pv

def read_附件4():
    """返回 (dates[365], price[365,144]) 附件4 波动电价"""
    p = os.path.join(_data_dir(), '附件4.xlsx')
    df = pd.read_excel(p, sheet_name='Sheet1')
    dates = pd.to_datetime(df.iloc[:, 0]).dt.to_pydatetime()
    price = df.iloc[:, 1:145].to_numpy(dtype=float)
    return dates, price

def read_附件3():
    """返回 dict: {date: {T: f[24]}}，T∈{0,6,12,18}，f=未来24小时整点光伏预报(kW)"""
    p = os.path.join(_data_dir(), '附件3.xlsx')
    df = pd.read_excel(p, sheet_name='Sheet1')
    df.columns = [str(c).strip() for c in df.columns]
    df['日期'] = df['日期'].ffill()
    df['预报时刻'] = df['预报时刻'].astype(str).str.strip()
    cols = [c for c in df.columns if '预报' in c and '小时' in c]
    T_map = {'0:00': 0, '6:00': 6, '12:00': 12, '18:00': 18}
    out = {}
    for _, row in df.iterrows():
        d = str(row['日期']).strip()
        T = T_map.get(row['预报时刻'])
        if T is None:
            continue
        f = pd.to_numeric(row[cols], errors='coerce').to_numpy(dtype=float)
        out.setdefault(d, {})[T] = f
    return out

# ---- 光伏预报小时值 -> 10分钟间隔功率 ----
def forecast_10min(T, f, k0=0, k1=N_INT - 1):
    """按时刻T发布的预报 f[24]（f[i]=T+(i+1)小时的整点功率），
    线性插值到间隔 k∈[k0,k1] 的功率(kW)。间隔k对应时间(k+1)/6小时（间隔末端）。"""
    hours = np.arange(T, T + 25, dtype=float)          # T, T+1, ..., T+24
    vals = np.concatenate(([f[0]], f))                  # 当前整点用预报1小时近似
    ts = (np.arange(k0, k1 + 1, dtype=float) + 1.0) / 6.0   # 间隔末端时刻(小时)
    pv = np.interp(ts, hours, vals)
    return np.maximum(pv, 0.0)

def _forecast_day10min(fc, T, k0, k1):
    """把附件3某日某时刻预报插值到该日间隔 k0..k1（绝对日间隔序号）"""
    return forecast_10min(T, fc[T], k0, k1)

# ---- 单日 LP 求解 ----
def solve_daily(L, S, price, e0=None, soc_cycle=False, k0=0, k1=N_INT - 1):
    """求解间隔 k0..k1 的购电/充放电调度。
    L,S,price 长度均为 (k1-k0+1)（或全144，取 k0:k1+1 切片）。
    e0: 初始储电量(固定)；soc_cycle: 问题一——固定 E[k0]=e0（附录1给定，默认6000）
    并施加日循环 E[k0]=E[k1+1]。
    返回 (g, ch, dch, E, cost)：g/ch/dch(kW, 长n)，E(kWh, 长n+1)，cost(元)。"""
    L = np.asarray(L, dtype=float)[k0:k1 + 1]
    S = np.asarray(S, dtype=float)[k0:k1 + 1]
    price = np.asarray(price, dtype=float)[k0:k1 + 1]
    n = k1 - k0 + 1
    # 变量顺序: g(0..n-1), ch(n..2n-1), dch(2n..3n-1), E(3n..4n)
    nv = 4 * n + 1
    c = np.zeros(nv)
    c[:n] = price * DT
    # 不等式: 供电≥负载（允许弃光） g + dch - ch >= L - S  ->  -g - dch + ch <= S - L
    Aub = np.zeros((n, nv))
    bub = np.zeros(n)
    for i in range(n):
        Aub[i, i] = -1.0            # -g
        Aub[i, 2 * n + i] = -1.0    # -dch
        Aub[i, n + i] = 1.0         # +ch
        bub[i] = S[i] - L[i]
    # 等式约束: SOC动态(n) (+ 初始/周期)
    Aeq = np.zeros((n, nv))
    beq = np.zeros(n)
    for i in range(n):
        Aeq[i, 3 * n + i + 1] = 1.0      # E[i+1]
        Aeq[i, 3 * n + i] = -1.0         # -E[i]
        Aeq[i, n + i] = -ETA * DT        # -eta*dt*ch
        Aeq[i, 2 * n + i] = DT / ETA     # +dt/eta*dch
        beq[i] = 0.0
    # 边界
    lb = np.zeros(nv)
    ub = np.full(nv, np.inf)
    ub[n:3 * n] = PMAX                  # ch, dch <= 5000
    lb[3 * n:] = EMIN
    ub[3 * n:] = EMAX
    # 初始/周期约束
    if soc_cycle:
        # 附录1给定 0:00 储电量：E[k0] = e0（默认 6000 kWh），不再作为可优化变量
        e0v = float(E0_INIT if e0 is None else e0)
        row = np.zeros(nv)
        row[3 * n] = 1.0
        Aeq = np.vstack([Aeq, row])
        beq = np.append(beq, e0v)
        # 日循环约束：E[k0] - E[k1+1] = 0
        row = np.zeros(nv)
        row[3 * n] = 1.0
        row[4 * n] = -1.0
        Aeq = np.vstack([Aeq, row])
        beq = np.append(beq, 0.0)
    else:
        # E[k0] = e0
        row = np.zeros(nv)
        row[3 * n] = 1.0
        Aeq = np.vstack([Aeq, row])
        beq = np.append(beq, float(e0))
    res = linprog(c, A_ub=Aub, b_ub=bub, A_eq=Aeq, b_eq=beq, bounds=list(zip(lb, ub)), method='highs')
    if not res.success:
        # 回退到 highs-ds / highs-ipm
        res = linprog(c, A_ub=Aub, b_ub=bub, A_eq=Aeq, b_eq=beq, bounds=list(zip(lb, ub)), method='highs-ds')
    if not res.success:
        raise RuntimeError(f'LP失败: {res.message}')
    x = res.x
    g = x[:n]
    ch = x[n:2 * n]
    dch = x[2 * n:3 * n]
    E = x[3 * n:4 * n + 1]
    cost = float(res.fun)
    return g, ch, dch, E, cost

# ---- 带违约/超额惩罚的调整 LP ----
def solve_adjust(L, S, price, plan, e0, k0=0, k1=N_INT - 1):
    """在间隔 k0..k1 重优化调整购电，费用=min(plan,adj)+0.5*max(plan-adj,0)+1.5*max(adj-plan,0)。
    plan 为全144的0:00计划购电(kW)；e0 为 E[k0]。
    返回 (adj, ch, dch, E, cost)。"""
    L = np.asarray(L, dtype=float)[k0:k1 + 1]
    S = np.asarray(S, dtype=float)[k0:k1 + 1]
    price = np.asarray(price, dtype=float)[k0:k1 + 1]
    plan = np.asarray(plan, dtype=float)[k0:k1 + 1]
    n = k1 - k0 + 1
    # 变量: g(0..n-1), ch(n..2n-1), dch(2n..3n-1), E(3n..4n), w(4n+1..5n)
    nv = 5 * n + 1
    c = np.zeros(nv)
    c[4 * n + 1:5 * n + 1] = 1.0          # min sum w
    # 等式: SOC动态(n) + 初始(1)
    Aeq = np.zeros((n + 1, nv))
    beq = np.zeros(n + 1)
    for i in range(n):
        Aeq[i, 3 * n + i + 1] = 1.0
        Aeq[i, 3 * n + i] = -1.0
        Aeq[i, n + i] = -ETA * DT
        Aeq[i, 2 * n + i] = DT / ETA
        beq[i] = 0.0
    Aeq[n, 3 * n] = 1.0
    beq[n] = float(e0)
    # 不等式1: 供电≥负载（允许弃光） -g - dch + ch <= S - L
    # 不等式2: 分段费用上境 w >= f(adj)
    Aub = np.zeros((3 * n, nv))
    bub = np.zeros(3 * n)
    for i in range(n):
        Aub[i, i] = -1.0
        Aub[i, 2 * n + i] = -1.0
        Aub[i, n + i] = 1.0
        bub[i] = S[i] - L[i]
    for i in range(n):
        p = price[i]
        # w - 0.5*dt*p*g >= 0.5*dt*p*plan  ->  -w + 0.5dtp g <= -0.5dtp plan
        Aub[n + i, 4 * n + 1 + i] = -1.0
        Aub[n + i, i] = 0.5 * DT * p
        bub[n + i] = -0.5 * DT * p * plan[i]
        # w - 1.5*dt*p*g >= -0.5*dt*p*plan ->  -w + 1.5dtp g <= 0.5dtp plan
        Aub[2 * n + i, 4 * n + 1 + i] = -1.0
        Aub[2 * n + i, i] = 1.5 * DT * p
        bub[2 * n + i] = 0.5 * DT * p * plan[i]
    lb = np.zeros(nv)
    ub = np.full(nv, np.inf)
    ub[n:3 * n] = PMAX
    lb[3 * n:4 * n + 1] = EMIN
    ub[3 * n:4 * n + 1] = EMAX
    lb[4 * n + 1:5 * n + 1] = 0.0
    res = linprog(c, A_ub=Aub, b_ub=bub, A_eq=Aeq, b_eq=beq,
                  bounds=list(zip(lb, ub)), method='highs')
    if not res.success:
        res = linprog(c, A_ub=Aub, b_ub=bub, A_eq=Aeq, b_eq=beq,
                      bounds=list(zip(lb, ub)), method='highs-ds')
    if not res.success:
        raise RuntimeError(f'调整LP失败: {res.message}')
    x = res.x
    adj = x[:n]
    ch = x[n:2 * n]
    dch = x[2 * n:3 * n]
    E = x[3 * n:4 * n + 1]
    return adj, ch, dch, E, float(res.fun)

# ---- 10分钟间隔标签 ----
def interval_labels(k0=0, k1=N_INT - 1):
    """间隔 k=[k/6,(k+1)/6] 的 'HH:MM-HH:MM' 标签（用末端时刻对齐，跨24点加+1）"""
    labs = []
    for k in range(k0, k1 + 1):
        a = k * 10
        b = (k + 1) * 10
        s = _hhmm(a) + '-' + _hhmm(b)
        if b >= 1440:
            s = _hhmm(a) + '-' + _hhmm(b - 1440) + '+1'
        labs.append(s)
    return labs

def _hhmm(mins):
    h = (mins // 60) % 24
    m = mins % 60
    return f'{h:02d}:{m:02d}'
