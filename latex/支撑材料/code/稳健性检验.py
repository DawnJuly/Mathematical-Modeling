# 第六章稳健性/鲁棒性检验：数据摄动 + 不同算法一致性
# 数据摄动：对问题二三段式（预测—随机LP—结算）全年滚动施加乘性高斯噪声，重算 2.1—12.31 购电费
# 算法一致性：离散动态规划(DP) vs 线性规划(LP) 求解问题一单日调度
import sys, os, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from _common import *
from _models import *

price_daily, load1, pv1 = read_附件1()
dates, load_all, pv_all = read_附件2()
N = len(dates)
S = 31          # 2025-02-01 索引；1月为预热期，仅统计 2.1—12.31
PI = np.outer([0.2, 0.6, 0.2], [0.2, 0.6, 0.2]).ravel()   # 9 情景 = 3 负载 × 3 光伏


def run_year_q2(load, pv):
    """问题二三段式全年滚动。返回 (计划购电费, 紧急购电费)（仅累计 2.1—12.31）。
    与 问题二.py 主循环同口径：0:00 只用历史数据预测 → 9 情景两阶段随机 LP → 真值结算。"""
    pool_L, pool_P = [], []
    carry = E0_INIT
    plan_tot = 0.0
    emg_tot = 0.0
    for d in range(N):
        if d == 0:
            continue                                   # 1/1 无任何历史，计划置零
        L_fc = forecast_load(load[:d], dates[:d], dates[d])
        S_fc = forecast_pv(pv[:d])
        fL, fP = scenario_factors(np.concatenate(pool_L) if pool_L else np.array([]),
                                  np.concatenate(pool_P) if pool_P else np.array([]))
        LF = np.repeat(fL, 3); SF = np.tile(fP, 3)
        g, ch, dch, E, _ = solve_daily_stochastic(L_fc, S_fc, price_daily,
                                                  LF, SF, PI, e0=carry)
        _, _, plan_cost, emerg_cost = settle_emergency(load[d], pv[d], price_daily, g, ch, dch)
        if d >= S:
            plan_tot += plan_cost
            emg_tot += emerg_cost
        carry = float(E[-1])
        pool_L.append(pred_residual(L_fc, load[d]))
        m = S_fc > 50.0
        if m.any():
            pool_P.append(((pv[d] - S_fc) / np.maximum(S_fc, 1.0))[m])
    return plan_tot, emg_tot


def run_year_nostorage(load, pv):
    """无储能对照：时段解耦时随机最优计划量满足 P(净负荷>g)=0.2（因边际紧急电价 5 倍），
    g 取 9 情景净负荷的加权 80% 分位；再按真值以 5 倍电价结算缺口。返回总购电费。"""
    pool_L, pool_P = [], []
    tot = 0.0
    for d in range(N):
        if d == 0:
            continue
        L_fc = forecast_load(load[:d], dates[:d], dates[d])
        S_fc = forecast_pv(pv[:d])
        fL, fP = scenario_factors(np.concatenate(pool_L) if pool_L else np.array([]),
                                  np.concatenate(pool_P) if pool_P else np.array([]))
        LF = np.repeat(fL, 3); SF = np.tile(fP, 3)
        net = L_fc[None, :] * LF[:, None] - S_fc[None, :] * SF[:, None]   # (9,144)
        g = np.empty(N_INT)
        for k in range(N_INT):
            o = np.argsort(net[:, k]); w = np.cumsum(PI[o])
            g[k] = net[o[min(int(np.searchsorted(w, 0.8)), 8)], k]
        if d >= S:
            tot += float(np.sum(price_daily * g) * DT)
            gap = np.maximum(0.0, (load[d] - pv[d]) - g)
            tot += float(np.sum(5.0 * price_daily * gap) * DT)
        pool_L.append(pred_residual(L_fc, load[d]))
        m = S_fc > 50.0
        if m.any():
            pool_P.append(((pv[d] - S_fc) / np.maximum(S_fc, 1.0))[m])
    return tot


t0 = time.time()
plan_base, emg_base = run_year_q2(load_all, pv_all)
base = plan_base + emg_base
print(f'基准三段式 2.1—12.31: 计划购电费={plan_base:.2f} 紧急购电费={emg_base:.2f} '
      f'合计={base:.2f} 元（1次全年耗时 {time.time()-t0:.1f}s）')

