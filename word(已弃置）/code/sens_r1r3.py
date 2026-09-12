# -*- coding: utf-8 -*-
"""R1/R3 论文补充的复核计算（结果写入 C题/sens_r1r3_log.txt）

R3：问题1 无储能基准对照 + 光伏自发自用率（典型日=附件1）
R1：问题1 变流器功率上限 P_inv 灵敏度（4000/5000/6000 kW）
R1：问题3 紧急购电价倍数灵敏度（4/5/6，全年 334 天滚动口径）

说明：
- 问题1 LP 与 q1.py 完全一致：SOC[0]=6000 kWh 固定 + 日循环闭合，仅把变流器
  功率上限参数化（PMAX = P_inv * DT）。
- 问题3 复用 lp_core.q3_year，通过 monkeypatch lp_core.EMERG 实现。
"""
import io
import numpy as np
import pandas as pd
from scipy.optimize import linprog
from scipy.sparse import lil_matrix

import lp_core as C

T, DT = C.T, C.DT
D0, D1 = C.OUT_START, 365
BASE = C.BASE

LOG = []


def log(s=''):
    LOG.append(s)
    print(s)


def q1_full(pmax_kw, eta=0.9):
    """问题1 典型日 LP，返回 (购电费, buy, ch, dis, soc)。"""
    a1 = pd.read_excel(BASE / '附件/附件1.xlsx')
    price = a1['电价'].to_numpy(float)
    load = a1['小区负载'].to_numpy(float) * DT
    pv = a1['光伏发电预测功率'].to_numpy(float) * DT
    pmax = pmax_kw * DT

    N = 4 * T + 1
    ib, ic, id_, is_ = 0, T, 2 * T, 3 * T
    c = np.zeros(N)
    c[ib:ib + T] = price
    Aeq = lil_matrix((T + 1, N))
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
    soc_b = [(C.SOC_LO, C.SOC_HI)] * (T + 1)
    soc_b[0] = (6000.0, 6000.0)          # 附录1 题给 0:00 初值，与 q1.py 一致
    bounds = [(0, None)] * T + [(0, pmax)] * (2 * T) + soc_b
    res = linprog(c, A_ub=Aub.tocsr(), b_ub=pv - load, A_eq=Aeq.tocsr(),
                  b_eq=np.zeros(T + 1), bounds=bounds, method='highs')
    assert res.status == 0, res.message
    x = res.x
    buy = x[ib:ib + T]
    ch = x[ic:ic + T]
    dis = x[id_:id_ + T]
    soc = x[is_:is_ + T + 1]
    return float(price @ buy), buy, ch, dis, soc


def main():
    a1 = pd.read_excel(BASE / '附件/附件1.xlsx')
    price = a1['电价'].to_numpy(float)
    load_e = a1['小区负载'].to_numpy(float) * DT
    pv_e = a1['光伏发电预测功率'].to_numpy(float) * DT

    log('=' * 72)
    log('R3 问题1：无储能基准与光伏自发自用率（典型日）')
    # 无储能：光伏优先供本地，缺口购电
    buy0 = np.maximum(load_e - pv_e, 0.0)
    cost0 = float(price @ buy0)
    sc0 = float(np.minimum(pv_e, load_e).sum() / pv_e.sum())
    log('  无储能购电费 = %.4f 元' % cost0)
    log('  无储能购电量 = %.4f kWh' % buy0.sum())
    log('  无储能光伏自发自用率 = %.4f%%' % (sc0 * 100))

    cost1, buy1, ch1, dis1, soc1 = q1_full(5000.0)
    # 弃光 = 能量平衡残差 buy+pv+dis-load-ch（非负，LP 约束保证）
    curt = buy1 + pv_e + dis1 - load_e - ch1
    sc1 = float((pv_e.sum() - curt.sum()) / pv_e.sum())
    log('  有储能购电费 = %.4f 元 (q1 基准 35126.95)' % cost1)
    assert abs(cost1 - 35126.95) < 0.01, cost1
    save = cost0 - cost1
    log('  储能节省 = %.4f 元 (%.4f%%)' % (save, save / cost0 * 100))
    log('  有储能弃光量 = %.4f kWh' % curt.sum())
    log('  有储能光伏自发自用率 = %.4f%%' % (sc1 * 100))
    log('  光伏消纳率提升 = %.4f 个百分点' % ((sc1 - sc0) * 100))
    log('  0:00 储电量 %.4f  24:00 储电量 %.4f' % (soc1[0], soc1[-1]))

    log('')
    log('=' * 72)
    log('R1 问题1：变流器功率上限 P_inv 灵敏度')
    for pk in (4000.0, 5000.0, 6000.0):
        v, _, _, _, _ = q1_full(pk)
        log('  P_inv=%5.0f kW : 购电费 %.4f 元  相对基准 %+.4f%%'
            % (pk, v, (v - cost1) / cost1 * 100))

    log('')
    log('=' * 72)
    log('R1 问题3：紧急购电价倍数灵敏度（全年 334 天滚动）')
    D = C.load_data()
    price1, FC, LOAD, PV = D['price1'], D['FC'], D['LOAD'], D['PV']
    vals = {}
    for em in (4.0, 5.0, 6.0):
        old = C.EMERG
        C.EMERG = em
        try:
            adj = C.q3_year(price1, FC, LOAD, PV, adjust=True)
        finally:
            C.EMERG = old
        vals[em] = sum(adj[d]['total'] for d in range(D0, D1))
        log('  EMERG=%.1f : 滚动总电费 %.2f 元' % (em, vals[em]))
    log('  (基准 EMERG=5.0 应对应 q3 日志 17000834.39)')
    assert abs(vals[5.0] - 17000834.39) < 1.0, vals[5.0]
    for em in (4.0, 6.0):
        log('  EMERG=%.1f 相对基准变化 %+.4f%%' %
            (em, (vals[em] - vals[5.0]) / vals[5.0] * 100))

    log('')
    log('done.')
    with io.open(BASE / 'sens_r1r3_log.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join(LOG))
    log('sens_r1r3_log.txt written')


if __name__ == '__main__':
    main()
