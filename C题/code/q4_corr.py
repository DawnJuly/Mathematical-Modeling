# -*- coding: utf-8 -*-
"""问题四：电价统计量与"电价—负荷—光伏"相关分析复算（结果写入 q4_corr_log.txt）

复算论文 8.3 节引用的全部统计量：
  一、附件4 逐时段电价的 min / max / mean，以及日内极差（均值、最大）；
  二、12 个月的平均电价与日均光伏出力；
  三、六个相关系数：
      日均电价 × {问题四重算问题二的日购电量、日购电费、问题四滚动调整后当日总购电费}；
      日光伏出力 × {8:00-16:00 时段均价、全天均价}；
      日均电价 × 日总负荷。

口径说明：
- 输出窗口与 result4-2/result4-3 一致，取 2025-02-01 ~ 2025-12-31（日索引 31..364，共 334 天）；
- 日购电量/日购电费取 result4-2.xlsx「计划购电量」表末两列（末列-1 为全天购电量，
  末列为全天购电费）；问题四滚动调整后当日总购电费取 result4-3.xlsx「调整购电量」表末列；
- 日光伏出力 = 当日 144 个时段的实际光伏发电量之和（kWh）；日总负荷同法累加。
"""
import io
import numpy as np
import pandas as pd
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DT = 1.0 / 6.0
D0, D1 = 31, 365          # 2025-02-01 ~ 2025-12-31
SL = slice(D0, D1)

LOG = []


def log(s=''):
    LOG.append(s)
    print(s)


def corr(a, b):
    return float(np.corrcoef(np.asarray(a, float), np.asarray(b, float))[0, 1])


def month_label(dates, i):
    return '%d-%02d' % (dates[i].year, dates[i].month)


def main():
    load_df = pd.read_excel(BASE / '附件/附件2.xlsx', sheet_name='小区负载')
    pv_df = pd.read_excel(BASE / '附件/附件2.xlsx', sheet_name='光伏发电实际功率')
    dates = pd.to_datetime(load_df.iloc[:, 0])
    LOAD = load_df.iloc[:, 1:].to_numpy(float) * DT          # (365,144) kWh
    PV = pv_df.iloc[:, 1:].to_numpy(float) * DT
    PRICE4 = pd.read_excel(BASE / '附件/附件4.xlsx').iloc[:, 1:].to_numpy(float)
    price1 = pd.read_excel(BASE / '附件/附件1.xlsx')['电价'].to_numpy(float)

    p_day = PRICE4.mean(axis=1)                 # 日均电价
    p_mid = PRICE4[:, 48:96].mean(axis=1)       # 8:00-16:00 时段均价
    pv_day = PV.sum(axis=1)                     # 日光伏出力 kWh
    ld_day = LOAD.sum(axis=1)                   # 日总负荷 kWh

    log('=' * 72)
    log('一、附件4 逐时段电价统计（全 365 天，144 时段/天）')
    log('  min  = %.4f 元/kWh' % PRICE4.min())
    log('  max  = %.4f 元/kWh' % PRICE4.max())
    log('  mean = %.4f 元/kWh' % PRICE4.mean())
    rng = PRICE4.max(axis=1) - PRICE4.min(axis=1)
    log('  日内极差 mean = %.4f 元/kWh   max = %.4f 元/kWh' % (rng.mean(), rng.max()))
    log('  附件1 固定电价 mean = %.4f 元/kWh（与附件4 均值对比）' % price1.mean())
    assert abs(PRICE4.mean() - price1.mean()) < 1e-4

    log('')
    log('二、逐月平均电价与日均光伏出力（2025 全年）')
    for m in range(1, 13):
        idx = [i for i in range(365) if dates[i].month == m]
        log('  %2d月  均价 %.4f 元/kWh   日均光伏 %9.2f kWh'
            % (m, PRICE4[idx].mean(), pv_day[idx].mean()))
    mmin = min(range(1, 13), key=lambda m: p_day[[i for i in range(365)
                                                  if dates[i].month == m]].mean())
    mmax = max(range(1, 13), key=lambda m: p_day[[i for i in range(365)
                                                  if dates[i].month == m]].mean())
    pvmin = min(range(1, 13), key=lambda m: pv_day[[i for i in range(365)
                                                    if dates[i].month == m]].mean())
    log('  => 全年最高均价月 = %d 月，最低均价月 = %d 月，光伏最低月 = %d 月'
        % (mmax, mmin, pvmin))

    # ---- 结果文件 ----
    r42 = pd.read_excel(BASE / '结果/result4-2.xlsx', sheet_name='计划购电量')
    r43 = pd.read_excel(BASE / '结果/result4-3.xlsx', sheet_name='调整购电量')
    buy2 = r42.iloc[:, -2].to_numpy(float)          # 重算问题二 日购电量（334 天）
    cost2 = r42.iloc[:, -1].to_numpy(float)         # 重算问题二 日购电费
    cost3 = r43.iloc[:, -1].to_numpy(float)         # 滚动调整后 当日总购电费
    assert len(buy2) == 334 and len(cost2) == 334 and len(cost3) == 334

    p2 = p_day[SL]
    pv2 = pv_day[SL]
    ld2 = ld_day[SL]
    pm2 = p_mid[SL]

    log('')
    log('=' * 72)
    log('三、相关系数（窗口 2025-02-01 ~ 2025-12-31，334 天）')
    log('  [1] 日均电价 × 问题四重算问题二日购电量        r = %+.4f' % corr(p2, buy2))
    log('  [2] 日均电价 × 问题四重算问题二日购电费        r = %+.4f' % corr(p2, cost2))
    log('  [3] 日均电价 × 问题四滚动调整后当日总购电费    r = %+.4f' % corr(p2, cost3))
    log('  [4] 日光伏出力 × 8:00-16:00 时段均价           r = %+.4f' % corr(pv2, pm2))
    log('  [5] 日光伏出力 × 全天均价                     r = %+.4f' % corr(pv2, p2))
    log('  [6] 日均电价 × 日总负荷                       r = %+.4f' % corr(p2, ld2))

    log('')
    log('论文 8.3 节引用值：0.9747 / 0.9776 / 0.9794 / -0.4733 / -0.2600 / 0.9194')
    for name, val, ref in [
            ('[1]', corr(p2, buy2), 0.9747),
            ('[2]', corr(p2, cost2), 0.9776),
            ('[3]', corr(p2, cost3), 0.9794),
            ('[4]', corr(pv2, pm2), -0.4733),
            ('[5]', corr(pv2, p2), -0.2600),
            ('[6]', corr(p2, ld2), 0.9194)]:
        assert abs(val - ref) < 5e-4, (name, val, ref)
    log('  全部与论文一致（|差| < 5e-4）：校验通过')

    with io.open(BASE / 'q4_corr_log.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join(LOG))
    print('q4_corr_log.txt written')


if __name__ == '__main__':
    main()
