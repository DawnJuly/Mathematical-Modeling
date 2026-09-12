# 问题二：每天电价相同，负载与光伏随时间变化；0:00 预测 — 决策 — 结算 三段式
# ① 预测段：0:00 用历史数据滚动预测当日负载与光伏（绝不用当日真值）
# ② 决策段：不确定下的两阶段随机 LP 定计划购电量与充放电计划
# ③ 结算段：按计划执行，实际缺口以 5 倍电价紧急购电补足，富余弃电
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
SOLVE = os.path.dirname(HERE)
sys.path.insert(0, SOLVE)
from _common import *
from _models import *

price_daily, _, _ = read_附件1()          # 每日相同电价（附件1，日内随时段波动）
dates, load_all, pv_all = read_附件2()
N = len(dates)
S = 31                                     # 2025-02-01 索引；1 月作预测模型预热与情景标定窗口
SPEC = ['2025-03-20', '2025-06-21', '2025-09-23', '2025-12-21']
idx_map = {}
for i, dd in enumerate(dates):
    ds = f'{dd.year:04d}-{dd.month:02d}-{dd.day:02d}'
    if ds in SPEC:
        idx_map[ds] = i
assert len(idx_map) == 4, f'指定日期缺失: {idx_map}'
print('附件2 日期范围:', dates[0].date(), '→', dates[-1].date(), '天数', N)
print(f'统计口径: 2025-02-01 → 2025-12-31 共 {N - S} 天；1 月为预热期')

# ---------- 三段式逐日滚动 ----------
g_all = np.zeros((N, N_INT)); ch_all = np.zeros((N, N_INT)); dch_all = np.zeros((N, N_INT))
dl_all = np.zeros((N, N_INT)); su_all = np.zeros((N, N_INT))          # 紧急购电(kW)、弃电(kWh)
E_all = np.zeros((N, N_INT + 1))
plan_all = np.zeros(N); emg_all = np.zeros(N)                          # 日计划费、日紧急费(元)
Lf_all = np.full((N, N_INT), np.nan); Sf_all = np.full((N, N_INT), np.nan)
fL_all = np.full((N, 3), np.nan); fP_all = np.full((N, 3), np.nan)
res_pool_L, res_pool_P = [], []
PI = np.outer([0.2, 0.6, 0.2], [0.2, 0.6, 0.2]).ravel()               # 9 情景 = 3 负载 × 3 光伏
carry = E0_INIT
for d in range(N):
    if d == 0:
        # 1/1 0:00 尚无任何历史数据，计划量置零，储电量全天保持 6000 kWh
        E_all[d] = np.full(N_INT + 1, E0_INIT)
        continue
    L_fc = forecast_load(load_all[:d], dates[:d], dates[d])
    S_fc = forecast_pv(pv_all[:d])
    fL, fP = scenario_factors(np.concatenate(res_pool_L) if res_pool_L else np.array([]),
                              np.concatenate(res_pool_P) if res_pool_P else np.array([]))
    LF = np.repeat(fL, 3); SF = np.tile(fP, 3)
    g, ch, dch, E, _ = solve_daily_stochastic(L_fc, S_fc, price_daily, LF, SF, PI, e0=carry)
    delta, _, plan_cost, emerg_cost = settle_emergency(load_all[d], pv_all[d], price_daily, g, ch, dch)
    g_all[d], ch_all[d], dch_all[d], E_all[d] = g, ch, dch, E
    dl_all[d] = delta; plan_all[d] = plan_cost; emg_all[d] = emerg_cost
    su_all[d] = np.maximum(0.0, pv_all[d] + g + dch - ch - load_all[d]) * DT
    Lf_all[d], Sf_all[d], fL_all[d], fP_all[d] = L_fc, S_fc, fL, fP
    carry = float(E[-1])
    # 把当日"事前预测—事后实际"的残差并入标定池，供次日及以后使用
    res_pool_L.append(pred_residual(L_fc, load_all[d]))
    m = S_fc > 50.0
    if m.any():
        res_pool_P.append(((pv_all[d] - S_fc) / np.maximum(S_fc, 1.0))[m])

