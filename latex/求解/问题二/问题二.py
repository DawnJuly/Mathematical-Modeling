# 问题二：每天电价相同，负载与光伏随时间变化，逐日0:00计划购电（紧急购电5倍价）
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
SOLVE = os.path.dirname(HERE)
sys.path.insert(0, SOLVE)
from _common import *
from _models import *

price_daily, _, _ = read_附件1()      # 每日相同电价（附件1）
dates, load_all, pv_all = read_附件2()
print('附件2 日期范围:', dates[0].date(), '→', dates[-1].date(), '天数', len(dates))

# ---------- 全年逐日 LP 滚动 ----------
N = len(dates)
S = 31   # 2025-02-01 索引；附件5仅要求保存 2.1—12.31，1月作为预热期，不纳入汇总统计
g_all = np.zeros((N, N_INT)); ch_all = np.zeros((N, N_INT)); dch_all = np.zeros((N, N_INT))
E_all = np.zeros((N, N_INT + 1)); cost_all = np.zeros(N)
carry = E0_INIT
for d in range(N):
    g, ch, dch, E, c = solve_daily(load_all[d], pv_all[d], price_daily, e0=carry)
    g_all[d], ch_all[d], dch_all[d], E_all[d], cost_all[d] = g, ch, dch, E, c
    carry = float(E[-1])
print(f'全年(365天,含1月预热)购电费合计={cost_all.sum():.2f} 元')
print(f'[汇总口径] 2.1—12.31 购电费合计={cost_all[S:].sum():.2f} 元, 日均={cost_all[S:].mean():.2f} 元, 天数={N-S}')
print(f'2025-02-01 0:00 SOC={E_all[S,0]:.2f}, 全年SOC下限均值={E_all[:,0].mean():.2f}, 末SOC={carry:.2f}')

# 表3 指定四天 + 表1/表2
idx_map = {pd.Timestamp('2025-03-20'): None, pd.Timestamp('2025-06-21'): None,
           pd.Timestamp('2025-09-23'): None, pd.Timestamp('2025-12-21'): None}
for d in range(N):
    dd = pd.Timestamp(dates[d]).date()
    for k in list(idx_map.keys()):
        if dd == k.date():
            idx_map[k] = d
spec_days = ['2025-03-20', '2025-06-21', '2025-09-23', '2025-12-21']
print('\n表1/表2 指定日期结果:')
for sd in spec_days:
    d = idx_map[pd.Timestamp(sd)]
    gE = g_all[d] * DT
    print(f'  {sd}: 全天购电量={gE.sum():.2f} kWh, 购电费={cost_all[d]:.2f} 元, SOC0={E_all[d,0]:.2f}, SOC24={E_all[d,-1]:.2f}')
    for hh in [10, 12, 14, 16, 18, 20]:
        k = hh * 6
        print(f'     {hh:02d}:00-{hh:02d}:10 购电量={gE[k]:.2f}')

# ---------- 预处理：缺失/异常检查 ----------
miss = np.isnan(load_all).sum() + np.isnan(pv_all).sum()
print(f'附件2 缺失值总数={miss}, 负载范围=[{load_all.min():.1f},{load_all.max():.1f}], 光伏范围=[{pv_all.min():.1f},{pv_all.max():.1f}]')

# ---------- 出图 ----------
t = np.arange(N_INT) / 6.0
C1, C2, C3, C4, C5 = '#2E5FA3', '#E07B39', '#3BA272', '#C0504D', '#8A6BBE'
plt.rcParams.update({'figure.dpi': 150, 'savefig.dpi': 300, 'axes.unicode_minus': False})

def style_ax(ax, xlabel=None, ylabel=None):
    ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
    ax.tick_params(direction='in', labelsize=9)
    for s in ['bottom', 'left']:
        ax.spines[s].set_linewidth(0.9)
    if xlabel: ax.set_xlabel(xlabel, fontsize=10)
    if ylabel: ax.set_ylabel(ylabel, fontsize=10)

