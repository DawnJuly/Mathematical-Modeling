# -*- coding: utf-8 -*-
"""
生成 Q1/Q2 论文用图（6 张，存 pic/）。
数据来源：附件/附件1.xlsx、附件/附件2.xlsx、result1.xlsx、result2.xlsx
Q1 逐时段充放电/SOC：由能量平衡 net = buy + PV - Load = ch - dis 反推
（典型日无弃光，反推值与 result1 块级存储值吻合到 1e-3 量级，脚本内 assert）。
Q2 块级 SOC：由 result2 每天 6 个 4h 块充放电量从当天 0:00 储电量递推，
与存储 24:00 储电量及跨天连续性校验（逐时段反推不可行，因白天存在弃光）。
"""
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import os

DT = 1.0 / 6.0
T = 144
ETA = 0.9
SOC_LO, SOC_HI = 1200.0, 10800.0
BLOCKS = [(0, 24), (24, 48), (48, 72), (72, 96), (96, 120), (120, 144)]
PIC = 'pic'
os.makedirs(PIC, exist_ok=True)

plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['figure.dpi'] = 150
plt.rcParams['savefig.dpi'] = 150
plt.rcParams['axes.grid'] = True
plt.rcParams['grid.alpha'] = 0.3

def pr(*a):
    print(' '.join(str(x) for x in a).encode('gbk', 'replace').decode('gbk'))

def hours():
    return (np.arange(T) + 0.5) / 6.0   # 时段中点（小时）

# ================= 数据加载 =================
a1 = pd.read_excel('附件/附件1.xlsx')
price = a1['电价'].to_numpy(float)
load_kw = a1['小区负载'].to_numpy(float)
pv_kw = a1['光伏发电预测功率'].to_numpy(float)
load1 = load_kw * DT
pv1 = pv_kw * DT

buy1 = pd.read_excel('result1.xlsx', sheet_name='计划购电量').iloc[:, 1].to_numpy(float)
r1cd = pd.read_excel('result1.xlsx', sheet_name='充放电量')
soc0_q1 = float(r1cd.iloc[0, 4])
soc24_q1 = float(r1cd.iloc[1, 4])

# ---- Q1 反推 ch/dis/SOC（144 时段） ----
net1 = buy1 + pv1 - load1
ch1 = np.clip(net1, 0, None)
dis1 = np.clip(-net1, 0, None)
for k, (a, b) in enumerate(BLOCKS):
    assert abs(ch1[a:b].sum() - float(r1cd.iloc[k, 1])) < 0.5, ('Q1 充电块校验失败', k)
    assert abs(dis1[a:b].sum() - float(r1cd.iloc[k, 2])) < 0.5, ('Q1 放电块校验失败', k)
soc1 = np.empty(T + 1)
soc1[0] = soc0_q1
for t in range(T):
    soc1[t + 1] = soc1[t] + ETA * ch1[t] - dis1[t] / ETA
assert abs(soc1[-1] - soc24_q1) < 0.5, 'Q1 SOC 24:00 校验失败'
assert soc1.min() > SOC_LO - 1 and soc1.max() < SOC_HI + 1, 'Q1 SOC 越界'
pr('Q1 反推校验通过: 总购电 %.2f kWh, 电费 %.2f 元, SOC [%.2f, %.2f], 端点 %.2f/%.2f' % (
    buy1.sum(), float(price @ buy1), soc1.min(), soc1.max(), soc1[0], soc1[-1]))

# ---- Q2 数据 ----
buy_df = pd.read_excel('result2.xlsx', sheet_name='计划购电量')
dates2 = pd.to_datetime(buy_df.iloc[:, 0])
BUY = buy_df.iloc[:, 1:145].to_numpy(float)
day_buy = buy_df.iloc[:, 145].to_numpy(float)
day_cost = buy_df.iloc[:, 146].to_numpy(float)
ND = len(dates2)
cd2 = pd.read_excel('result2.xlsx', sheet_name='充放电量')

# ---- Q2 块级 SOC（每天 7 个端点：0,4,...,24h） ----
soc_blk = np.empty((ND, 7))           # 列 j 对应时刻 4j 点
max_end_err = 0.0
max_cont_err = 0.0
for i in range(ND):
    s = float(cd2.iloc[6 * i, 5])     # 当天 0:00 储电量
    soc_blk[i, 0] = s
    for k, (a, b) in enumerate(BLOCKS):
        ch_b = float(cd2.iloc[6 * i + k, 2])
        dis_b = float(cd2.iloc[6 * i + k, 3])
        s = s + ETA * ch_b - dis_b / ETA
        soc_blk[i, k + 1] = s
    s24 = float(cd2.iloc[6 * i + 1, 5])
    max_end_err = max(max_end_err, abs(soc_blk[i, 6] - s24))
    if i > 0:
        max_cont_err = max(max_cont_err, abs(soc_blk[i, 0] - soc_blk[i - 1, 6]))
