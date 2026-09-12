# 问题一：每天电价与负载相同 + 光伏预测已知，储能0:00与24:00储电量相同
# 单日计划购电策略 LP
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from _common import *
from _models import *

# ---------- 1. 读数据 & 预处理 ----------
price, load, pv = read_附件1()
print('附件1 列核对: 电价/小区负载/光伏发电预测功率, 行数=', len(price))
# 预处理：数值化(已由read完成)、时间边界'0:00+1'→24:00、144点映射为144个10分钟间隔
# 异常值检测(3σ)：记录异常数（用于预处理前后对比说明）
def outlier_mask(x, k=3.0):
    mu, sd = x.mean(), x.std()
    return (np.abs(x - mu) > k * sd)
for name, arr in [('电价', price), ('负载', load), ('光伏', pv)]:
    print(f'  {name}: min={arr.min():.4f} max={arr.max():.4f} 异常点数(3σ)={outlier_mask(arr).sum()}')

# 预处理后数据（间隔对齐：第k个间隔=[k·10,(k+1)·10]分钟，功率=间隔k的平均功率）
proc = pd.DataFrame({
    '间隔序号': np.arange(N_INT),
    '间隔标签': interval_labels(),
    '电价(元/kWh)': price,
    '小区负载(kW)': load,
    '光伏预测(kW)': pv,
})
proc.to_csv(shared_path('预处理数据.csv'), index=False, encoding='utf-8-sig')
print('已保存 支撑材料/预处理数据.csv')

# ---------- 2. LP 求解 ----------
# 附录1给定 2025-01-01 0:00 储电量 E0=6000 kWh，故固定 E0=6000 并施加日循环 E0=E144
g, ch, dch, E, cost = solve_daily(load, pv, price, e0=E0_INIT, soc_cycle=True)
E0, E24 = E[0], E[-1]
gE = g * DT          # 购电量 kWh/间隔
chE = ch * DT
dchE = dch * DT
print(f'\n问题一结果: 全天购电量={gE.sum():.4f} kWh, 全天购电费={cost:.4f} 元')
print(f'  0:00储电量={E0:.4f}, 24:00储电量={E24:.4f} kWh, SOC范围=[{E.min():.2f},{E.max():.2f}]')
print(f'  全天充电量={chE.sum():.4f}, 全天放电量={dchE.sum():.4f} kWh')

# 表1 指定时间段
spec = [(10, 0), (12, 0), (14, 0), (16, 0), (18, 0), (20, 0)]  # (时,分)
print('\n表1 指定时间段购电量:')
for hh, mm in spec:
    k = (hh * 60 + mm) // 10
    print(f'  {hh:02d}:{mm:02d}-{hh:02d}:{mm + 10:02d}  购电量={gE[k]:.4f} kWh')

# 表2 6个4小时段充放电量
print('\n表2 储能充放电量:')
blocks = [(0, 4), (4, 8), (8, 12), (12, 16), (16, 20), (20, 24)]
block_rec = []
for a, b in blocks:
    k0, k1 = a * 6, b * 6 - 1
    cq = chE[k0:k1 + 1].sum()
    dq = dchE[k0:k1 + 1].sum()
    block_rec.append((f'{a:02d}:00-{b:02d}:00', cq, dq))
    print(f'  {a:02d}:00-{b:02d}:00  充电量={cq:.4f}  放电量={dq:.4f}')
print(f'  0:00储电量={E0:.4f} kWh, 24:00储电量={E24:.4f} kWh')

# ---------- 3. 出图 ----------
t = np.arange(N_INT) / 6.0   # 小时
C1, C2, C3, C4, C5 = '#2E5FA3', '#E07B39', '#3BA272', '#C0504D', '#8A6BBE'
plt.rcParams.update({'figure.dpi': 150, 'savefig.dpi': 300, 'axes.unicode_minus': False})

def style_ax(ax, xlabel=None, ylabel=None):
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.tick_params(direction='in', labelsize=9)
    for s in ['bottom', 'left']:
        ax.spines[s].set_linewidth(0.9)
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=10)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=10)

# 图1-1 预处理前后对比（原始时间点序列 vs 间隔对齐，整合为单张双轴图，不再拆成三个小图）
fig, ax = plt.subplots(figsize=(11.5, 5.4))
t_raw = np.arange(N_INT + 1) / 6.0   # 原始时间点序列（含'0:00+1'→24:00边界点）