# 图2-1 预处理前后对比（附件2 全年完整性 + 样本日对齐）
fig, axes = plt.subplots(1, 3, figsize=(15.6, 5.0))
d0 = idx_map[pd.Timestamp('2025-03-20')]
pv_peak = pv_all.max(axis=1); load_peak = load_all.max(axis=1)
ax = axes[0]
ax.plot(dates, load_peak, '.', ms=3, color=C2, alpha=0.5, label='负载峰值')
ax.plot(dates, pv_peak, '.', ms=3, color=C3, alpha=0.5, label='光伏峰值')
style_ax(ax, '日期', '功率峰值 (kW)')
ax.legend(fontsize=8, loc='upper right', framealpha=0.9)
ax = axes[1]
daily_na = np.isnan(load_all).sum(axis=1) + np.isnan(pv_all).sum(axis=1)
ax.bar(np.arange(12), [int(daily_na[m::12].sum()) for m in range(12)], color=C1, edgecolor='black', lw=0.5)
ax.set_xticks(np.arange(12)); ax.set_xticklabels([f'{m+1}月' for m in range(12)], fontsize=8)
style_ax(ax, '月份', '缺失值计数')
ax = axes[2]
t_raw = np.arange(N_INT + 1) / 6.0
ax.plot(t_raw, np.append(load_all[d0], load_all[d0, 0]), '-', color='#9AA5B1', lw=1.2, label='原始时间点')
ax.plot(t, load_all[d0], '-', color=C2, lw=1.8, label='间隔对齐')
style_ax(ax, '小时', '负载 (kW)')
ax.legend(fontsize=8, loc='upper right', framealpha=0.9)
for ax, tag, name in zip(axes, 'abc', ['全年数据完整性', '缺失值月度分布', '样本日负载对齐']):
    ax.text(0.02, -0.22, f'({tag}) {name}', transform=ax.transAxes, fontsize=10, fontweight='bold')
save_fig(fig, '图2-1_预处理前后对比')

# 图2-2 2.1—12.31 逐日购电费与能量
fig, ax = plt.subplots(figsize=(11.5, 5.2))
ax.plot(dates[S:], cost_all[S:], color=C1, lw=1.0, alpha=0.9, label='逐日购电费')
ax.plot(dates[S:], pd.Series(cost_all[S:]).rolling(7, center=True).mean(), color=C4, lw=1.8, label='7日滑动平均')
style_ax(ax, '日期', '购电费 (元)')
ax.legend(fontsize=9, loc='upper left', framealpha=0.9)
ax.text(0.01, 0.02, '(a) 2.1—12.31逐日购电费', transform=ax.transAxes, fontsize=10, fontweight='bold')
save_fig(fig, '图2-2_全年逐日购电费')

# 图2-3 四季典型日购电功率对比（1×4）
fig, axes = plt.subplots(1, 4, figsize=(15.6, 4.6))
for ax, sd, col in zip(axes, spec_days, [C1, C3, C4, C2]):
    d = idx_map[pd.Timestamp(sd)]
    ax.bar(t, g_all[d], width=0.14, color=col, alpha=0.85, edgecolor='black', lw=0.5)
    ax.set_xticks(np.arange(0, 25, 6)); style_ax(ax, '小时', '购电 (kW)')
    ax.set_ylim(0, g_all[d].max() * 1.12)
    ax.text(0.03, 0.02, f'({sd[5:]})', transform=ax.transAxes, fontsize=9, fontweight='bold')
save_fig(fig, '图2-3_四季典型日购电策略')

# 图2-4 四季典型日SOC轨迹（1×4）
fig, axes = plt.subplots(1, 4, figsize=(15.6, 4.6))
for ax, sd, col in zip(axes, spec_days, [C1, C3, C4, C2]):
    d = idx_map[pd.Timestamp(sd)]
    ax.plot(t, E_all[d, :144], color=col, lw=1.8)
    ax.fill_between(t, EMIN, E_all[d, :144], color=col, alpha=0.12)
    ax.axhline(EMIN, color='#7A7A7A', lw=0.8, ls=':'); ax.axhline(EMAX, color='#7A7A7A', lw=0.8, ls=':')
    ax.set_xticks(np.arange(0, 25, 6)); style_ax(ax, '小时', 'SOC (kWh)')
    ax.set_ylim(EMIN - 400, EMAX + 400)
    ax.text(0.03, 0.02, f'({sd[5:]})', transform=ax.transAxes, fontsize=9, fontweight='bold')
save_fig(fig, '图2-4_四季典型日SOC轨迹')

# 图2-5 储能SOC月度分布（2—12月，箱线）
fig, ax = plt.subplots(figsize=(11.5, 5.2))
monthly = []
for m in range(1, 12):
    idx = [d for d in range(N) if dates[d].month == m + 1]
    soc0 = E_all[idx, 0]
    monthly.append(soc0)
bp = safe_boxplot(ax, monthly, [f'{m+1}月' for m in range(1, 12)])
for i, b in enumerate(bp['boxes']):
    b.set_facecolor(get_colors('tab20', 11)[i]); b.set_edgecolor('black'); b.set_linewidth(0.9)