# ---------- 汇总指标（2.1—12.31） ----------
gE = g_all * DT; chE = ch_all * DT; dchE = dch_all * DT
W = slice(S, N); nW = N - S
plan_kwh = float(gE[W].sum()); plan_fee = float(plan_all[W].sum())
emg_kwh = float(dl_all[W].sum() * DT); emg_fee = float(emg_all[W].sum())
tot_fee = plan_fee + emg_fee
n_emg_int = int((dl_all[W].reshape(-1) > 1e-6).sum())
n_emg_day = int((dl_all[W].sum(axis=1) > 1e-6).sum())
net_kwh = float((load_all[W] - pv_all[W]).sum() * DT)
print(f'\n[计划段] 计划购电量={plan_kwh:.2f} kWh, 计划购电费={plan_fee:.2f} 元')
print(f'[紧急段] 紧急购电量={emg_kwh:.2f} kWh, 紧急购电费={emg_fee:.2f} 元')
print(f'[合计]   总购电费={tot_fee:.2f} 元, 日均={tot_fee / nW:.2f} 元')
print(f'[紧急覆盖面] 非零间隔={n_emg_int} 个 ({n_emg_int / (nW * N_INT) * 100:.2f}%), '
      f'发生天数={n_emg_day} 天 ({n_emg_day / nW * 100:.2f}%)')
print(f'[紧急强度] 最大功率={dl_all[W].max():.2f} kW, 单日最大电量={float((dl_all[W].sum(axis=1) * DT).max()):.2f} kWh')
print(f'[储能] 2/1 0:00 SOC={E_all[S, 0]:.2f}, 12/31 24:00 SOC={E_all[N - 1, -1]:.2f}, '
      f'SOC 最小={E_all[W, :].min():.2f}, SOC 最大={E_all[W, :].max():.2f}')
print(f'[能量流] 净负荷={net_kwh:.2f} kWh, 放电量={float(dchE[W].sum()):.2f} kWh, '
      f'充电量={float(chE[W].sum()):.2f} kWh, 弃电={float(su_all[W].sum()):.2f} kWh')
bal = net_kwh - plan_kwh - float(dchE[W].sum()) + float(chE[W].sum())
print(f'[自洽校验] 净负荷-计划-放电+充电={bal:.2f} = 紧急电量({emg_kwh:.2f}) - 弃电({float(su_all[W].sum()):.2f})')

# ---------- 预测精度（2.1—12.31 窗口内 out-of-sample） ----------
err_L = (load_all - Lf_all)[W].reshape(-1); err_P = (pv_all - Sf_all)[W].reshape(-1)
rel_L = ((load_all - Lf_all) / np.maximum(Lf_all, 1.0))[W].reshape(-1)
maskP = (Sf_all[W] > 50.0).reshape(-1)
rel_P = ((pv_all - Sf_all) / np.maximum(Sf_all, 1.0))[W].reshape(-1)[maskP]
q = np.arange(0, 101, 10)
print(f'\n[预测精度] 负载 MAE={np.mean(np.abs(err_L)):.2f} kW, RMSE={np.sqrt(np.mean(err_L ** 2)):.2f} kW')
print(f'           光伏 MAE={np.mean(np.abs(err_P)):.2f} kW, RMSE={np.sqrt(np.mean(err_P ** 2)):.2f} kW')
print(f'           负载相对误差分位(%)=[{", ".join(f"{v:.2f}" for v in np.percentile(rel_L, q) * 100)}], '
      f'std={np.std(rel_L) * 100:.2f}%')
print(f'           光伏相对误差分位(%)=[{", ".join(f"{v:.2f}" for v in np.percentile(rel_P, q) * 100)}] '
      f'(样本 {maskP.sum()}), std={np.std(rel_P) * 100:.2f}%')
for nm, arr in (('负载', fL_all[S:]), ('光伏', fP_all[S:])):
    print(f'[情景因子] {nm} 低/中/高 均值=[{", ".join(f"{v:.4f}" for v in arr.mean(axis=0))}], '
          f'低档 min/median/max={arr[:, 0].min():.4f}/{np.median(arr[:, 0]):.4f}/{arr[:, 0].max():.4f}, '
          f'高档 min/median/max={arr[:, 2].min():.4f}/{np.median(arr[:, 2]):.4f}/{arr[:, 2].max():.4f}')

