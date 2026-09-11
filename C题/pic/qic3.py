# -*- coding: utf-8 -*-
"""
Q3 图（图1-4，存 pic/）：预报 vs 实际、预报误差、计划 vs 滚动调整、总电费对比。
数据来源：lp_core 重算（固定电价下的 Q2、Q3、对照组全年结果 +
附件3 预报误差统计），与 q3_log.txt 全年汇总断言一致后出图。
"""
import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
PIC = BASE / 'pic'
sys.path.insert(0, str(BASE / 'code'))

from lp_core import (load_data, q2_year, q3_year, fc_error_stats,
                     STAGES, FOUR_DAYS, DAYS_OUT, T)

plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['figure.dpi'] = 150
plt.rcParams['savefig.dpi'] = 150
plt.rcParams['axes.grid'] = True
plt.rcParams['grid.alpha'] = 0.3


def pr(*a):
    print(' '.join(str(x) for x in a).encode('gbk', 'replace').decode('gbk'))


H = (np.arange(T) + 0.5) / 6.0          # 时段中点（小时）
XS = np.arange(T + 1) / 6.0             # 阶梯图边界（小时）

# ================= 数据重算 =================
D = load_data()
price1, dates = D['price1'], D['dates']
LOAD, PV, FC, HA = D['LOAD'], D['PV'], D['FC'], D['HA']

q2_f = q2_year(price1)
q3_f = q3_year(price1, FC, LOAD, PV, adjust=True)
ct_f = q3_year(price1, FC, LOAD, PV, adjust=False)

tot = lambda res, key: sum(res[d][key] for d in DAYS_OUT)
q2f, q3f, ctf = tot(q2_f, 'cost'), tot(q3_f, 'total'), tot(ct_f, 'total')

# 与 q3_log.txt 全年汇总一致性断言
assert abs(q2f - 12254765.72) < 1.0
assert abs(q3f - 17000834.39) < 1.0
assert abs(ctf - 17400028.28) < 1.0
pr('全年汇总断言通过: Q2f %.2f Q3f %.2f 对照f %.2f' % (q2f, q3f, ctf))

four_idx = [i for i, t in enumerate(dates)
            if t.strftime('%Y-%m-%d') in FOUR_DAYS]
four_lab = [dates[d].strftime('%m月%d日') for d in four_idx]

# ================= 图1: 四天 0:00 预报 vs 实际逐时功率 =================
fig, axes = plt.subplots(2, 2, figsize=(10, 6.5), sharex=True)
xh = np.arange(25)
for ax, d, lab in zip(axes.flat, four_idx, four_lab):
    fc24 = FC[d, 0, :]                  # 约定B: 预报k小时 -> 当天第k-1小时
    ax.step(xh, np.r_[fc24, fc24[-1]], where='post',
            color='#4878a8', lw=1.6, label='0:00发布光伏预报')
    ax.plot(np.arange(24) + 0.5, HA[d], color='#c0392b', lw=1.4,
            label='实际功率(逐时均值)')
    mae = np.abs(fc24 - HA[d]).mean()
    ax.set_title('%s（全天MAE %.1f kW）' % (lab, mae), fontsize=11)
    ax.set_xlim(0, 24)
    ax.set_xticks(range(0, 25, 4))
    ax.set_ylim(bottom=0)
axes.flat[0].legend(loc='upper right', fontsize=9, framealpha=0.9)
for ax in axes[1]:
    ax.set_xlabel('时刻 / h')
for ax in axes[:, 0]:
    ax.set_ylabel('功率 / kW')
fig.suptitle('问题3 四个代表日0:00光伏预报与实际功率对比（约定B）', fontsize=13)
fig.tight_layout(rect=(0, 0, 1, 0.97))
fig.savefig(PIC / 'q3_forecast_vs_actual.png')
plt.close(fig)
pr('saved q3_forecast_vs_actual.png')

