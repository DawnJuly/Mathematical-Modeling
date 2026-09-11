# 问题四：波动电价下重算问题2、问题3
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
SOLVE = os.path.dirname(HERE)
sys.path.insert(0, SOLVE)
from _common import *
from _models import *

price_fixed, _, _ = read_附件1()
dates, load_all, pv_actual_all = read_附件2()
d4, price_all = read_附件4()
fc = read_附件3()

def date_key(d):
    return f'{d.year}-{d.month}-{d.day}'

N = len(dates)
S = 31   # 2025-02-01 索引；附件5仅要求保存 2.1—12.31，1月作为预热期，不纳入汇总统计
# ---- 4-2: 逐日LP（波动电价） ----
g42 = np.zeros((N, N_INT)); ch42 = np.zeros((N, N_INT)); dch42 = np.zeros((N, N_INT))
E42 = np.zeros((N, N_INT + 1)); cost42 = np.zeros(N)
carry2 = E0_INIT
for d in range(N):
    g, ch, dch, E, c = solve_daily(load_all[d], pv_actual_all[d], price_all[d], e0=carry2)
    g42[d], ch42[d], dch42[d], E42[d], cost42[d] = g, ch, dch, E, c
    carry2 = float(E[-1])
print(f'4-2 波动电价全年(365天)购电费={cost42.sum():.2f} 元')
print(f'[汇总口径] 4-2 2.1—12.31 购电费={cost42[S:].sum():.2f} 元（固定电价问题2为 12254765.72 元）')

# ---- 4-3: 滚动（波动电价） ----
def run_day43(d):
    L = load_all[d]; S_act = pv_actual_all[d]; key = date_key(dates[d]); f = fc[key]
    pr = price_all[d]
    S0 = forecast_10min(0, f[0], 0, 143); S6 = forecast_10min(6, f[6], 0, 143)
    S12 = forecast_10min(12, f[12], 0, 143); S18 = forecast_10min(18, f[18], 0, 143)
    g0, ch0, dch0, E0, c_plan = solve_daily(L, S0, pr, e0=carry3[d])
    g6, ch6, dch6, E6, _ = solve_adjust(L, S6, pr, g0, e0=float(E0[36]), k0=36)
    g12, ch12, dch12, E12, _ = solve_adjust(L, S12, pr, g0, e0=float(E6[36]), k0=72)
    g18, ch18, dch18, E18, _ = solve_adjust(L, S18, pr, g0, e0=float(E12[36]), k0=108)
    blocks = [0, 36, 72, 108, 144]
    sols = [(g0, ch0, dch0, E0), (g6, ch6, dch6, E6), (g12, ch12, dch12, E12), (g18, ch18, dch18, E18)]
    adj = np.zeros(144); chf = np.zeros(144); dchf = np.zeros(144); Ef = np.empty(145); Ef[0] = E0[0]
    for i in range(4):
        a, b = blocks[i], blocks[i + 1]
        g_, c_, d_, E_ = sols[i]
        adj[a:b] = g_[0:b - a]; chf[a:b] = c_[0:b - a]; dchf[a:b] = d_[0:b - a]
        Ef[a + 1:b + 1] = E_[1:b - a + 1]
    plan = g0
    base = np.minimum(plan, adj) * DT * pr
    down = np.maximum(plan - adj, 0) * DT * pr * 0.5
    up = np.maximum(adj - plan, 0) * DT * pr * 1.5
    plan_commit = (plan * DT * pr).sum()
    purchase_total = (base + down + up).sum()
    # 紧急购电 = 实际供电缺口：delta_k = max{L - (g_k + S^r_k + d_k - c_k), 0}
    gap = np.maximum(L - (adj + S_act + dchf - chf), 0.0)
    emer_kwh = gap * DT
    emer_cost = (emer_kwh * 5.0 * pr).sum()
    total = purchase_total + emer_cost
    return dict(g0=g0, adj=adj, chf=chf, dchf=dchf, Ef=Ef, emer_kwh=emer_kwh, emer_cost=emer_cost,
                plan_commit=plan_commit, purchase_total=purchase_total, total=total, pr=pr)

carry3 = [E0_INIT] * N
rec43 = [None] * N
cost43 = np.zeros(N)
for d in range(N):
    r = run_day43(d)
    rec43[d] = r; cost43[d] = r['total']
    if d + 1 < N:
        carry3[d + 1] = float(r['Ef'][-1])
