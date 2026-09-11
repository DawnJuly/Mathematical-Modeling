# 第六章稳健性/鲁棒性检验：数据摄动 + 不同算法一致性
# 数据摄动：对问题二全年负荷/光伏施加乘性高斯噪声，重算 2.1—12.31 购电费
# 算法一致性：离散动态规划(DP) vs 线性规划(LP) 求解问题一单日调度
import sys, os, time
HERE = os.path.dirname(os.path.abspath(__file__))
SOLVE = HERE
sys.path.insert(0, SOLVE)
from _common import *
from _models import *

price_daily, load1, pv1 = read_附件1()
dates, load_all, pv_all = read_附件2()
N = len(dates)
S = 31          # 2025-02-01 索引；1月为预热期，仅统计 2.1—12.31

def run_year_lp(load, pv):
    """问题二全年滚动（自由末值），返回 2.1—12.31 购电费合计"""
    carry = E0_INIT
    tot = 0.0
    for d in range(N):
        _, _, _, E, c = solve_daily(load[d], pv[d], price_daily, e0=carry)
        if d >= S:
            tot += c
        carry = float(E[-1])
    return tot

t0 = time.time()
base = run_year_lp(load_all, pv_all)
print(f'基准 LP 2.1—12.31 购电费 = {base:.2f} 元（1次全年耗时 {time.time()-t0:.1f}s）')

# ---------- 数据摄动检验 ----------
def perturb_run(sigma, seed):
    r = np.random.default_rng(seed)
    L = load_all * (1.0 + r.normal(0.0, sigma, load_all.shape))
    P = pv_all * (1.0 + r.normal(0.0, sigma, pv_all.shape))
    return run_year_lp(L, P)

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
print(f'base={base:.2f}')
for sigma in [0.05, 0.10]:
    v = pert[sigma]
    print(f'sigma{sigma}: mean={v.mean():.2f} std={v.std():.2f} maxdev_up={100*(v.max()-base)/base:.3f} maxdev_dn={100*(v.min()-base)/base:.3f}')
print(f'lp_cost1={lp_cost1:.2f}')
for de in [80.0, 40.0, 20.0]:
    print(f'dp_de{de:.0f}={dp_results[de]:.2f} dev={100*(dp_results[de]-lp_cost1)/lp_cost1:.3f}')
print(f'lp_free1={lp_free1:.2f} dp_free1={dp_free1:.2f} dev={100*(dp_free1-lp_free1)/lp_free1:.3f}')