# ================= 图2: 预报误差随提前时长 =================
tbl, overall = fc_error_stats(D)
ks = [r[0] for r in tbl]
maes = [r[2] for r in tbl]
rmses = [r[3] for r in tbl]
dmaes = [r[4] for r in tbl]
fig, ax = plt.subplots(figsize=(9, 4.8))
ax.plot(ks, maes, 'o-', color='#2c3e50', lw=1.6, ms=4, label='MAE（全天）')
ax.plot(ks, dmaes, 's-', color='#e67e22', lw=1.6, ms=4,
        label='MAE（白天，功率>100kW）')
ax.plot(ks, rmses, '^--', color='#8e44ad', lw=1.2, ms=4, label='RMSE')
ax.axhline(overall[0], color='#2c3e50', ls=':', lw=1.0, alpha=0.7)
ax.text(24.2, overall[0], '总体MAE\n%.1f' % overall[0], fontsize=8,
        va='center', color='#2c3e50')
ax.set_xlabel('提前时长 k / h')
ax.set_ylabel('预报误差 / kW')
ax.set_xlim(0.5, 26.5)
ax.set_xticks(range(1, 25, 1), minor=True)
ax.set_xticks(range(1, 25, 2))
ax.set_title('问题3 附件3光伏预报误差随提前时长的变化（全年365天×4发布时刻）')
ax.legend(loc='upper left', framealpha=0.9)
fig.tight_layout()
fig.savefig(PIC / 'q3_forecast_error.png')
plt.close(fig)
pr('saved q3_forecast_error.png')

# ================= 图3: 四天 计划 vs 滚动调整购电量 =================
fig, axes = plt.subplots(2, 2, figsize=(10, 6.5), sharex=True)
for ax, d, lab in zip(axes.flat, four_idx, four_lab):
    r = q3_f[d]
    ax.step(XS, np.r_[r['plan'], r['plan'][-1]], where='post',
            color='#4878a8', lw=1.4, label='0:00计划购电量')
    ax.step(XS, np.r_[r['adj'], r['adj'][-1]], where='post',
            color='#c0392b', lw=1.2, ls='--', label='滚动调整后购电量')
    if r['e'].sum() > 1e-6:
        ax.fill_between(H, 0, r['e'], step='mid', color='#8e44ad',
                        alpha=0.45, label='紧急购电量')
    for h0 in STAGES[1:]:
        ax.axvline(h0, color='#27ae60', ls=':', lw=1.0)
    ax.set_title('%s（紧急购电 %.0f kWh）' % (lab, r['e'].sum()), fontsize=11)
    ax.set_xlim(0, 24)
    ax.set_xticks(range(0, 25, 4))
    ax.set_ylim(bottom=0)
axes.flat[0].legend(loc='upper left', fontsize=9, framealpha=0.9)
axes.flat[0].text(6.15, axes.flat[0].get_ylim()[1] * 0.55,
                  '绿虚线: 6/12/18:00调整时刻', fontsize=8, color='#27ae60')
for ax in axes[1]:
    ax.set_xlabel('时刻 / h')
for ax in axes[:, 0]:
    ax.set_ylabel('电量 / (kWh·时段$^{-1}$)')
fig.suptitle('问题3 四个代表日0:00计划与滚动调整购电量对比（固定电价）', fontsize=13)
fig.tight_layout(rect=(0, 0, 1, 0.97))
fig.savefig(PIC / 'q3_plan_vs_adj.png')
plt.close(fig)
pr('saved q3_plan_vs_adj.png')

# ================= 图4: Q3 总电费对比（固定电价） =================
fig, ax = plt.subplots(figsize=(7.5, 4.8))
names = ['Q2 理想情形\n(光伏已知)', 'Q3 滚动调整', '对照组\n(仅0:00计划)']
vals = [q2f / 1e4, q3f / 1e4, ctf / 1e4]
colors = ['#27ae60', '#4878a8', '#95a5a6']
bars = ax.bar(names, vals, color=colors, width=0.55)
for b, v in zip(bars, vals):
    ax.text(b.get_x() + b.get_width() / 2, v + 8, '%.2f' % v,
            ha='center', fontsize=10)