pr('Q2 块级SOC校验: 24:00递推误差 %.6f, 跨天连续误差 %.6f, SOC范围 [%.2f, %.2f]' % (
    max_end_err, max_cont_err, soc_blk.min(), soc_blk.max()))
assert max_end_err < 0.5 and max_cont_err < 0.5
assert soc_blk.min() > SOC_LO - 1 and soc_blk.max() < SOC_HI + 1
pr('Q2 总电费校验: %.2f (expect 12254765.72)' % day_cost.sum())

four = ['2025-03-20', '2025-06-21', '2025-09-23', '2025-12-21']
four_idx = [int(np.where(dates2 == pd.Timestamp(s))[0][0]) for s in four]

H = hours()

# ================= 图1: 电价 + 负载/光伏 =================
fig, ax1 = plt.subplots(figsize=(9, 4.8))
ax2 = ax1.twinx()
ax1.step(np.arange(T + 1) / 6.0, np.r_[price, price[-1]], where='post',
         color='#c0392b', lw=1.8, label='电价')
ax2.plot(H, load_kw, color='#2c3e50', lw=1.4, label='小区负载')
ax2.plot(H, pv_kw, color='#e67e22', lw=1.4, label='光伏发电预测功率')
ax1.set_xlim(0, 24)
ax1.set_xticks(range(0, 25, 2))
ax1.set_xlabel('时刻 / h')
ax1.set_ylabel('电价 / (元·kWh$^{-1}$)', color='#c0392b')
ax2.set_ylabel('功率 / kW')
ax1.tick_params(axis='y', labelcolor='#c0392b')
ax1.grid(False)
lines = ax1.get_lines() + ax2.get_lines()
ax1.legend(lines, [l.get_label() for l in lines], loc='upper left', framealpha=0.9)
ax1.set_title('典型日电价、小区负载与光伏预测功率曲线')
fig.tight_layout()
fig.savefig(f'{PIC}/q1_price_load_pv.png')
plt.close(fig)
pr('saved q1_price_load_pv.png')

# ================= 图2: Q1 购电 + 充放电 =================
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 7), sharex=True,
                               gridspec_kw={'height_ratios': [1, 1]})
ax1.bar(H, buy1, width=1.0 / 6.0, color='#4878a8', label='计划购电量')
ax1.set_ylabel('购电量 / (kWh·时段$^{-1}$)')
ax1.set_title('问题1 典型日购电计划与储能充放电策略')
ax1b = ax1.twinx()
ax1b.step(np.arange(T + 1) / 6.0, np.r_[price, price[-1]], where='post',
          color='#c0392b', lw=1.2, ls='--', alpha=0.8, label='电价')
ax1b.set_ylabel('电价 / (元·kWh$^{-1}$)', color='#c0392b')
ax1b.tick_params(axis='y', labelcolor='#c0392b')
ax1b.grid(False)
l1, lab1 = ax1.get_legend_handles_labels()
l2, lab2 = ax1b.get_legend_handles_labels()
ax1.legend(l1 + l2, lab1 + lab2, loc='upper left', framealpha=0.9)

ax2.fill_between(H, 0, ch1, step='mid', color='#27ae60', alpha=0.85, label='充电量')
ax2.fill_between(H, 0, -dis1, step='mid', color='#e67e22', alpha=0.85, label='放电量(取负)')
ax2.axhline(0, color='k', lw=0.6)
ax2.set_xlim(0, 24)
ax2.set_xticks(range(0, 25, 2))
ax2.set_xlabel('时刻 / h')
ax2.set_ylabel('充/放电量 / (kWh·时段$^{-1}$)')
ax2b = ax2.twinx()
ax2b.step(np.arange(T + 1) / 6.0, np.r_[price, price[-1]], where='post',
          color='#c0392b', lw=1.2, ls='--', alpha=0.8, label='电价')
ax2b.set_ylabel('电价 / (元·kWh$^{-1}$)', color='#c0392b')
ax2b.tick_params(axis='y', labelcolor='#c0392b')
ax2b.grid(False)
l1, lab1 = ax2.get_legend_handles_labels()
l2, lab2 = ax2b.get_legend_handles_labels()
ax2.legend(l1 + l2, lab1 + lab2, loc='upper left', framealpha=0.9)
fig.tight_layout()
fig.savefig(f'{PIC}/q1_power_dispatch.png')
plt.close(fig)
pr('saved q1_power_dispatch.png')