# 左轴：负载、光伏（单位均为 kW，量级接近，共轴对比）
ax.plot(t_raw, np.append(load, load[0]), '--', color='#9AA5B1', lw=1.1, label='负载·原始(时间点)')
ax.plot(t, load, '-', color=C2, lw=1.8, label='负载·间隔对齐')
ax.plot(t_raw, np.append(pv, pv[0]), '--', color='#B8C6D9', lw=1.1, label='光伏·原始(时间点)')
ax.plot(t, pv, '-', color=C3, lw=1.8, label='光伏·间隔对齐')
style_ax(ax, '小时', '负载 / 光伏 (kW)')
ax.set_xticks(np.arange(0, 25, 6))
ax.set_xlim(-0.3, 24.3)
ax.set_ylim(0, max(load.max(), pv.max()) * 1.12)

# 右轴：电价（元/kWh，量级与功率不同，单独成轴）
ax2 = ax.twinx()
ax2.plot(t_raw, np.append(price, price[0]), '--', color='#CBB7A5', lw=1.1, label='电价·原始(时间点)')
ax2.plot(t, price, '-', color=C1, lw=1.8, label='电价·间隔对齐')
ax2.set_ylabel('电价 (元/kWh)', fontsize=10)
ax2.set_ylim(0, price.max() * 1.12)
ax2.tick_params(direction='in', labelsize=9)
ax2.spines['top'].set_visible(False)
ax2.spines['bottom'].set_visible(False)
ax2.spines['right'].set_linewidth(0.9)

# 合并双轴图例（单图单图例，说明三条序列预处理前后均吻合）
h1, l1 = ax.get_legend_handles_labels()
h2, l2 = ax2.get_legend_handles_labels()
ax.legend(h1 + h2, l1 + l2, fontsize=8, loc='upper center', bbox_to_anchor=(0.5, -0.14), ncol=3, frameon=False)
ax.text(0.01, 0.02, '(a) 数据预处理前后对比', transform=ax.transAxes, fontsize=10, fontweight='bold')
save_fig(fig, '图1-1_预处理前后对比')

# 图1-2 分时电价与最优购电功率（双轴）
fig, ax = plt.subplots(figsize=(11.5, 5.2))
ax.bar(t, g, width=0.12, color=C1, alpha=0.85, edgecolor='black', lw=0.6, label='购电功率')
style_ax(ax, '小时', '购电功率 (kW)')
ax.set_xticks(np.arange(0, 25, 6))
ax.set_xlim(-0.3, 24.3)
ax2 = ax.twinx()
ax2.plot(t, price, color=C4, lw=1.6, label='电价')
ax2.set_ylabel('电价 (元/kWh)', fontsize=10)
ax2.tick_params(direction='in', labelsize=9)
ax2.spines['top'].set_visible(False)
ax2.spines['bottom'].set_visible(False)
ax2.spines['right'].set_linewidth(0.9)
h1, l1 = ax.get_legend_handles_labels()
h2, l2 = ax2.get_legend_handles_labels()
ax.legend(h1 + h2, l1 + l2, fontsize=9, loc='upper left', framealpha=0.9)
ax.text(0.01, 0.02, '(a) 分时电价与购电功率', transform=ax.transAxes, fontsize=10, fontweight='bold')
save_fig(fig, '图1-2_电价与购电策略')

# 图1-3 负载/光伏/净负荷与储能充放电
fig, ax = plt.subplots(figsize=(11.5, 5.2))
net = load - pv
ax.plot(t, load, color=C2, lw=1.6, label='小区负载')
ax.plot(t, pv, color=C3, lw=1.6, label='光伏功率')
ax.plot(t, net, color=C4, lw=1.3, ls='--', label='净负荷(负载-光伏)')
ax.bar(t, ch, width=0.1, color=C5, alpha=0.7, edgecolor='black', lw=0.4, label='充电')
ax.bar(t, -dch, width=0.1, color=C1, alpha=0.7, edgecolor='black', lw=0.4, label='放电')
style_ax(ax, '小时', '功率 (kW)')
ax.axhline(0, color='black', lw=0.8)
ax.set_xticks(np.arange(0, 25, 6)); ax.set_xlim(-0.3, 24.3)
ax.legend(fontsize=8, loc='upper right', framealpha=0.9, ncol=2)
ax.text(0.01, 0.02, '(a) 负载-光伏-净负荷与储能充放电', transform=ax.transAxes, fontsize=10, fontweight='bold')
save_fig(fig, '图1-3_负荷光伏净负荷与充放电')