for med in bp['medians']:
    med.set_color('black'); med.set_linewidth(1.2)
style_ax(ax, '月份', '每日0:00储电量 (kWh)')
ax.axhline(EMIN, color='#7A7A7A', lw=0.8, ls=':')
ax.text(0.01, 0.02, '(a) 2—12月储电量月度分布', transform=ax.transAxes, fontsize=10, fontweight='bold')
save_fig(fig, '图2-5_全年储能SOC月度分布')

# 图2-6 购电量与净负荷关系散点+月度购电量柱（2—12月）
fig, axes = plt.subplots(1, 2, figsize=(15.6, 5.4))
ax = axes[0]
net_all = (load_all - pv_all).mean(axis=1)      # 日均净负荷功率
g_day = g_all.mean(axis=1)
ax.scatter(net_all[S:], g_day[S:], s=10, c=cost_all[S:], cmap='RdYlGn_r', edgecolor='black', lw=0.3)
ax.set_xlabel('日均净负荷 (kW)', fontsize=10); ax.set_ylabel('日均购电功率 (kW)', fontsize=10)
style_ax(ax, '日均净负荷 (kW)', '日均购电功率 (kW)')
cb = fig.colorbar(ax.collections[0], ax=ax, fraction=0.046, pad=0.04)
cb.set_label('购电费 (元)', fontsize=9); cb.ax.tick_params(labelsize=8)
ax = axes[1]
mcost = [cost_all[[d for d in range(N) if dates[d].month == m + 1]].sum() / 10000 for m in range(1, 12)]
ax.bar(np.arange(11), mcost, color=get_colors('tab20', 11), edgecolor='black', lw=0.6)
ax.set_xticks(np.arange(11)); ax.set_xticklabels([f'{m+1}月' for m in range(1, 12)], fontsize=9)
style_ax(ax, '月份', '月度购电费 (万元)')
ax.text(0.02, 0.02, '(b) 月度购电费', transform=ax.transAxes, fontsize=10, fontweight='bold')
ax.text(0.02, 0.02, '(a) 购电量-净负荷关系', transform=axes[0].transAxes, fontsize=10, fontweight='bold')
save_fig(fig, '图2-6_购电量与净负荷关系')

# ---------- 写 result2.xlsx ----------
from openpyxl import Workbook
out = os.path.join(ROOT_OUT, 'result2.xlsx')
wb = Workbook()
# 计划购电量
ws = wb.active; ws.title = '计划购电量'
labs = interval_labels()
ws.append(['日期\\时间'] + labs + ['全天购电量', '全天购电费'])
start = S  # 2025-02-01 索引（附件5：结果仅保存 2.1—12.31）
for d in range(start, N):
    gE = g_all[d] * DT
    row = [dates[d]] + [round(float(x), 4) for x in gE] + [round(float(gE.sum()), 4), round(float(cost_all[d]), 4)]
    ws.append(row)
# 充放电量
ws2 = wb.create_sheet('充放电量')
ws2.append(['日期', '时间段', '充电量', '放电量', '时刻', '储电量'])
for d in range(start, N):
    chE = ch_all[d] * DT; dchE = dch_all[d] * DT
    for bi, (a, b) in enumerate([(0, 4), (4, 8), (8, 12), (12, 16), (16, 20), (20, 24)]):
        k0, k1 = a * 6, b * 6 - 1
        cq = round(float(chE[k0:k1 + 1].sum()), 4); dq = round(float(dchE[k0:k1 + 1].sum()), 4)
        if bi == 0:
            ws2.append([dates[d], f'{a:02d}:00-{b:02d}:00', cq, dq, '00:00:00', round(float(E_all[d, 0]), 4)])
        elif bi == 1:
            ws2.append([None, f'{a:02d}:00-{b:02d}:00', cq, dq, '24:00', round(float(E_all[d, -1]), 4)])
        else:
            ws2.append([None, f'{a:02d}:00-{b:02d}:00', cq, dq, None, None])
# 紧急购电量（完美信息下为0）
ws3 = wb.create_sheet('紧急购电量')
ws3.append(['日期', '购电时间段', '购电量'])
for d in range(start, N):
    ws3.append([dates[d], None, 0.0])
wb.save(out)
wb.save(os.path.join(OUT_DIR, 'result2.xlsx'))
print(f'已保存 result2.xlsx（{N - start} 天）→ 求解/结果/ 与 问题二/结果/')