# ================= 图3: Q1 SOC 轨迹 =================
fig, ax = plt.subplots(figsize=(9, 4.8))
xs = np.arange(T + 1) / 6.0
ax.axhspan(SOC_LO, SOC_HI, color='#27ae60', alpha=0.06)
ax.plot(xs, soc1, color='#2c3e50', lw=1.8, label='储电量 (SOC)')
ax.axhline(SOC_LO, color='#c0392b', ls='--', lw=1.2)
ax.axhline(SOC_HI, color='#c0392b', ls='--', lw=1.2)
ax.text(15.0, SOC_LO - 300, '下限 1200 kWh', color='#c0392b', ha='left', fontsize=9)
ax.text(0.3, SOC_HI + 150, '上限 10800 kWh', color='#c0392b', ha='left', fontsize=9)
ax.plot([0, 24], [soc1[0], soc1[-1]], 'o', color='#c0392b', ms=5)
ax.annotate('0:00  %.0f kWh' % soc1[0], (0, soc1[0]), xytext=(0.4, soc1[0] + 450), fontsize=9)
ax.annotate('24:00  %.0f kWh' % soc1[-1], (24, soc1[-1]), xytext=(21.6, soc1[-1] + 450), fontsize=9)
ax.set_xlim(0, 24)
ax.set_xticks(range(0, 25, 2))
ax.set_ylim(600, 11800)
ax.set_xlabel('时刻 / h')
ax.set_ylabel('储电量 / kWh')
ax.set_title('问题1 典型日储能储电量 (SOC) 全天轨迹')
ax.legend(loc='upper right', framealpha=0.9)
fig.tight_layout()
fig.savefig(f'{PIC}/q1_soc.png')
plt.close(fig)
pr('saved q1_soc.png')

# ================= 图4: Q2 每日电费 =================
fig, ax = plt.subplots(figsize=(10, 4.8))
ax.fill_between(dates2, 0, day_cost, color='#4878a8', alpha=0.35)
ax.plot(dates2, day_cost, color='#2c3e50', lw=0.9)
offsets = [(10, 18), (10, 20), (10, 18), (-12, -30)]
for k, (i, ds) in enumerate(zip(four_idx, four)):
    ax.plot(dates2[i], day_cost[i], 'o', color='#c0392b', ms=6, zorder=5)
    ha = 'left' if offsets[k][0] > 0 else 'right'
    ax.annotate('%s\n%.2f 元' % (pd.Timestamp(ds).strftime('%m月%d日'), day_cost[i]),
                (dates2[i], day_cost[i]), xytext=offsets[k], textcoords='offset points',
                fontsize=9, color='#c0392b', ha=ha,
                arrowprops=dict(arrowstyle='->', color='#c0392b', lw=0.8))
ax.set_title('问题2 2025年2月1日—12月31日每日购电费（334天，总计 %.2f 元）' % day_cost.sum())
ax.set_xlabel('日期')
ax.set_ylabel('日购电费 / 元')
ax.xaxis.set_major_locator(mdates.MonthLocator())
ax.xaxis.set_major_formatter(mdates.DateFormatter('%m月'))
ax.set_xlim(dates2.iloc[0], dates2.iloc[-1])
fig.tight_layout()
fig.savefig(f'{PIC}/q2_daily_cost.png')
plt.close(fig)
pr('saved q2_daily_cost.png')

# ================= 图5: Q2 SOC 热力图（行=块端时刻, 列=日期） =================
fig, ax = plt.subplots(figsize=(10, 4.6))
data = soc_blk.T                      # 7 x 334
im = ax.imshow(data, aspect='auto', cmap='viridis', origin='upper',
               extent=[-0.5, ND - 0.5, 6.5, -0.5],
               vmin=SOC_LO, vmax=SOC_HI)
month_first = [i for i in range(ND) if dates2.iloc[i].day == 1]
ax.set_xticks(month_first)
ax.set_xticklabels([dates2.iloc[i].strftime('%m月') for i in month_first])
ax.set_yticks(range(7))
ax.set_yticklabels(['%d:00' % (4 * j) for j in range(7)])
ax.set_xlabel('日期（2025年）')
ax.set_ylabel('时刻')
cb = fig.colorbar(im, ax=ax, pad=0.015)
cb.set_label('储电量 / kWh')
ax.set_title('问题2 全年储能储电量 (SOC) 热力图（4小时块端点）')
ax.grid(False)
fig.tight_layout()
fig.savefig(f'{PIC}/q2_soc_heatmap.png')
plt.close(fig)
pr('saved q2_soc_heatmap.png')

# ================= 图6: 四个代表日购电量 =================
fig, axes = plt.subplots(2, 2, figsize=(10, 6.5), sharex=True)
colors = ['#4878a8', '#27ae60', '#e67e22', '#8e44ad']
for k, (ax, i, ds) in enumerate(zip(axes.flat, four_idx, four)):
    ax.bar(H, BUY[i], width=1.0 / 6.0, color=colors[k])
    ts = pd.Timestamp(ds)
    ax.set_title('%s（日购电费 %.2f 元）' % (ts.strftime('%m月%d日'), day_cost[i]), fontsize=11)
    ax.set_xlim(0, 24)
    ax.set_xticks(range(0, 25, 4))
for ax in axes[1]:
    ax.set_xlabel('时刻 / h')
for ax in axes[:, 0]:
    ax.set_ylabel('购电量 / (kWh·时段$^{-1}$)')
fig.suptitle('问题2 四个代表日计划购电量日内分布（10分钟时段）', fontsize=13)
fig.tight_layout(rect=(0, 0, 1, 0.97))
fig.savefig(f'{PIC}/q2_four_days.png')
plt.close(fig)
pr('saved q2_four_days.png')

pr('ALL DONE')