print(f'4-3 波动电价滚动全年(365天)总费用={cost43.sum():.2f} 元')
print(f'[汇总口径] 4-3 2.1—12.31 总费用={cost43[S:].sum():.2f} 元（固定电价问题3为 14337999.15 元）')

# 指定四天
spec_days = ['2025-03-20', '2025-06-21', '2025-09-23', '2025-12-21']
idx = {}
for d in range(N):
    dd = pd.Timestamp(dates[d]).date()
    for sd in spec_days:
        if dd == pd.Timestamp(sd).date():
            idx[sd] = d
print('\n表1/表2/表3 指定日期(波动电价):')
for sd in spec_days:
    d = idx[sd]
    print(f'  {sd}: 4-2购电费={cost42[d]:.2f}, 4-3总费用={cost43[d]:.2f}(计划{rec43[d]["plan_commit"]:.0f}+紧急{rec43[d]["emer_cost"]:.0f})')

# ---------- 出图 ----------
t = np.arange(144) / 6.0
C1, C2, C3, C4, C5, C6 = '#2E5FA3', '#E07B39', '#3BA272', '#C0504D', '#8A6BBE', '#D4A017'
plt.rcParams.update({'figure.dpi': 150, 'savefig.dpi': 300, 'axes.unicode_minus': False})

def style_ax(ax, xlabel=None, ylabel=None):
    ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
    ax.tick_params(direction='in', labelsize=9)
    for s in ['bottom', 'left']:
        ax.spines[s].set_linewidth(0.9)
    if xlabel: ax.set_xlabel(xlabel, fontsize=10)
    if ylabel: ax.set_ylabel(ylabel, fontsize=10)

sd = '2025-09-23'; d0 = idx[sd]

# 图4-1 波动电价 vs 固定电价（典型日）
fig, ax = plt.subplots(figsize=(11.5, 5.2))
ax.plot(t, price_all[d0], color=C4, lw=1.6, label='波动电价(附件4)')
ax.plot(t, price_fixed, color=C1, lw=1.6, ls='--', label='固定电价(附件1)')
style_ax(ax, '小时', '电价 (元/kWh)')
ax.set_xticks(np.arange(0, 25, 6)); ax.set_xlim(-0.3, 24.3)
ax.legend(fontsize=9, loc='upper right', framealpha=0.9)
ax.text(0.01, 0.02, f'(a) {sd} 波动电价与固定电价对比', transform=ax.transAxes, fontsize=10, fontweight='bold')
save_fig(fig, '图4-1_波动与固定电价对比')

# 图4-2 波动电价四季典型日购电策略（4-2）
fig, axes = plt.subplots(1, 4, figsize=(15.6, 4.6))
for ax, sd_, col in zip(axes, spec_days, [C1, C3, C4, C2]):
    d = idx[sd_]
    ax.bar(t, g42[d], width=0.14, color=col, alpha=0.85, edgecolor='black', lw=0.5)
    ax.set_xticks(np.arange(0, 25, 6)); style_ax(ax, '小时', '购电 (kW)')
    ax.set_ylim(0, g42[d].max() * 1.12)
    ax.text(0.03, 0.02, f'({sd_[5:]})', transform=ax.transAxes, fontsize=9, fontweight='bold')
save_fig(fig, '图4-2_波动电价四季典型日购电')

# 图4-3 波动电价滚动调整购电量（4-3）
fig, ax = plt.subplots(figsize=(11.5, 5.2))
ax.plot(t, rec43[d0]['g0'], color=C1, lw=1.4, label='0:00计划购电')
ax.plot(t, rec43[d0]['adj'], color=C4, lw=1.4, ls='--', label='滚动调整后购电')
style_ax(ax, '小时', '购电功率 (kW)')
ax.set_xticks(np.arange(0, 25, 6)); ax.set_xlim(-0.3, 24.3)
ax.legend(fontsize=9, loc='upper right', framealpha=0.9)
ax.text(0.01, 0.02, f'(a) {sd} 波动电价下计划与调整购电', transform=ax.transAxes, fontsize=10, fontweight='bold')
save_fig(fig, '图4-3_波动电价滚动调整购电')