# ---------- 表1 / 表2 / 表3：四个指定日期 ----------
def merge_runs(delta, thr=1e-6):
    """把非零紧急购电的连续间隔合并为 (起时刻, 止时刻, 电量kWh)。"""
    labs = interval_labels(); out = []; i = 0; n = len(delta)
    while i < n:
        if delta[i] > thr:
            j = i
            while j + 1 < n and delta[j + 1] > thr:
                j += 1
            out.append((labs[i].split('-')[0], labs[j].split('-')[1].replace('+1', ''),
                        float(np.sum(delta[i:j + 1]) * DT)))
            i = j + 1
        else:
            i += 1
    return out

print('\n===== 表1 微网在指定时间段的购电量及全天的购电量和购电费（计划） =====')
print('日期        10:00-10:10 12:00-12:10 14:00-14:10 16:00-16:10 18:00-18:10 20:00-20:10 全天购电量 全天购电费')
tab1 = {}
for sd in SPEC:
    d = idx_map[sd]; gd = gE[d]
    vals = [float(gd[h * 6]) for h in (10, 12, 14, 16, 18, 20)]
    tot = float(gd.sum())
    tab1[sd] = (vals, tot, float(plan_all[d]), float(emg_all[d]), float(dl_all[d].sum() * DT))
    print(f'{sd}  ' + ' '.join(f'{v:10.2f}' for v in vals) + f' {tot:9.2f} {plan_all[d]:10.2f}'
          f'  [紧急 {float(dl_all[d].sum() * DT):.2f} kWh / {emg_all[d]:.2f} 元]')

print('\n===== 表2 储能设备在指定时间段的充放电量及0:00和24:00的储电量 =====')
tab2 = {}
for sd in SPEC:
    d = idx_map[sd]; ce = chE[d]; de = dchE[d]
    segs = []
    for a, b in [(0, 4), (4, 8), (8, 12), (12, 16), (16, 20), (20, 24)]:
        k0, k1 = a * 6, b * 6 - 1
        segs.append((f'{a:02d}:00-{b:02d}:00', float(ce[k0:k1 + 1].sum()), float(de[k0:k1 + 1].sum())))
    tab2[sd] = (segs, float(E_all[d, 0]), float(E_all[d, -1]))
    print(f'  {sd}  0:00储电量={E_all[d, 0]:.2f}  24:00储电量={E_all[d, -1]:.2f}')
    for nm, c, dn in segs:
        print(f'    {nm}  充电量={c:9.2f}  放电量={dn:9.2f}')

print('\n===== 表3 微网在指定日期的紧急购电量 =====')
tab3 = {}
for sd in SPEC:
    d = idx_map[sd]
    runs = merge_runs(dl_all[d])
    tab3[sd] = runs
    tot = float(dl_all[d].sum() * DT)
    if not runs:
        print(f'  {sd}: 无紧急购电')
    else:
        print(f'  {sd}: 合计 {tot:.2f} kWh, 共 {len(runs)} 段')
        for a, b, e in runs:
            print(f'    {a}-{b}  {e:.2f} kWh')

# ---------- 预处理：缺失/异常检查 ----------
miss = int(np.isnan(load_all).sum() + np.isnan(pv_all).sum())
print(f'\n附件2 缺失值总数={miss}, 负载范围=[{load_all.min():.1f},{load_all.max():.1f}] kW, '
      f'光伏范围=[{pv_all.min():.1f},{pv_all.max():.1f}] kW')

# ---------- 出图 ----------
t = np.arange(N_INT) / 6.0
C1, C2, C3, C4, C5 = '#2E5FA3', '#E07B39', '#3BA272', '#C0504D', '#8A6BBE'
dw = np.array([dates[d] for d in range(S, N)])

def style_ax(ax, xlabel=None, ylabel=None):
    ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
    ax.tick_params(direction='in', labelsize=9)
    for s in ['bottom', 'left']:
        ax.spines[s].set_linewidth(0.9)
    if xlabel: ax.set_xlabel(xlabel, fontsize=10)
    if ylabel: ax.set_ylabel(ylabel, fontsize=10)

def tag(ax, s, bold=True):
    ax.text(0.02, 0.02, s, transform=ax.transAxes, fontsize=9,
            fontweight='bold' if bold else 'normal')