t0 = time.time()
nostor = run_year_nostorage(load_all, pv_all)
print(f'无储能对照 2.1—12.31 购电费 = {nostor:.2f} 元（耗时 {time.time()-t0:.1f}s，'
      f'相对储能方案 {100*(nostor-base)/base:+.2f}%）')

# ---------- 数据摄动检验 ----------
def perturb_run(sigma, seed):
    r = np.random.default_rng(seed)
    L = np.maximum(load_all * (1.0 + r.normal(0.0, sigma, load_all.shape)), 0.0)
    P = np.maximum(pv_all * (1.0 + r.normal(0.0, sigma, pv_all.shape)), 0.0)
    p, e = run_year_q2(L, P)
    return p + e

pert = {}
for sigma, seeds in [(0.05, 6), (0.10, 3)]:
    vals = np.array([perturb_run(sigma, 1000 + i) for i in range(seeds)])
    pert[sigma] = vals
    print(f'sigma={sigma:.2f}: 均值={vals.mean():.2f} 标准差={vals.std():.2f} '
          f'范围=[{vals.min():.2f},{vals.max():.2f}] 最大偏差=[{100*(vals.min()-base)/base:+.3f}%, {100*(vals.max()-base)/base:+.3f}%]')

# ---------- 算法一致性：离散动态规划(DP) vs LP ----------
def solve_dp(load, pv, price, e0, e_end=None, de=20.0):
    """SOC 网格化动态规划求解单日调度。返回 (最优费用, 末值边界费用向量)。
    e_end=None 自由末值；否则固定末值（问题一的日循环 E0=E24）。"""
    L = np.asarray(load, dtype=float); S = np.asarray(pv, dtype=float)
    pr = np.asarray(price, dtype=float); n = len(L)
    grid = np.arange(EMIN, EMAX + de / 2.0, de)
    ng = len(grid)
    INF = 1e18
    dp = np.full(ng, INF)
    dp[int(round((e0 - EMIN) / de))] = 0.0
    gv = grid.reshape(ng, 1)
    for k in range(n):
        Delta = gv.T - gv                    # Delta[b,a] = SOC_b - SOC_a
        c = np.where(Delta > 0, Delta / (ETA * DT), 0.0)     # 充电功率
        d = np.where(Delta < 0, -Delta * ETA / DT, 0.0)      # 放电功率
        feas = (c <= PMAX + 1e-6) & (d <= PMAX + 1e-6)
        g = np.maximum(L[k] - S[k] - d + c, 0.0)             # 电网购电功率
        cost = g * pr[k] * DT
        cost[~feas] = INF
        dp = np.min(dp[None, :] + cost, axis=1)
    if e_end is None:
        return float(dp.min()), dp
    return float(dp[int(round((e_end - EMIN) / de))]), dp

# 问题一 LP 基准（日循环 E0=E24=6000）
_, _, _, _, lp_cost1 = solve_daily(load1, pv1, price_daily, e0=E0_INIT, soc_cycle=True)
print(f'问题一 LP(日循环) 购电费 = {lp_cost1:.2f} 元')
dp_results = {}
for de in [80.0, 40.0, 20.0]:
    c, _ = solve_dp(load1, pv1, price_daily, E0_INIT, e_end=E0_INIT, de=de)
    dp_results[de] = c
    print(f'问题一 DP(日循环, de={de:.0f}kWh) 购电费 = {c:.2f} 元, 相对LP偏差 {100*(c-lp_cost1)/lp_cost1:+.4f}%')

# 问题一自由末值 LP vs DP（同口径，验证算法一致性，不含日循环）
_, _, _, _, lp_free1 = solve_daily(load1, pv1, price_daily, e0=E0_INIT)
dp_free1, _ = solve_dp(load1, pv1, price_daily, E0_INIT, e_end=None, de=20.0)
print(f'问题一(自由末值): LP={lp_free1:.2f} 元, DP(de=20)={dp_free1:.2f} 元, 偏差 {100*(dp_free1-lp_free1)/lp_free1:+.4f}%')