# 图4-4 波动电价SOC轨迹（4-2典型日）
fig, ax = plt.subplots(figsize=(11.5, 5.2))
ax.plot(t, E42[d0, :144], color=C3, lw=1.8, label='4-2 SOC')
ax.plot(t, rec43[d0]['Ef'][:144], color=C4, lw=1.8, ls='--', label='4-3 调整后SOC')
ax.axhline(EMIN, color='#7A7A7A', lw=0.8, ls=':'); ax.axhline(EMAX, color='#7A7A7A', lw=0.8, ls=':')
style_ax(ax, '小时', '储电量 (kWh)')
ax.set_xticks(np.arange(0, 25, 6)); ax.set_ylim(EMIN - 400, EMAX + 400)
ax.legend(fontsize=9, loc='upper right', framealpha=0.9)
ax.text(0.01, 0.02, f'(a) {sd} 波动电价储能SOC轨迹', transform=ax.transAxes, fontsize=10, fontweight='bold')
save_fig(fig, '图4-4_波动电价SOC轨迹')

# 图4-5 波动电价紧急购电量（4-3，2.1—12.31）
fig, ax = plt.subplots(figsize=(11.5, 5.2))
emer_daily = np.array([rec43[d]['emer_kwh'].sum() for d in range(N)])
ax.bar(dates[S:], emer_daily[S:], width=1.0, color=C4, alpha=0.8, edgecolor='none')
style_ax(ax, '日期', '紧急购电量 (kWh)')
ax.text(0.01, 0.02, '(a) 波动电价下2.1—12.31逐日紧急购电量', transform=ax.transAxes, fontsize=10, fontweight='bold')
save_fig(fig, '图4-5_波动电价紧急购电量')

# 图4-6 固定vs波动电价费用对比（2.1—12.31）
fig, axes = plt.subplots(1, 2, figsize=(13.6, 5.0))
ax = axes[0]
fixed = [12254765.72, 14337999.15]   # 固定电价下问题2/问题3 的 2.1—12.31 汇总
fluc = [cost42[S:].sum(), cost43[S:].sum()]
x = np.arange(2)
w = 0.35
ax.bar(x - w / 2, [f / 1e4 for f in fixed], w, color=C1, edgecolor='black', lw=0.7, label='固定电价')
ax.bar(x + w / 2, [f / 1e4 for f in fluc], w, color=C4, edgecolor='black', lw=0.7, label='波动电价')
for i in range(2):
    ax.text(i - w / 2, fixed[i] / 1e4 + 10, f'{fixed[i]/1e4:.0f}', ha='center', fontsize=8)
    ax.text(i + w / 2, fluc[i] / 1e4 + 10, f'{fluc[i]/1e4:.0f}', ha='center', fontsize=8)
ax.set_xticks(x); ax.set_xticklabels(['问题2(逐日计划)', '问题3(滚动调整)'], fontsize=10)
style_ax(ax, None, '2.1—12.31购电费 (万元)')
ax.legend(fontsize=9, loc='upper left', framealpha=0.9)
ax.text(0.02, 0.02, '(a) 固定/波动电价2.1—12.31费用', transform=ax.transAxes, fontsize=10, fontweight='bold')
ax = axes[1]
em_fixed = sum(rec43[d]['emer_cost'] for d in range(N))  # 占位，改为固定电价问题3紧急费用近似
# 重新读固定电价问题3的紧急费用：用现有结果近似对比月度购电费
mfix = []; mflu = []
for m in range(1, 12):
    dd = [d for d in range(N) if dates[d].month == m + 1]
    mfix.append(0)  # 固定电价问题3月度费用（无缓存，这里用4-3近似）
    mflu.append(cost43[dd].sum() / 1e4)
ax.bar(np.arange(11), mflu, color=get_colors('tab20', 11), edgecolor='black', lw=0.6)
ax.set_xticks(np.arange(11)); ax.set_xticklabels([f'{m+1}月' for m in range(1, 12)], fontsize=9)
style_ax(ax, '月份', '波动电价4-3月度费用 (万元)')
ax.text(0.02, 0.02, '(b) 波动电价4-3月度费用', transform=ax.transAxes, fontsize=10, fontweight='bold')
save_fig(fig, '图4-6_固定与波动电价费用对比')

# ---------- 写 result4-2.xlsx ----------
from openpyxl import Workbook
labs = interval_labels()
start = S
wb = Workbook()
ws = wb.active; ws.title = '计划购电量'
ws.append(['日期\\时间'] + labs + ['全天购电量', '全天购电费'])
for d in range(start, N):
    gE = g42[d] * DT
    ws.append([dates[d]] + [round(float(x), 4) for x in gE] + [round(float(gE.sum()), 4), round(float(cost42[d]), 4)])