# 图2-1 预处理前后对比（附件2 全年完整性 + 样本日对齐）
fig, axes = plt.subplots(1, 3, figsize=(15.6, 5.0))
d0 = idx_map['2025-03-20']
ax = axes[0]
ax.plot(dates, load_all.max(axis=1), '.', ms=3, color=C2, alpha=0.5, label='负载峰值')
ax.plot(dates, pv_all.max(axis=1), '.', ms=3, color=C3, alpha=0.5, label='光伏峰值')
style_ax(ax, '日期', '功率峰值 (kW)')
ax.legend(fontsize=8, loc='upper right', framealpha=0.9)
ax = axes[1]
daily_na = np.isnan(load_all).sum(axis=1) + np.isnan(pv_all).sum(axis=1)
ax.bar(np.arange(12), [int(daily_na[m::12].sum()) for m in range(12)], color=C1, edgecolor='black', lw=0.5)
ax.set_xticks(np.arange(12)); ax.set_xticklabels([f'{m + 1}月' for m in range(12)], fontsize=8)
style_ax(ax, '月份', '缺失值计数')
ax = axes[2]
ax.plot(np.arange(N_INT + 1) / 6.0, np.append(load_all[d0], load_all[d0, 0]), '-', color='#9AA5B1', lw=1.2, label='原始时间点')
ax.plot(t, load_all[d0], '-', color=C2, lw=1.8, label='间隔对齐')
style_ax(ax, '小时', '负载 (kW)')
ax.legend(fontsize=8, loc='upper right', framealpha=0.9)
for ax_, tg, name in zip(axes, 'abc', ['全年数据完整性', '缺失值月度分布', '样本日负载对齐']):
    tag(ax_, f'({tg}) {name}')
save_fig(fig, '图2-1_预处理前后对比')

# 图2-2 2.1—12.31 逐日购电费（计划 + 紧急 叠加柱）
fig, ax = plt.subplots(figsize=(11.5, 5.2))
pv_e = plan_all[S:]; ev_e = emg_all[S:]
ax.bar(dw, pv_e, width=0.85, color=C1, edgecolor='black', lw=0.15, label='计划购电费')
ax.bar(dw, ev_e, bottom=pv_e, width=0.85, color=C4, edgecolor='black', lw=0.15, label='紧急购电费')
ax.plot(dw, pd.Series(pv_e + ev_e).rolling(7, center=True).mean(), color='black', lw=1.6, label='总费用7日滑动平均')
style_ax(ax, '日期', '购电费 (元)')
ax.legend(fontsize=9, loc='upper left', framealpha=0.9)
tag(ax, '(a) 2.1—12.31逐日购电费构成')
save_fig(fig, '图2-2_全年逐日购电费')

# 图2-3 四季典型日购电功率（计划 + 紧急 叠加柱）
fig, axes = plt.subplots(1, 4, figsize=(15.6, 4.6))
for ax, sd, col in zip(axes, SPEC, [C1, C3, C4, C2]):
    d = idx_map[sd]
    ax.bar(t, g_all[d], width=0.14, color=col, alpha=0.85, edgecolor='black', lw=0.4, label='计划')
    ax.bar(t, dl_all[d], bottom=g_all[d], width=0.14, color=C5, alpha=0.9, edgecolor='black', lw=0.4, label='紧急')
    ax.set_xticks(np.arange(0, 25, 6)); style_ax(ax, '小时', '购电 (kW)')
    top = max(g_all[d].max(), (g_all[d] + dl_all[d]).max()) * 1.18
    ax.set_ylim(0, top)
    tag(ax, f'({sd[5:]})')
axes[0].legend(fontsize=8, loc='upper left', framealpha=0.9)
save_fig(fig, '图2-3_四季典型日购电策略')

# 图2-4 四季典型日SOC轨迹
fig, axes = plt.subplots(1, 4, figsize=(15.6, 4.6))
for ax, sd, col in zip(axes, SPEC, [C1, C3, C4, C2]):
    d = idx_map[sd]
    ax.plot(t, E_all[d, :N_INT], color=col, lw=1.8)
    ax.fill_between(t, EMIN, E_all[d, :N_INT], color=col, alpha=0.12)
    ax.axhline(EMIN, color='#7A7A7A', lw=0.8, ls=':'); ax.axhline(EMAX, color='#7A7A7A', lw=0.8, ls=':')
    ax.set_xticks(np.arange(0, 25, 6)); style_ax(ax, '小时', '储电量 (kWh)')
    ax.set_ylim(EMIN - 400, EMAX + 400)
    tag(ax, f'({sd[5:]})')
save_fig(fig, '图2-4_四季典型日SOC轨迹')

