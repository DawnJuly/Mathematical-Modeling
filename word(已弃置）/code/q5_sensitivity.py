# -*- coding: utf-8 -*-
"""灵敏度分析（论文第九章）：
(1) 问题一：储能容量 12000±10% kWh、充放电效率 0.90±0.05 对典型日购电费的影响
    （LP 结构与 q1.py 完全一致：soc[0]=6000 kWh 固定 + 日循环闭合，仅参数化容量与效率）；
(2) 问题二：储能容量 ±10% 对全年(2.1-12.31, 334天)总电费的影响（理想光伏情形，
    通过 monkeypatch lp_core.SOC_LO/SOC_HI 实现，LP 与 q2.py 同构）；
(3) 问题三：光伏预报系统性偏差（FC×0.8 / ×1.0 / ×1.2）对全年滚动调度总电费
    及"MPC 调整 vs 不调整"节省率的影响。
口径与 q2/q3 日志一致：全年 = 2025-02-01~12-31 共 334 天（1 月为 SOC 预热期）。
"""
import numpy as np
import pandas as pd
from scipy.optimize import linprog
from scipy.sparse import lil_matrix

import lp_core as C

T, DT, PMAX = C.T, C.DT, C.PMAX
D0, D1 = C.OUT_START, 365          # 统计口径: 日索引 31..364


def q1_lp(S, eta):
    """问题一参数化 LP：容量 S(决定 SOC 盒 [0.1S, 0.9S])、效率 eta。数据=附件1。"""
    a1 = pd.read_excel(C.BASE / '附件/附件1.xlsx')
    price = a1['电价'].to_numpy(float)
    load = a1['小区负载'].to_numpy(float) * DT
    pv = a1['光伏发电预测功率'].to_numpy(float) * DT
    s_lo, s_hi = 0.1 * S, 0.9 * S

    N = 4 * T + 1
    ib, ic, id_, is_ = 0, T, 2 * T, 3 * T
    c = np.zeros(N)
    c[ib:ib + T] = price
    Aeq = lil_matrix((T + 1, N))
    beq = np.zeros(T + 1)
    for t in range(T):
        Aeq[t, is_ + t + 1] = 1.0
        Aeq[t, is_ + t] = -1.0
        Aeq[t, ic + t] = -eta
        Aeq[t, id_ + t] = 1.0 / eta
    Aeq[T, is_ + T] = 1.0
    Aeq[T, is_] = -1.0
    Aub = lil_matrix((T, N))
    for t in range(T):
        Aub[t, ib + t] = -1.0
        Aub[t, id_ + t] = -1.0
        Aub[t, ic + t] = 1.0
    soc_b = [(s_lo, s_hi)] * (T + 1)
    soc_b[0] = (6000.0, 6000.0)          # 附录1 题给 0:00 初值，与 q1.py 一致
    bounds = [(0, None)] * T + [(0, PMAX)] * (2 * T) + soc_b
    res = linprog(c, A_ub=Aub.tocsr(), b_ub=pv - load, A_eq=Aeq.tocsr(),
                  b_eq=beq, bounds=bounds, method='highs')
    assert res.status == 0, res.message
    return float(price @ res.x[ib:ib + T])


def q2_year_cost(S):
    """问题二全年总电费(334天)：容量 S -> SOC 盒 [0.1S, 0.9S]。"""
    old = (C.SOC_LO, C.SOC_HI)
    C.SOC_LO, C.SOC_HI = 0.1 * S, 0.9 * S
    try:
        out = C.q2_year(D['price1'])
    finally:
        C.SOC_LO, C.SOC_HI = old
    return sum(out[d]['cost'] for d in range(D0, D1))


def q3_year_totals(scale):
    """问题三全年总电费(334天)：预报 FC×scale，返回 (调整总费, 不调整总费)。"""
    adj = C.q3_year(D['price1'], D['FC'] * scale, D['LOAD'], D['PV'], adjust=True)
    no = C.q3_year(D['price1'], D['FC'] * scale, D['LOAD'], D['PV'], adjust=False)
    return (sum(adj[d]['total'] for d in range(D0, D1)),
            sum(no[d]['total'] for d in range(D0, D1)))


def main():
    print('=' * 72)
    print('(1) 问题一：容量与效率灵敏度（典型日=附件1，基准 35126.95）')
    base = q1_lp(12000.0, 0.9)
    print('  基准 S=12000, eta=0.90 : %.2f  (q1 日志 35126.95)' % base)
    assert abs(base - 35126.95) < 0.01, base
    for S in (13200.0, 10800.0):
        v = q1_lp(S, 0.9)
        print('  S=%7.0f (%+.0f%%) : %.2f  变化 %+.2f%%'
              % (S, (S / 12000 - 1) * 100, v, (v - base) / base * 100))
    for eta in (0.85, 0.95):
        v = q1_lp(12000.0, eta)
        print('  eta=%.2f        : %.2f  变化 %+.2f%%'
              % (eta, v, (v - base) / base * 100))

    print('=' * 72)
    print('(2) 问题二：容量灵敏度（全年334天理想光伏，基准 12254765.72）')
    base2 = q2_year_cost(12000.0)
    print('  基准 S=12000 : %.2f  (q2 日志 12254765.72)' % base2)
    assert abs(base2 - 12254765.72) < 0.01, base2
    for S in (13200.0, 10800.0):
        v = q2_year_cost(S)
        print('  S=%7.0f (%+.0f%%) : %.2f  变化 %+.2f%%'
              % (S, (S / 12000 - 1) * 100, v, (v - base2) / base2 * 100))

    print('=' * 72)
    print('(3) 问题三：光伏预报系统性偏差灵敏度（全年334天滚动）')
    for scale in (0.8, 1.0, 1.2):
        tot_adj, tot_no = q3_year_totals(scale)
        sav = (tot_no - tot_adj) / tot_no * 100
        print('  预报x%.1f: 滚动调整 %s 元 | 不调整 %s 元 | 节省 %.2f%%'
              % (scale, format(tot_adj, '.2f'), format(tot_no, '.2f'), sav))
    print('  (基准 x1.0 应对应 q3 日志: 调整 17000834.39 / 不调整 17400028.28 / 节省 2.29%)')


if __name__ == '__main__':
    D = C.load_data()
    main()
