# 公共求解模块：微网购电调度 LP 建模与数据读取
# 供 求解/问题X/*.py 通过 `from _models import *` 使用
import os
import numpy as np
import pandas as pd
from scipy.optimize import linprog
from scipy.sparse import csr_matrix

# ---- 常量 ----
DT = 1.0 / 6.0          # 10分钟 = 1/6 小时
ETA = 0.9               # 充/放电效率 90%
EMIN, EMAX = 1200.0, 10800.0   # 储电量上下界 (kWh)
PMAX = 5000.0           # 最大充放电功率 (kW)
E0_INIT = 6000.0        # 2025-01-01 0:00 初始储电量 (kWh)
N_INT = 144             # 一天 144 个 10 分钟间隔

# ---- 数据读取 ----
def _data_dir():
    """按候选顺序探测附件目录（兼容 求解/ 与 求解/问题X/ 两种脚本位置）。"""
    import glob as _glb
    here = os.path.dirname(os.path.abspath(__file__))
    cands = []
    for n in (1, 2, 3):
        up = os.path.normpath(os.path.join(here, *['..'] * n))
        for name in ('附件', '数据'):
            cands.append(os.path.join(up, name))
            cands += sorted(_glb.glob(os.path.join(up, '*', name)))
    for c in cands:
        if os.path.isfile(os.path.join(c, '附件1.xlsx')):
            return c
    raise FileNotFoundError('未找到附件目录，已尝试: ' + '; '.join(cands))

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
    """返回 dict: {date: {T: f[24]}}，T in {0,6,12,18}，f=未来24小时整点光伏预报(kW)"""
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
    线性插值到间隔 k in [k0,k1] 的功率(kW)。间隔k对应时间(k+1)/6小时（间隔末端）。"""
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

# ================= 问题二：预测 — 决策 — 结算 三段式 =================
VALLEY_WEEKDAYS = (4, 5)      # 实测工作日/休息日负荷形态在此处分档（周五、周六）

def _norm_shape(x):
    """归一化日形状：逐点除以日均值，均值为 0 时原样返回。"""
    x = np.asarray(x, dtype=float)
    m = x.mean()
    return x / m if m > 0 else x.copy()

def forecast_load(hist_load, hist_dates, target, k_shape=8, k_level=2):
    """负载预测：同类日 EWMA 水平 × 近 k_shape 个同类日归一化形状均值。

    hist_load  长 (T,144) 历史负载；hist_dates 长 T 的日期序列；target 目标日。
    只使用 target 之前的数据，同类日按 VALLEY_WEEKDAYS 分档。
    返回长 144 的预测负载 (kW)。
    """
    hist_load = np.asarray(hist_load, dtype=float)
    hist_dates = list(hist_dates)
    tgt_cls = target.weekday() in VALLEY_WEEKDAYS
    idx = [i for i, d in enumerate(hist_dates)
           if (d.weekday() in VALLEY_WEEKDAYS) == tgt_cls]
    if len(idx) == 0:
        idx = list(range(len(hist_dates)))
    idx = idx[-max(k_shape, k_level):]
    lvls = hist_load[idx].mean(axis=1)
    k_l = min(k_level, len(idx))
    w = np.linspace(1.0, 2.0, k_l)
    level = float(np.average(lvls[-k_l:], weights=w))
    shape = np.mean([_norm_shape(hist_load[i]) for i in idx[-k_shape:]], axis=0)
    return np.maximum(level * shape, 0.0)

def forecast_pv(hist_pv, hist_dates=None, target=None, k_shape=4, k_level=4):
    """光伏预测：近 k_shape 天归一化形状均值 × 近 k_level 天日均水平的 EWMA。

    光伏形态对星期不敏感，跨星期取最近若干天。返回长 144 的预测光伏 (kW)。
    """
    hist_pv = np.asarray(hist_pv, dtype=float)
    k_s = min(k_shape, len(hist_pv))
    idx = list(range(len(hist_pv) - k_s, len(hist_pv)))
    shape = np.mean([_norm_shape(hist_pv[i]) for i in idx], axis=0)
    lvls = hist_pv[idx].mean(axis=1)
    k_l = min(k_level, len(idx))
    w = np.linspace(1.0, 2.0, k_l)
    level = float(np.average(lvls[-k_l:], weights=w))
    return np.maximum(level * shape, 0.0)

def pred_residual(F, A, thr=1.0):
    """逐点相对预测残差 (A-F)/max(F,thr)，展平返回。"""
    F = np.asarray(F, dtype=float)
    A = np.asarray(A, dtype=float)
    return ((A - F) / np.maximum(F, thr)).ravel()

def scenario_factors(res_load, res_pv, q=(0.1, 0.5, 0.9), fallback=(0.95, 1.0, 1.05)):
    """由历史预测残差的经验分位数标定情景因子。

    因子 f = 1 + 残差分位数；样本不足 50 时退回先验 fallback。
    返回 (load_fac, pv_fac) 各长 3，并做安全裁剪。
    """
    out = []
    for res, lo, hi in ((res_load, 0.7, 1.3), (res_pv, 0.5, 1.5)):
        res = np.asarray(res, dtype=float)
        res = res[np.isfinite(res)]
        if res.size < 50:
            f = np.asarray(fallback, dtype=float)
        else:
            f = 1.0 + np.percentile(res, np.asarray(q, dtype=float) * 100.0)
        out.append(np.clip(f, lo, hi))
    return out[0], out[1]

def solve_daily_stochastic(L_fc, S_fc, price, load_fac, pv_fac, pi, e0,
                           emerg_mult=5.0, k0=0, k1=N_INT - 1):
    """两阶段随机 LP：0:00 一次性决定计划购电与充放电，紧急购电事后兜底。

    第一阶段 g/ch/dch/E 不依赖情景；第二阶段各情景的紧急购电 δ_s 按 5 倍电价计入。
    目标 min Σ p_k g_k dt + Σ_s π_s Σ_k 5 p_k δ_{s,k} dt
    约束 δ_{s,k} ≥ L̂_k f^L_s − Ŝ_k f^PV_s − g_k − dch_k + ch_k（逐情景独立）
    SOC 递推对全情景唯一，δ ≥ 0、ch/dch ≤ P_max、E 在 [E_min,E_max] 内。
    返回 (g, ch, dch, E, exp_cost)。
    """
    L_fc = np.asarray(L_fc, dtype=float)[k0:k1 + 1]
    S_fc = np.asarray(S_fc, dtype=float)[k0:k1 + 1]
    price = np.asarray(price, dtype=float)[k0:k1 + 1]
    load_fac = np.asarray(load_fac, dtype=float)
    pv_fac = np.asarray(pv_fac, dtype=float)
    pi = np.asarray(pi, dtype=float)
    n = k1 - k0 + 1
    ns = len(load_fac)
    off_d = 4 * n + 1                    # δ_s 的起始列
    nv = off_d + ns * n
    # 变量顺序: g, ch, dch, E(0..4n), δ(off_d..)
    c = np.zeros(nv)
    c[:n] = price * DT
    for s in range(ns):
        c[off_d + s * n: off_d + (s + 1) * n] = pi[s] * emerg_mult * price * DT
    # 不等式 δ_{s,k} + g_k + dch_k - ch_k >= L̂_k f^L_s - Ŝ_k f^SV_s
    nr = ns * n
    ri = np.repeat(np.arange(nr), 4)
    base = np.tile(np.arange(n), ns)
    ci = np.empty(nr * 4, dtype=np.int64)
    ci[0::4] = base
    ci[1::4] = base + n
    ci[2::4] = base + 2 * n
    ci[3::4] = np.arange(nr) + off_d
    va = np.empty(nr * 4)
    va[0::4] = -1.0
    va[1::4] = 1.0
    va[2::4] = -1.0
    va[3::4] = -1.0
    Aub = csr_matrix((va, (ri, ci)), shape=(nr, nv))
    bub = (S_fc[None, :] * pv_fac[:, None] - L_fc[None, :] * load_fac[:, None]).ravel()
    # SOC 等式：E_{k+1} - E_k - eta*dt*ch_k + dt/eta*dch_k = 0；首行 E_0 = e0
    er = np.repeat(np.arange(n), 4)
    ec = np.empty(4 * n, dtype=np.int64)
    ec[0::4] = 3 * n + np.arange(n) + 1
    ec[1::4] = 3 * n + np.arange(n)
    ec[2::4] = n + np.arange(n)
    ec[3::4] = 2 * n + np.arange(n)
    ev = np.empty(4 * n)
    ev[0::4] = 1.0
    ev[1::4] = -1.0
    ev[2::4] = -ETA * DT
    ev[3::4] = DT / ETA
    Aeq = csr_matrix((np.append(ev, 1.0), (np.append(er, n), np.append(ec, 3 * n))),
                     shape=(n + 1, nv))
    beq = np.zeros(n + 1)
    beq[n] = float(e0)
    lb = np.zeros(nv)
    ub = np.full(nv, np.inf)
    ub[n:3 * n] = PMAX
    lb[3 * n:4 * n + 1] = EMIN
    ub[3 * n:4 * n + 1] = EMAX
    res = linprog(c, A_ub=Aub, b_ub=bub, A_eq=Aeq, b_eq=beq,
                  bounds=list(zip(lb, ub)), method='highs')
    if not res.success:
        raise RuntimeError(f'随机LP失败: {res.message}')
    x = res.x
    return x[:n], x[n:2 * n], x[2 * n:3 * n], x[3 * n:4 * n + 1], float(res.fun)

def settle_emergency(L_act, S_act, price, g_plan, ch_plan, dch_plan,
                     emerg_mult=5.0, k0=0, k1=N_INT - 1):
    """实际运行结算：按计划充放电，缺口用 5 倍电价紧急购电补足。

    返回 (delta, delta_energy, plan_cost, emerg_cost)：
    delta(kW)、delta_energy(kWh)、计划购电费（全间隔按计划量计价）、紧急购电费。
    """
    L_act = np.asarray(L_act, dtype=float)[k0:k1 + 1]
    S_act = np.asarray(S_act, dtype=float)[k0:k1 + 1]
    price = np.asarray(price, dtype=float)[k0:k1 + 1]
    g_plan = np.asarray(g_plan, dtype=float)[k0:k1 + 1]
    ch_plan = np.asarray(ch_plan, dtype=float)[k0:k1 + 1]
    dch_plan = np.asarray(dch_plan, dtype=float)[k0:k1 + 1]
    delta = np.maximum(0.0, L_act - S_act - g_plan - dch_plan + ch_plan)
    delta_energy = delta * DT
    plan_cost = float(np.sum(price * g_plan) * DT)
    emerg_cost = float(np.sum(emerg_mult * price * delta) * DT)
    return delta, delta_energy, plan_cost, emerg_cost

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