# 图2-5 储能SOC月度分布（2—12月，箱线）
fig, ax = plt.subplots(figsize=(11.5, 5.2))
monthly = [[E_all[d, 0] for d in range(S, N) if dates[d].month == m] for m in range(2, 13)]
bp = safe_boxplot(ax, monthly, [f'{m}月' for m in range(2, 13)])
cols = get_colors('tab20', 11)
for i, b in enumerate(bp['boxes']):
    b.set_facecolor(cols[i]); b.set_edgecolor('black'); b.set_linewidth(0.9)
for med in bp['medians']:
    med.set_color('black'); med.set_linewidth(1.2)
style_ax(ax, '月份', '每日0:00储电量 (kWh)')
ax.axhline(EMIN, color='#7A7A7A', lw=0.8, ls=':')
tag(ax, '(a) 2—12月0:00储电量月度分布')
save_fig(fig, '图2-5_全年储能SOC月度分布')

# 图2-6 购电量与净负荷关系 + 月度购电费构成
fig, axes = plt.subplots(1, 2, figsize=(15.6, 5.4))
ax = axes[0]
net_all = (load_all - pv_all).mean(axis=1)
ax.scatter(net_all[S:], g_all.mean(axis=1)[S:], s=10, c=(plan_all + emg_all)[S:], cmap='RdYlGn_r',
           edgecolor='black', lw=0.3)
style_ax(ax, '日均净负荷 (kW)', '日均计划购电功率 (kW)')
cb = fig.colorbar(ax.collections[0], ax=ax, fraction=0.046, pad=0.04)
cb.set_label('购电费 (元)', fontsize=9); cb.ax.tick_params(labelsize=8)
ax = axes[1]
months = np.arange(2, 13)
mp = np.array([plan_all[[d for d in range(S, N) if dates[d].month == m]].sum() / 1e4 for m in months])
me = np.array([emg_all[[d for d in range(S, N) if dates[d].month == m]].sum() / 1e4 for m in months])
ax.bar(months - 0.18, mp, width=0.36, color=C1, edgecolor='black', lw=0.5, label='计划购电费')
ax.bar(months + 0.18, me, width=0.36, color=C4, edgecolor='black', lw=0.5, label='紧急购电费')
ax.set_xticks(months); ax.set_xticklabels([f'{m}月' for m in months], fontsize=9)
style_ax(ax, '月份', '月度购电费 (万元)')
ax.legend(fontsize=9, loc='upper left', framealpha=0.9)
tag(axes[0], '(a) 购电量-净负荷关系'); tag(ax, '(b) 月度购电费构成')
save_fig(fig, '图2-6_购电量与净负荷关系')

# 图2-7 预测与实际对比（上排负载、下排光伏，四个指定日）
fig, axes = plt.subplots(2, 4, figsize=(15.6, 7.6))
for j, sd in enumerate(SPEC):
    d = idx_map[sd]
    ax = axes[0, j]
    ax.plot(t, load_all[d], color=C2, lw=1.6, label='实际')
    ax.plot(t, Lf_all[d], color=C1, lw=1.4, ls='--', label='0:00预测')
    ax.set_xticks(np.arange(0, 25, 6)); style_ax(ax, '小时', '负载 (kW)' if j == 0 else None)
    tag(ax, f'({chr(97 + j)}) {sd[5:]} 负载')
    if j == 0: ax.legend(fontsize=8, loc='upper right', framealpha=0.9)
    ax = axes[1, j]
    ax.plot(t, pv_all[d], color=C3, lw=1.6, label='实际')
    ax.plot(t, Sf_all[d], color=C1, lw=1.4, ls='--', label='0:00预测')
    ax.set_xticks(np.arange(0, 25, 6)); style_ax(ax, '小时', '光伏 (kW)' if j == 0 else None)
    tag(ax, f'({chr(101 + j)}) {sd[5:]} 光伏')
save_fig(fig, '图2-7_预测与实际对比')

# 图2-8 预测误差分布
fig, axes = plt.subplots(1, 2, figsize=(15.6, 5.2))
ax = axes[0]
bp = safe_boxplot(ax, [rel_L * 100, rel_P * 100], ['负载', '光伏'], whis=(5, 95), showfliers=False)
for b, c in zip(bp['boxes'], [C1, C3]):
    b.set_facecolor(c); b.set_edgecolor('black'); b.set_linewidth(0.9)