# 图1-4 储能SOC轨迹与充放电功率（双子图，共享x）
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11.5, 6.4), sharex=True)
ax1.plot(t, E[:144], color=C1, lw=1.8)
ax1.fill_between(t, EMIN, E[:144], color=C1, alpha=0.12)
ax1.axhline(EMIN, color='#7A7A7A', lw=0.8, ls=':')
ax1.axhline(EMAX, color='#7A7A7A', lw=0.8, ls=':')
ax1.set_ylim(EMIN - 400, EMAX + 400)
style_ax(ax1, None, '储电量 (kWh)')
ax1.set_xticks(np.arange(0, 25, 6))
ax2.bar(t, ch, width=0.12, color=C5, edgecolor='black', lw=0.5, label='充电')
ax2.bar(t, -dch, width=0.12, color=C4, edgecolor='black', lw=0.5, label='放电')
ax2.axhline(0, color='black', lw=0.8)
style_ax(ax2, '小时', '充/放电功率 (kW)')
ax2.legend(fontsize=9, loc='upper right', framealpha=0.9)
ax1.text(0.01, 0.02, '(a) SOC轨迹', transform=ax1.transAxes, fontsize=10, fontweight='bold')
ax2.text(0.01, 0.02, '(b) 充放电功率', transform=ax2.transAxes, fontsize=10, fontweight='bold')
save_fig(fig, '图1-4_储能SOC与充放电功率')

# 图1-5 能量平衡（24小时堆叠面积：购电+光伏+放电 = 负载+充电）
fig, ax = plt.subplots(figsize=(11.5, 5.2))
supply = np.vstack([g, pv, dch])
ax.stackplot(t, supply, labels=['购电', '光伏', '储能放电'], colors=[C1, C3, C4],
             alpha=0.82, edgecolor='black', linewidth=0.5)
ax.plot(t, load, color='black', lw=1.6, label='小区负载')
ax.plot(t, load + ch, color='#5A5A5A', lw=1.2, ls='--', label='负载+充电')
style_ax(ax, '小时', '功率 (kW)')
ax.set_xticks(np.arange(0, 25, 6)); ax.set_xlim(-0.3, 24.3)
ax.legend(fontsize=8, loc='upper right', framealpha=0.9)
ax.text(0.01, 0.02, '(a) 能量平衡关系', transform=ax.transAxes, fontsize=10, fontweight='bold')
save_fig(fig, '图1-5_能量平衡')

# 图1-6 灵敏度：购电费随0:00储电量初值变化（固定 E0 并满足日循环 E24=E0）
e0s = np.linspace(EMIN, EMAX, 21)
costs = []
for e0 in e0s:
    # 固定 E0=e0 且要求 E24=e0（周期），观察购电费
    _, _, _, _, c_ = solve_daily(load, pv, price, e0=float(e0), soc_cycle=True)
    costs.append(c_)
costs = np.array(costs)
cost_at_given = costs[np.argmin(np.abs(e0s - E0_INIT))]
fig, ax = plt.subplots(figsize=(11.5, 5.2))
ax.plot(e0s, costs, '-o', color=C1, lw=1.6, ms=4, markeredgecolor='black')
ax.axvline(E0_INIT, color=C4, lw=1.0, ls='--')
ax.plot(E0_INIT, cost_at_given, 'o', color=C4, ms=6)
ax.annotate(f'附录1给定 E0=6000 kWh\n对应购电费={cost_at_given:.0f} 元',
            xy=(E0_INIT, cost_at_given),
            xytext=(E0_INIT + 500, costs.min() + (costs.max() - costs.min()) * 0.55), fontsize=9,
            arrowprops=dict(arrowstyle='->', lw=0.9))
style_ax(ax, '0:00储电量 E0 (kWh)', '全天购电费 (元)')
ax.text(0.02, 0.02, '(a) 购电费对储能初值灵敏度', transform=ax.transAxes, fontsize=10, fontweight='bold')
save_fig(fig, '图1-6_购电费灵敏度')