ax.annotate('较对照组节省 %.2f 万元 (2.29%%)' % ((ctf - q3f) / 1e4),
            xy=(1, vals[1] + 40), xytext=(0.28, vals[1] + 90),
            fontsize=9, color='#c0392b',
            arrowprops=dict(arrowstyle='->', color='#c0392b', lw=0.9))
ax.set_ylabel('总电费 / 万元')
ax.set_ylim(0, max(vals) * 1.16)
ax.set_title('问题3 2025年2月1日—12月31日总电费对比（固定电价，334天）')
fig.tight_layout()
fig.savefig(PIC / 'q3_cost_compare.png')
plt.close(fig)
pr('saved q3_cost_compare.png')

# ============ 图5: 四个发布时刻的光伏预报误差箱线图 ============
err_by_stage = {h0: [] for h0 in STAGES}
for d in range(365):
    for j, h0 in enumerate(STAGES):
        for k in range(1, 25):
            h_abs = h0 + k - 1
            dd = d + h_abs // 24
            if dd > 364:
                continue
            err_by_stage[h0].append(FC[d, j, k - 1] - HA[dd, h_abs % 24])

fig, ax = plt.subplots(figsize=(8.2, 4.8))
labs = ['%d:00发布' % h0 for h0 in STAGES]
data = [np.array(err_by_stage[h0]) for h0 in STAGES]
bp = ax.boxplot(data, labels=labs, widths=0.5, showfliers=True,
                flierprops=dict(marker='.', ms=2, alpha=0.25,
                                markerfacecolor='#7f8c8d',
                                markeredgecolor='#7f8c8d'),
                patch_artist=True)
for patch, c in zip(bp['boxes'], ['#4878a8', '#27ae60', '#e67e22', '#8e44ad']):
    patch.set_facecolor(c)
    patch.set_alpha(0.55)
for med in bp['medians']:
    med.set_color('#c0392b')
    med.set_linewidth(1.4)
for i, arr in enumerate(data):
    ax.text(i + 1, ax.get_ylim()[1], 'MAE %.1f' % np.abs(arr).mean(),
            ha='center', va='bottom', fontsize=9, color='#2c3e50')
ax.axhline(0, color='#2c3e50', lw=0.9, ls='--')
ax.set_ylabel('预报误差 / kW')
ax.set_title('问题3 四个发布时刻的光伏预报误差分布（全年365天×24个提前时长）')
fig.tight_layout()
fig.savefig(PIC / 'q3_err_boxplot.png')
plt.close(fig)
pr('saved q3_err_boxplot.png')

# ============ 图6: 滚动调整累计节省曲线 ============
daily_save = np.array([ct_f[d]['total'] - q3_f[d]['total'] for d in DAYS_OUT])
cum = np.cumsum(daily_save)
xday = [dates[d] for d in DAYS_OUT]

fig, ax = plt.subplots(figsize=(9, 4.6))
ax.plot(xday, cum / 1e4, color='#c0392b', lw=1.8)
ax.fill_between(xday, 0, cum / 1e4, color='#c0392b', alpha=0.12)
ax.annotate('累计节省 %.2f 万元' % (cum[-1] / 1e4),
            xy=(xday[-1], cum[-1] / 1e4),
            xytext=(xday[int(len(xday) * 0.45)], cum[-1] / 1e4 * 0.62),
            fontsize=10, color='#c0392b',
            arrowprops=dict(arrowstyle='->', color='#c0392b', lw=1.0))
ax.set_xlabel('日期')
ax.set_ylabel('累计节省 / 万元')
ax.set_title('问题3 滚动调整策略相对“仅0:00计划”的累计节省（334天）')
fig.autofmt_xdate(rotation=25)
fig.tight_layout()
fig.savefig(PIC / 'q3_cum_saving.png')
plt.close(fig)
pr('saved q3_cum_saving.png  累计节省 %.2f 元' % cum[-1])

pr('ALL DONE (Q3)')
