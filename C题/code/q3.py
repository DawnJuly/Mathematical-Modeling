# -*- coding: utf-8 -*-
"""Q3: 基于滚动预报的购电调整 (MPC)。
0:00 用0:00预报做全天计划; 6:00/12:00/18:00 用最新预报重解剩余时段LP。
对照组: 只用0:00计划交割, 缺口全部按5倍电价紧急购电。
输出: result3.xlsx (并覆盖 附件/附件5/result3.xlsx), q3_log.txt"""
import shutil
import time
import numpy as np
from pathlib import Path
from openpyxl import load_workbook
from lp_core import (load_data, q2_year, q3_year, fc_error_stats, write_result,
                     STAGES, BLOCKS, BNAMES, SIX_TIMES, FOUR_DAYS, DAYS_OUT,
                     SOC_LO, SOC_HI, T)

BASE = Path(__file__).resolve().parent.parent

t_start = time.time()
L = []  # 日志行

def log(s=''):
    L.append(s)
    print(s)

# ---------- 0. 空提交模板(原始文件, 来自 附件备份/附件5) ----------
BAK = BASE / '附件备份/附件5'
assert (BAK / 'result3.xlsx').exists(), '缺少空提交模板: %s' % (BAK / 'result3.xlsx')

# ---------- 1. 数据 ----------
D = load_data()
price1, dates = D['price1'], D['dates']
LOAD, PV, FC, HA = D['LOAD'], D['PV'], D['FC'], D['HA']
log('附件3 预报负值个数: %d (已clip到0)' % D['n_neg_fc'])

# ---------- 2. 预报映射约定验证 (约定B vs 约定A) ----------
log('')
log('===== 预报映射约定验证 =====')
log('约定B: 「预报k小时」对应发布时刻起第k个小时区间 [T+k-1, T+k), 即 lag=0')
log('约定A: 「预报k小时」对应提前一个小时的区间 [T+k-2, T+k-1), 即 lag=-1')
log('按发布时刻分组全年统计 (单位kW):')
log('%-8s %-6s %10s %10s %10s %8s' % ('发布时刻', '约定', 'MAE', '白天MAE', 'RMSE', 'corr'))
conv_tbl = []
for j, h0 in enumerate(STAGES):
    for lag, name in [(0, 'B'), (-1, 'A')]:
        errs, preds, acts = [], [], []
        for d in range(365):
            for k in range(1, 25):
                h_abs = h0 + k - 1 + lag
                dd = d + h_abs // 24
                if dd > 364:
                    continue
                errs.append(FC[d, j, k - 1] - HA[dd, h_abs % 24])
                preds.append(FC[d, j, k - 1])
                acts.append(HA[dd, h_abs % 24])
        errs = np.array(errs); preds = np.array(preds); acts = np.array(acts)
        mae = np.abs(errs).mean()
        rmse = np.sqrt((errs ** 2).mean())
        corr = np.corrcoef(preds, acts)[0, 1]
        day = (np.maximum(preds, acts) > 100)
        dmae = np.abs(errs[day]).mean()
        log('%-8s %-6s %10.1f %10.1f %10.1f %8.4f' %
            ('%d:00' % h0, name, mae, dmae, rmse, corr))
        conv_tbl.append((h0, name, mae, dmae, rmse, corr))
log('结论: 4个发布时刻上约定B的MAE/白天MAE/RMSE/corr全面优于约定A,')
log('且约定B下0:00发布的预报1..24小时恰好覆盖当天0:00..24:00, 无缺口。采用约定B。')

# ---------- 3. Q2 基准复核 ----------
q2 = q2_year(price1)
q2_tot = sum(q2[d]['cost'] for d in DAYS_OUT)
log('')
log('Q2基准复核: 2.1-12.31 总电费 = %.2f 元 (result2 口径 12254765.72)' % q2_tot)
assert abs(q2_tot - 12254765.72) < 1.0

# ---------- 4. Q3 MPC 与对照 ----------
t0 = time.time()
q3 = q3_year(price1, FC, LOAD, PV, adjust=True)
log('Q3 MPC 全年求解耗时 %.1fs' % (time.time() - t0))
t0 = time.time()
ctrl = q3_year(price1, FC, LOAD, PV, adjust=False)
log('对照组(不调整) 全年求解耗时 %.1fs' % (time.time() - t0))

# ---------- 5. 四天明细 ----------
four_idx = [i for i, t in enumerate(dates)
            if t.strftime('%Y-%m-%d') in FOUR_DAYS]
for d in four_idx:
    r = q3[d]
    key = dates[d].strftime('%Y-%m-%d')
    log('')
    log('===== %s (day idx %d) =====' % (key, d))
    log('计划购电量合计: %.4f kWh   计划购电费: %.4f 元' %
        (r['plan'].sum(), r['plan_cost']))
    log('调整后购电量合计: %.4f kWh   当天实际总电费: %.4f 元' %
        (r['adj'].sum(), r['total']))
    for name, t in SIX_TIMES:
        log('  %s-%d:00 1小时: 计划 %.4f  调整后 %.4f kWh' %
            (name, int(name[:2]) + 1,
             r['plan'][t:t + 6].sum(), r['adj'][t:t + 6].sum()))
    for k, (a, b) in enumerate(BLOCKS):
        log('  %-11s 充电 %.4f  放电 %.4f' %
            (BNAMES[k], r['ch'][a:b].sum(), r['dis'][a:b].sum()))
    log('  0:00 储电量 %.4f   24:00 储电量 %.4f' % (r['soc'][0], r['soc'][-1]))
    log('  SOC min/max: %.4f / %.4f  (限值 %.0f/%.0f)' %
        (r['soc'].min(), r['soc'].max(), SOC_LO, SOC_HI))
    log('  费用分解: 计划 %.2f + 上调 %.2f - 下调回退 %.2f + 紧急 %.2f = %.2f 元' %
        (r['plan_cost'], r['up'], r['down'], r['emerg'], r['total']))
    log('  紧急购电量: %.6f kWh   对照组当天总电费: %.2f 元' %
        (r['e'].sum(), ctrl[d]['total']))