# ---------- 4. 写 result1.xlsx（严格按附件5模板：工作表名/列名/时间段标签一致） ----------
from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

def _tpl_time(m):
    '''附件5模板时间格式：整数分钟→'H:MM'；跨日部分记作 'H:MM+1'。'''
    if m >= 1440:
        return f'{m // 60 - 24}:{m % 60:02d}+1'
    return f'{m // 60}:{m % 60:02d}'

# 模板标签：第 k+1 行（k=0..143）对应 [(k+1)·10,(k+2)·10] 分钟，与附件5逐行一致
labs_tpl = [f'{_tpl_time((k + 1) * 10)}-{_tpl_time((k + 1) * 10 + 10)}' for k in range(N_INT)]

wb = Workbook()

# Sheet1 计划购电量：144个10分钟间隔的购电量
ws1 = wb.active
ws1.title = '计划购电量'
ws1.append(['时间段', '购电量'])
for k in range(N_INT):
    ws1.append([labs_tpl[k], round(float(gE[k]), 4)])
ws1.append(['全天购电量', round(float(gE.sum()), 4)])
ws1.append(['全天购电费', round(float(cost), 4)])

# Sheet2 充放电量：6个4小时段的充/放电量，及 0:00、24:00 储电量
ws2 = wb.create_sheet('充放电量')
ws2.append(['时间段', '充电量', '放电量', '时刻', '储电量'])
for i, (a, b) in enumerate(blocks):
    _, cq, dq = block_rec[i]
    lab = f'{a}:00-{b}:00'
    if i == 0:
        ws2.append([lab, round(cq, 4), round(dq, 4), '0:00', round(float(E0), 4)])
    elif i == 1:
        ws2.append([lab, round(cq, 4), round(dq, 4), '24:00', round(float(E24), 4)])
    else:
        ws2.append([lab, round(cq, 4), round(dq, 4), None, None])

# 样式：表头加粗、冻结首行、设置列宽
hdr_font = Font(bold=True)
for ws in (ws1, ws2):
    for cell in ws[1]:
        cell.font = hdr_font
    ws.freeze_panes = 'A2'
for i, w in enumerate([18, 14], 1):
    ws1.column_dimensions[get_column_letter(i)].width = w
for i, w in enumerate([14, 12, 12, 10, 12], 1):
    ws2.column_dimensions[get_column_letter(i)].width = w

out1 = os.path.join(ROOT_OUT, 'result1.xlsx')
wb.save(out1)
wb.save(os.path.join(OUT_DIR, 'result1.xlsx'))

print('\n已保存 result1.xlsx（按附件5模板：计划购电量 / 充放电量，含全天购电量与全天购电费）→ 支撑材料/result/')
print('全部输出图完成')

# ---------- 5. 参数灵敏度（供第六章灵敏度分析，固定 E0=6000） ----------
import _models as M
print('\n第六章灵敏度分析（固定 E0=6000）:')
print(f'  基准购电费={cost:.2f} 元')

def _sens_cost(**kwargs):
    saved = {k: getattr(M, k) for k in kwargs}
    for k, v in kwargs.items():
        setattr(M, k, v)
    _, _, _, _, c_ = solve_daily(load, pv, price, e0=E0_INIT, soc_cycle=True)
    for k, v in saved.items():
        setattr(M, k, v)
    return c_

for label, kw in [
    ('ETA=0.85', {'ETA': 0.85}),
    ('ETA=0.95', {'ETA': 0.95}),
    ('PMAX=4000', {'PMAX': 4000.0}),
    ('PMAX=6000', {'PMAX': 6000.0}),
    ('EMIN=1500', {'EMIN': 1500.0}),
]:
    c_ = _sens_cost(**kw)
    print(f'  {label}: {c_:.2f} 元, 相对基准 {100*(c_-cost)/cost:+.2f}%')
for label, scale in [('load+5%', 1.05), ('load-5%', 0.95)]:
    _, _, _, _, c_ = solve_daily(load * scale, pv, price, e0=E0_INIT, soc_cycle=True)
    print(f'  {label}: {c_:.2f} 元, 相对基准 {100*(c_-cost)/cost:+.2f}%')
