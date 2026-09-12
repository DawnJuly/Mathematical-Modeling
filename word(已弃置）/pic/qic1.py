# -*- coding: utf-8 -*-
"""
Q1 图（图1-3，存 pic/）：电价+负载/光伏、购电计划与充放电、SOC 轨迹。
数据来源：附件/附件1.xlsx、result1.xlsx
Q1 逐时段充放电/SOC：由能量平衡 net = buy + PV - Load = ch - dis 反推
（典型日无弃光，反推值与 result1 块级存储值吻合到 1e-3 量级，脚本内 assert）。
"""
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path

DT = 1.0 / 6.0
T = 144
ETA = 0.9
SOC_LO, SOC_HI = 1200.0, 10800.0
BLOCKS = [(0, 24), (24, 48), (48, 72), (72, 96), (96, 120), (120, 144)]
BASE = Path(__file__).resolve().parent.parent
PIC = BASE / 'pic'

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
a1 = pd.read_excel(BASE / '附件/附件1.xlsx')
price = a1['电价'].to_numpy(float)
load_kw = a1['小区负载'].to_numpy(float)
pv_kw = a1['光伏发电预测功率'].to_numpy(float)
load1 = load_kw * DT
pv1 = pv_kw * DT

buy1 = pd.read_excel(BASE / 'result1.xlsx', sheet_name='计划购电量').iloc[:, 1].to_numpy(float)
r1cd = pd.read_excel(BASE / 'result1.xlsx', sheet_name='充放电量')
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
fig.savefig(PIC / 'q1_price_load_pv.png')
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
fig.savefig(PIC / 'q1_power_dispatch.png')
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
fig.savefig(PIC / 'q1_soc.png')
plt.close(fig)
pr('saved q1_soc.png')

pr('ALL DONE (Q1)')
