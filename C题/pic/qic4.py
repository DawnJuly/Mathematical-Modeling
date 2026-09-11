# -*- coding: utf-8 -*-
"""
Q4 图（图5-6，存 pic/）：固定 vs 波动电价曲线、两种电价下 Q2/Q3 总电费对比。
数据来源：lp_core 重算（固定/波动电价下的 Q2、Q3、对照组全年结果），
与 q3_log.txt/q4_log.txt 全年汇总断言一致后出图。
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

from lp_core import (load_data, q2_year, q3_year,
                     FOUR_DAYS, DAYS_OUT, T)

plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['figure.dpi'] = 150
plt.rcParams['savefig.dpi'] = 150
plt.rcParams['axes.grid'] = True
plt.rcParams['grid.alpha'] = 0.3


def pr(*a):
    print(' '.join(str(x) for x in a).encode('gbk', 'replace').decode('gbk'))


XS = np.arange(T + 1) / 6.0             # 阶梯图边界（小时）

# ================= 数据重算 =================
D = load_data()
price1, dates = D['price1'], D['dates']
LOAD, PV, FC, PRICE4 = D['LOAD'], D['PV'], D['FC'], D['PRICE4']

q2_f = q2_year(price1)
q3_f = q3_year(price1, FC, LOAD, PV, adjust=True)
q2_v = q2_year(PRICE4)
q3_v = q3_year(PRICE4, FC, LOAD, PV, adjust=True)
ct_v = q3_year(PRICE4, FC, LOAD, PV, adjust=False)
ct_f = q3_year(price1, FC, LOAD, PV, adjust=False)

tot = lambda res, key: sum(res[d][key] for d in DAYS_OUT)
q2f, q3f = tot(q2_f, 'cost'), tot(q3_f, 'total')
q2v, q3v, ctv = tot(q2_v, 'cost'), tot(q3_v, 'total'), tot(ct_v, 'total')
ctf = tot(ct_f, 'total')

# 与 q3_log.txt / q4_log.txt 全年汇总一致性断言
assert abs(q2f - 12254765.72) < 1.0
assert abs(q3f - 17000834.39) < 1.0
assert abs(q2v - 12841054.36) < 1.0
assert abs(q3v - 17742495.98) < 1.0
assert abs(ctv - 18133711.59) < 1.0
assert abs(ctf - 17400028.28) < 1.0
pr('全年汇总断言通过: Q2f %.2f Q3f %.2f 对照f %.2f | Q2v %.2f Q3v %.2f 对照v %.2f'
   % (q2f, q3f, ctf, q2v, q3v, ctv))

four_idx = [i for i, t in enumerate(dates)
            if t.strftime('%Y-%m-%d') in FOUR_DAYS]
four_lab = [dates[d].strftime('%m月%d日') for d in four_idx]

# ================= 图5: 固定 vs 波动电价曲线（代表日） =================
d_rep = four_idx[3]                     # 2025-12-21
fig, axes = plt.subplots(2, 1, figsize=(9, 6.2), sharex=True)
for ax, d, lab in zip(axes, [four_idx[0], d_rep],
                      [four_lab[0], four_lab[3]]):
    ax.step(XS, np.r_[price1, price1[-1]], where='post',
            color='#c0392b', lw=1.6, label='附件1 固定电价')
    ax.step(XS, np.r_[PRICE4[d], PRICE4[d][-1]], where='post',
            color='#2c3e50', lw=1.3, label='附件4 波动电价（%s）' % lab)
    ax.set_ylabel('电价 / (元·kWh$^{-1}$)')
    ax.set_ylim(0, 2.0)
    ax.legend(loc='upper left', fontsize=9, framealpha=0.9)
    ax.set_title('%s：波动电价日内极差 %.3f 元/kWh'
                 % (lab, PRICE4[d].max() - PRICE4[d].min()), fontsize=11)
axes[1].set_xlim(0, 24)
axes[1].set_xticks(range(0, 25, 2))
axes[1].set_xlabel('时刻 / h')
fig.suptitle('问题4 固定电价与波动电价曲线对比', fontsize=13)
fig.tight_layout(rect=(0, 0, 1, 0.97))
fig.savefig(PIC / 'q4_price_compare.png')
plt.close(fig)
pr('saved q4_price_compare.png')

# ================= 图6: 固定 vs 波动电价下 Q2/Q3 总电费 =================
fig, ax = plt.subplots(figsize=(7.5, 4.8))
x = np.arange(2)
w = 0.32
b1 = ax.bar(x - w / 2, [q2f / 1e4, q3f / 1e4], width=w,
            color='#4878a8', label='固定电价（附件1）')
b2 = ax.bar(x + w / 2, [q2v / 1e4, q3v / 1e4], width=w,
            color='#e67e22', label='波动电价（附件4）')
for bs in (b1, b2):
    for b in bs:
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 8,
                '%.2f' % b.get_height(), ha='center', fontsize=9)
for xi, (vf, vv) in enumerate([(q2f, q2v), (q3f, q3v)]):
    ax.text(xi + w / 2, vv / 1e4 + 55, '+%.2f%%' % (100 * (vv - vf) / vf),
            ha='center', fontsize=9, color='#c0392b')
ax.set_xticks(x)
ax.set_xticklabels(['Q2 理想情形（光伏已知）', 'Q3 滚动调整'])
ax.set_ylabel('总电费 / 万元')
ax.set_ylim(0, max(q3v, q3f) / 1e4 * 1.2)
ax.set_title('问题4 固定/波动电价下全年总电费对比（334天）')
ax.legend(loc='upper left', framealpha=0.9)
fig.tight_layout()
fig.savefig(PIC / 'q4_cost_compare.png')
plt.close(fig)
pr('saved q4_cost_compare.png')

# ============ 图7: 三方案×两种电价 全年总电费对比（6柱） ============
fig, ax = plt.subplots(figsize=(8.6, 5.0))
grp = ['Q2 理想情形\n(光伏已知)', 'Q3 滚动调整', 'Q3 对照组\n(仅0:00计划)']
vf = np.array([q2f, q3f, ctf]) / 1e4
vv = np.array([q2v, q3v, ctv]) / 1e4
x = np.arange(3)
w = 0.34
b1 = ax.bar(x - w / 2, vf, width=w, color='#4878a8',
            label='固定电价（附件1）')
b2 = ax.bar(x + w / 2, vv, width=w, color='#e67e22',
            label='波动电价（附件4）')
for bs in (b1, b2):
    for b in bs:
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 12,
                '%.2f' % b.get_height(), ha='center', fontsize=9)
ax.text(1, vf[1] + 120,
        '滚动较对照组省 %.2f 万元 (%.2f%%)'
        % ((ctf - q3f) / 1e4, 100 * (ctf - q3f) / ctf),
        ha='center', fontsize=9, color='#c0392b')
ax.text(1 + w / 2, vv[1] + 120,
        '%.2f%%' % (100 * (ctv - q3v) / ctv),
        ha='center', fontsize=9, color='#c0392b')
ax.set_xticks(x)
ax.set_xticklabels(grp)
ax.set_ylabel('总电费 / 万元')
ax.set_ylim(0, vv.max() * 1.22)
ax.set_title('问题4 三种方案在固定/波动电价下的全年总电费对比（334天）')
ax.legend(loc='upper right', framealpha=0.9)
fig.tight_layout()
fig.savefig(PIC / 'q4_four_plan.png')
plt.close(fig)
pr('saved q4_four_plan.png')

pr('ALL DONE (Q4)')