ws2 = wb.create_sheet('充放电量')
ws2.append(['日期', '时间段', '充电量', '放电量', '时刻', '储电量'])
for d in range(start, N):
    chE = ch42[d] * DT; dchE = dch42[d] * DT
    for bi, (a, b) in enumerate([(0, 4), (4, 8), (8, 12), (12, 16), (16, 20), (20, 24)]):
        k0, k1 = a * 6, b * 6 - 1
        cq = round(float(chE[k0:k1 + 1].sum()), 4); dq = round(float(dchE[k0:k1 + 1].sum()), 4)
        if bi == 0:
            ws2.append([dates[d], f'{a:02d}:00-{b:02d}:00', cq, dq, '00:00:00', round(float(E42[d, 0]), 4)])
        elif bi == 1:
            ws2.append([None, f'{a:02d}:00-{b:02d}:00', cq, dq, '24:00', round(float(E42[d, -1]), 4)])
        else:
            ws2.append([None, f'{a:02d}:00-{b:02d}:00', cq, dq, None, None])
ws3 = wb.create_sheet('紧急购电量')
ws3.append(['日期', '购电时间段', '购电量'])
for d in range(start, N):
    ws3.append([dates[d], None, 0.0])
wb.save(os.path.join(DATA_DIR, 'result4-2.xlsx'))
wb.save(os.path.join(OUT_DIR, 'result4-2.xlsx'))
print('已保存 result4-2.xlsx → 数据/ 与 求解/问题四/结果/')

# ---------- 写 result4-3.xlsx ----------
wb = Workbook()
ws = wb.active; ws.title = '计划购电量'
ws.append(['日期\\时间'] + labs + ['全天购电量', '全天购电费'])
for d in range(start, N):
    r = rec43[d]; gE = r['g0'] * DT
    ws.append([dates[d]] + [round(float(x), 4) for x in gE] + [round(float(gE.sum()), 4), round(float(r['plan_commit']), 4)])
ws2 = wb.create_sheet('调整购电量')
ws2.append(['日期\\时间'] + labs + ['全天购电量', '全天购电费'])
for d in range(start, N):
    r = rec43[d]; aE = r['adj'] * DT
    ws2.append([dates[d]] + [round(float(x), 4) for x in aE] + [round(float(aE.sum()), 4), round(float(r['purchase_total']), 4)])
ws3 = wb.create_sheet('充放电量')
ws3.append(['日期', '时间段', '充电量', '放电量', '时刻', '储电量'])
for d in range(start, N):
    r = rec43[d]; chE = r['chf'] * DT; dchE = r['dchf'] * DT
    for bi, (a, b) in enumerate([(0, 4), (4, 8), (8, 12), (12, 16), (16, 20), (20, 24)]):
        k0, k1 = a * 6, b * 6 - 1
        cq = round(float(chE[k0:k1 + 1].sum()), 4); dq = round(float(dchE[k0:k1 + 1].sum()), 4)
        if bi == 0:
            ws3.append([dates[d], f'{a:02d}:00-{b:02d}:00', cq, dq, '00:00:00', round(float(r['Ef'][0]), 4)])
        elif bi == 1:
            ws3.append([None, f'{a:02d}:00-{b:02d}:00', cq, dq, '24:00', round(float(r['Ef'][-1]), 4)])
        else:
            ws3.append([None, f'{a:02d}:00-{b:02d}:00', cq, dq, None, None])
ws4 = wb.create_sheet('紧急购电量')
ws4.append(['日期', '购电时间段', '购电量'])
for d in range(start, N):
    em = rec43[d]['emer_kwh']
    segs = []
    i = 0
    while i < 144:
        if em[i] > 1e-3:
            j = i
            while j < 144 and em[j] > 1e-3:
                j += 1
            segs.append((i, j, em[i:j].sum())); i = j
        else:
            i += 1
    if not segs:
        ws4.append([dates[d], None, 0.0])
    else:
        for si, (a, b, amt) in enumerate(segs):
            period = f'{a*10//60:02d}:{a*10%60:02d}-{b*10//60:02d}:{b*10%60:02d}'
            if si == 0:
                ws4.append([dates[d], period, round(float(amt), 4)])
            else:
                ws4.append([None, period, round(float(amt), 4)])
wb.save(os.path.join(DATA_DIR, 'result4-3.xlsx'))
wb.save(os.path.join(OUT_DIR, 'result4-3.xlsx'))
print('已保存 result4-3.xlsx → 数据/ 与 求解/问题四/结果/')