# ---------- 6. 全年汇总 ----------
def year_sum(res):
    c = dict(plan=0., up=0., down=0., emerg=0., total=0., e=0., nday=0)
    for d in DAYS_OUT:
        r = res[d]
        c['plan'] += r['plan_cost']; c['up'] += r['up']
        c['down'] += r['down']; c['emerg'] += r['emerg']
        c['total'] += r['total']; c['e'] += r['e'].sum()
        c['nday'] += int(r['e'].sum() > 1e-6)
    return c

y3, yc = year_sum(q3), year_sum(ctrl)
log('')
log('===== 全年汇总 (2025-02-01 ~ 2025-12-31, 334天) =====')
log('Q3(滚动调整): 计划 %.2f + 上调 %.2f - 下调回退 %.2f + 紧急 %.2f = 总电费 %.2f 元' %
    (y3['plan'], y3['up'], y3['down'], y3['emerg'], y3['total']))
log('  紧急购电总量 %.4f kWh, 非零天数 %d' % (y3['e'], y3['nday']))
log('对照组(仅0:00计划): 计划 %.2f + 紧急 %.2f = 总电费 %.2f 元' %
    (yc['plan'], yc['emerg'], yc['total']))
log('  紧急购电总量 %.4f kWh, 非零天数 %d' % (yc['e'], yc['nday']))
log('Q2(理想已知光伏) 总电费: %.2f 元' % q2_tot)
save_vs_ctrl = yc['total'] - y3['total']
log('滚动调整相对对照组节省: %.2f 元 (%.2f%%)' %
    (save_vs_ctrl, 100 * save_vs_ctrl / yc['total']))
gap_q2 = y3['total'] - q2_tot
log('滚动调整相对理想情形(Q2)仅高: %.2f 元 (%.2f%%)' %
    (gap_q2, 100 * gap_q2 / q2_tot))
log('结构性说明: LP平衡约束使交割缺口≈Σmax(最新预报误差,0), 故对照组紧急购电')
log('能量与电价无关; 滚动调整用更短提前期(更准)的预报, 正向预报误差减小,')
log('紧急购电量由 %.0f 降至 %.0f kWh, 同时付出上调/回退费用, 净节省为正。'
    % (yc['e'], y3['e']))

# ---------- 7. 预报误差统计 ----------
tbl, overall = fc_error_stats(D)
log('')
log('===== 附件3预报误差(约定B, 全年全部发布时刻, 单位kW) =====')
log('总体: MAE=%.2f RMSE=%.2f bias=%.2f' % overall)
log('%-6s %8s %10s %10s %10s' % ('提前k', '样本数', 'MAE', 'RMSE', '白天MAE'))
for k, n, mae, rmse, dmae in tbl:
    log('%-6d %8d %10.1f %10.1f %10.1f' % (k, n, mae, rmse, dmae))
log('结论: 提前时长越短误差越小(越近越准), 白天(功率>100kW)误差显著大于全天平均。')

# ---------- 8. 自验 ----------
log('')
log('===== 自验 =====')
ok = True
for tag, res in [('Q3', q3), ('对照', ctrl)]:
    for d in range(365):
        r = res[d]
        assert r['soc'].min() >= SOC_LO - 1e-6, (tag, d, r['soc'].min())
        assert r['soc'].max() <= SOC_HI + 1e-6, (tag, d, r['soc'].max())
        resid = r['adj'] + PV[d] + r['dis'] + r['e'] - LOAD[d] - r['ch']
        assert resid.min() > -1e-5, (tag, d, resid.min())
        assert (r['e'] >= 0).all()
        lb = price1 @ r['adj']
        assert r['total'] >= lb - 1e-4, (tag, d)
    log('%s: 365天 SOC∈[%.0f,%.0f]、能量平衡、e≥0、total≥Σprice·adj 全部通过'
        % (tag, SOC_LO, SOC_HI))
assert abs(q2_tot - 12254765.72) < 1.0
log('q2_year 复现 result2 总电费 12254765.72: 通过')

# ---------- 9. 写 result3.xlsx ----------
OUT3 = BASE / 'result3.xlsx'
n_em = write_result(BAK / 'result3.xlsx', OUT3,
                    dates, q3, with_adj=True)
shutil.copy(OUT3, BASE / '附件/附件5/result3.xlsx')
log('result3.xlsx 已生成并覆盖 附件/附件5/result3.xlsx, 紧急购电量sheet写入区间行数: %d' % n_em)

# sheet 结构复核
wb = load_workbook(OUT3, read_only=True)
for name, exp_col in [('计划购电量', 147), ('调整购电量', 147), ('充放电量', 6),
                      ('紧急购电量', 3)]:
    ws = wb[name]
    log('sheet %-6s: %d 行 x %d 列' % (name, ws.max_row, ws.max_column))
wb.close()
exp_rows = len(DAYS_OUT) * 6 + 1
wb = load_workbook(OUT3, read_only=True)
assert wb['计划购电量'].max_row == len(DAYS_OUT) + 1
assert wb['调整购电量'].max_row == len(DAYS_OUT) + 1
assert wb['充放电量'].max_row == exp_rows
wb.close()
log('sheet结构(335/335/%d 数据行)校验通过' % exp_rows)

log('')
log('总耗时 %.1fs' % (time.time() - t_start))
with open(BASE / 'q3_log.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(L))
print('q3_log.txt written')