for med in bp['medians']:
    med.set_color('black'); med.set_linewidth(1.2)
ax.axhline(0, color='#7A7A7A', lw=0.8, ls=':')
style_ax(ax, '预测量', '相对预测误差 (%)')
tag(ax, '(a) 相对误差箱线（5—95分位）')
ax = axes[1]
ax.plot(q, np.percentile(rel_L, q) * 100, '-o', ms=3, color=C1, lw=1.6, label='负载')
ax.plot(q, np.percentile(rel_P, q) * 100, '-s', ms=3, color=C3, lw=1.6, label='光伏')
ax.axhline(0, color='#7A7A7A', lw=0.8, ls=':')
style_ax(ax, '分位数 (%)', '相对误差 (%)')
ax.legend(fontsize=9, loc='upper left', framealpha=0.9)
tag(ax, '(b) 相对误差分位曲线')
save_fig(fig, '图2-8_预测误差分布')

# 图2-9 紧急购电分布
fig, axes = plt.subplots(1, 2, figsize=(15.6, 5.4))
ax = axes[0]
ax.bar(dw, dl_all[S:].sum(axis=1) * DT, width=0.85, color=C4, edgecolor='black', lw=0.15)
style_ax(ax, '日期', '紧急购电量 (kWh/日)')
tag(ax, '(a) 逐日紧急购电量')
ax = axes[1]
hm = np.zeros((12, 24))
for d in range(S, N):
    for k in range(N_INT):
        hm[dates[d].month - 1, k // 6] += dl_all[d, k] * DT
mesh = safe_heatmap(ax, hm, row_labels=[f'{m}月' for m in range(1, 13)],
                    col_labels=[f'{h}时' for h in range(24)], cmap='YlOrRd', fontsize=7)
cb = fig.colorbar(mesh, ax=ax, fraction=0.046, pad=0.04)
cb.set_label('紧急购电量 (kWh)', fontsize=9); cb.ax.tick_params(labelsize=8)
style_ax(ax, '时段', '月份')
tag(ax, '(b) 月份-时段紧急购电量', bold=False)
save_fig(fig, '图2-9_紧急购电分布')

# ---------- 写 result2.xlsx ----------
from openpyxl import Workbook
wb = Workbook()
ws = wb.active; ws.title = '计划购电量'
labs = template_labels('0:00-0:10+1')
ws.append(['日期\\时间'] + labs + ['全天购电量', '全天购电费'])
for d in range(S, N):
    ws.append([dates[d]] + [round(float(x), 4) for x in gE[d]]
              + [round(float(gE[d].sum()), 4), round(float(plan_all[d]), 4)])
ws2 = wb.create_sheet('充放电量')
ws2.append(['日期', '时间段', '充电量', '放电量', '时刻', '储电量'])
from datetime import time as _midnight
for d in range(S, N):
    for bi in range(len(TPL_BIN_LABELS)):
        k0, k1 = bi * 24, bi * 24 + 23
        cq = round(float(chE[d, k0:k1 + 1].sum()), 4); dq = round(float(dchE[d, k0:k1 + 1].sum()), 4)
        if bi == 0:
            ws2.append([dates[d], TPL_BIN_LABELS[bi], cq, dq, _midnight(0, 0), round(float(E_all[d, 0]), 4)])
        elif bi == 1:
            ws2.append([None, TPL_BIN_LABELS[bi], cq, dq, '24:00', round(float(E_all[d, -1]), 4)])
        else:
            ws2.append([None, TPL_BIN_LABELS[bi], cq, dq, None, None])
ws3 = wb.create_sheet('紧急购电量')
ws3.append(['日期', '紧急购电时间段', '紧急购电量'])
for d in range(S, N):
    runs = merge_runs(dl_all[d])
    if not runs:
        ws3.append([dates[d], None, None])
        continue
    for i, (a, b, e) in enumerate(runs):
        ws3.append([dates[d] if i == 0 else None, f'{a}-{b}', round(e, 4)])
for path in (os.path.join(ROOT_OUT, 'result2.xlsx'), os.path.join(OUT_DIR, 'result2.xlsx')):
    wb.save(path)
print(f'\n已保存 result2.xlsx（{nW} 天，3 张工作表）→ 求解/结果/ 与 问题二/结果/')