# 问题一无储能对照：储电量恒为 0，净负荷全部从电网购入，光伏富余计弃电
g_nostor1 = np.maximum(load1 - pv1, 0.0)
nostor1 = float(np.sum(price_daily * g_nostor1) * DT)
print(f'问题一无储能 全天购电费 = {nostor1:.2f} 元, 相对储能方案 {100*(nostor1-lp_cost1)/lp_cost1:+.2f}%')

# ---------- 出图 图6-1 稳健性检验 ----------
C1, C2, C3, C4, C6 = '#2E5FA3', '#E07B39', '#3BA272', '#C0504D', '#D4A017'
plt.rcParams.update({'figure.dpi': 150, 'savefig.dpi': 300, 'axes.unicode_minus': False})

def style_ax(ax, xlabel=None, ylabel=None):
    ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
    ax.tick_params(direction='in', labelsize=9)
    for s in ['bottom', 'left']:
        ax.spines[s].set_linewidth(0.9)
    if xlabel: ax.set_xlabel(xlabel, fontsize=10)
    if ylabel: ax.set_ylabel(ylabel, fontsize=10)

fig, axes = plt.subplots(1, 2, figsize=(13.6, 5.0))

# (a) 数据摄动
ax = axes[0]
means = [base, pert[0.05].mean(), pert[0.10].mean()]
stds = [0.0, pert[0.05].std(), pert[0.10].std()]
xs = np.arange(3)
ax.bar(xs, [m / 1e4 for m in means], width=0.5, yerr=[s / 1e4 for s in stds],
       capsize=5, color=[C1, C3, C4], edgecolor='black', lw=0.8, ecolor='black', error_kw=dict(lw=1.0))
for i, m in enumerate(means):
    ax.text(i, m / 1e4 + 18, f'{m/1e4:.1f}', ha='center', fontsize=9)
ax.set_xticks(xs); ax.set_xticklabels(['基准\n($\\sigma$=0)', '$\\sigma$=5%', '$\\sigma$=10%'], fontsize=9)
style_ax(ax, '摄动强度', '2.1—12.31购电费 (万元)')
ax.text(0.02, 0.02, '(a) 负荷/光伏数据摄动', transform=ax.transAxes, fontsize=10, fontweight='bold')

# (b) 算法一致性：LP vs DP（不同网格）
ax = axes[1]
x2 = np.arange(4)
vals2 = [lp_cost1 / 1e4, dp_results[80.0] / 1e4, dp_results[40.0] / 1e4, dp_results[20.0] / 1e4]
col2 = [C1, C6, C6, C6]
ax.bar(x2, vals2, width=0.55, color=col2, edgecolor='black', lw=0.8)
for i, v in enumerate(vals2):
    ax.text(i, v + 0.06, f'{v:.2f}', ha='center', fontsize=9)
ax.set_xticks(x2)
ax.set_xticklabels(['LP\n(连续)', 'DP\n$\\Delta$=80', 'DP\n$\\Delta$=40', 'DP\n$\\Delta$=20'], fontsize=8.5)
style_ax(ax, None, '问题一全天购电费 (万元)')
ax.text(0.02, 0.02, '(b) 不同算法一致性(LP vs DP)', transform=ax.transAxes, fontsize=10, fontweight='bold')

save_fig(fig, '图6-1_稳健性检验')
print('图6-1 已保存')

# 汇总打印（供 LaTeX 表取值）
print('\n===== 稳健性检验汇总 =====')
print(f'base={base:.2f} (计划={plan_base:.2f} 紧急={emg_base:.2f})')
print(f'nostorage={nostor:.2f} dev={100*(nostor-base)/base:+.3f}')
print(f'nostorage1={nostor1:.2f} dev={100*(nostor1-lp_cost1)/lp_cost1:+.3f}')
for sigma in [0.05, 0.10]:
    v = pert[sigma]
    print(f'sigma{sigma}: mean={v.mean():.2f} std={v.std():.2f} maxdev_up={100*(v.max()-base)/base:.3f} maxdev_dn={100*(v.min()-base)/base:.3f}')
print(f'lp_cost1={lp_cost1:.2f}')
for de in [80.0, 40.0, 20.0]:
    print(f'dp_de{de:.0f}={dp_results[de]:.2f} dev={100*(dp_results[de]-lp_cost1)/lp_cost1:.3f}')
print(f'lp_free1={lp_free1:.2f} dp_free1={dp_free1:.2f} dev={100*(dp_free1-lp_free1)/lp_free1:.3f}')
