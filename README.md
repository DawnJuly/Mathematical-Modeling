# 2026 国赛 C 题解题仓库 —— 文件说明

本仓库是 2026 年全国大学生数学建模竞赛 C 题（微网与外部电网电力调控策略）的完整工作区：
题目与参考材料、附件数据、求解程序、图表、以及最终论文的 LaTeX 工程。

权威产物只有两份：

- 论文：`latex/论文.tex`（主控）→ 编译得 `latex/论文.pdf`
- 结果：`C题/附件/附件5/`（提交口径）与 `C题/结果/`（输出副本）

其余目录都是过程材料、参考资料或旧版本的产物。

---

## 目录总览

```
math/
├── README.md                    本文件
├── .gitignore                   忽略规则
├── format2026.doc               赛方格式文件
├── 2026数学建模国赛论文.docx      Word 路线旧产物
├── make_paper.py                生成上面 docx 的脚本
├── make_refs.py                 生成 C题/thesis/参考文献.docx 的脚本
│
├── latex/                       论文工程（LaTeX，当前权威版）
│   ├── 论文.tex                 主控文件，按序 \input 各节
│   ├── 0.摘要.tex … 12.结论.tex  分节正文
│   ├── format.cls               CUMCM 赛方模板
│   ├── fonts/                   中文字体（SourceHanSerifCN）
│   ├── 求解/                    求解程序、数据预处理、图表、结果
│   ├── 结果/                    预留空目录
│   ├── 论文.pdf / 论文.xdv      编译产物
│   └── 论文.aux/.log/.out/...   编译中间产物（被忽略）
│
├── C题/                         本次赛题工作区
│   ├── C题.pdf                  赛题原文
│   ├── pdf_raw.txt              C题.pdf 的文本转出，便于检索
│   ├── showPicture.png          赛题配图
│   ├── 数学建模竞赛论文的写作方法_韩中庚.pdf   写作规范，评改依据
│   ├── 数学建模论文AI痕迹自动检测与诊断提示词.docx  AI 痕迹自查方案
│   ├── 成品论文.pdf              早期 Word 版论文导出
│   ├── 附件/                    附件工作副本（附件5 已填）
│   ├── 附件备份/                题目原始数据（禁止修改）
│   ├── 结果/                    求解输出 xlsx 与运行日志
│   ├── code/                    早期求解程序（已被 latex/求解/ 取代）
│   ├── pic/                     早期绘图脚本与图片
│   ├── txt/                     参考材料的纯文本抽取
│   └── thesis/参考文献.docx      参考文献草稿
│
├── papers_txt/                  12 篇历年优秀论文的纯文本版
└── 2021/ 2023/ 2024/            历年 C 题真题与优秀论文
```

---

## latex/ —— 论文工程

**主控文件 `论文.tex`**：设定题号、报名号、组别、学校、队员，然后按下面的顺序 `\input` 各节：

`0.摘要` → `1.问题重述` → `2.问题分析` → `3.模型假设` → `4.符号说明` → `5.模型的建立与求解`（含 `5.1`–`5.4` 四个问题，每个问题下再分 `具体分析 / 模型准备 / 模型建立 / 模型求解` 四小节）→ `6.模型检验` → `7.模型评价` → `8.模型改进推广` → `12.结论` → `9.AI说明` → `10.参考文献` → `11.附录`。

注意 `12.结论` 在 `9.AI说明` 之前被引入，这是有意安排的编排顺序，不是错误。

**同目录其余文件**：

- `format.cls`：赛方模板类，不要改。
- `fonts/`：模板需要的中文字体，`论文.pdf` 的中文排版靠它。
- `论文.pdf`：编译成品。`论文.xdv`、`论文.aux`、`论文.log`、`论文.out`、`论文.fls`、`论文.fdb_latexmk`、`_compile1.log`、`_fonts_ready` 都是可重新生成的中间产物，已在 `.gitignore` 中排除。
- `结果/`：空目录，预留位置，当前无内容。

### latex/求解/ —— 现行求解程序

公共模块与目录：

| 文件 | 作用 |
| --- | --- |
| `_common.py` | 公共工具（路径解析、Excel 读写、绘图样式等），被各问题脚本 `from _common import *` |
| `_models.py` | 微网购电调度 LP 建模与附件数据读取 |
| `稳健性检验.py` | 模型稳健性检验，出 `图片/图6-1_稳健性检验.png` |
| `预处理数据.csv` | 问题一预处理后的中间数据 |
| `结果/` | 五个提交件的最新副本：`result1.xlsx`、`result2.xlsx`、`result3.xlsx`、`result4-2.xlsx`、`result4-3.xlsx` |

四个问题各占一个子目录，内部结构一致（`问题X.py` + `图片/` + `结果/`）：

- `问题一/`：全年购电调度；6 张图（`图1-1`…`图1-6`）；`结果/result1.xlsx`
- `问题二/`：日尺度滚动调度；9 张图（`图2-1`…`图2-9`）；`结果/result2.xlsx`
- `问题三/`：光伏预报偏差下的滚动调整；7 张图（`图3-1`…`图3-7`）；`结果/result3.xlsx`
- `问题四/`：电价波动情景；6 张图（`图4-1`…`图4-6`）；`结果/result4-2.xlsx`、`result4-3.xlsx`

四个 `问题X.py` 都没有 `if __name__ == "__main__"` 入口，直接跑整个文件即可；脚本用 `sys.path` 指到上级目录来导入 `_common`/`_models`，所以从任意目录运行都能找到模块。

---

## C题/ —— 赛题工作区

### 题目与参考件

- `C题.pdf`：赛题原文；`pdf_raw.txt` 是它的文本转出，便于全文检索。
- `数学建模竞赛论文的写作方法_韩中庚.pdf`：写作规范，论文评改的依据。
- `数学建模论文AI痕迹自动检测与诊断提示词.docx`：AI 写作痕迹的自查与修改方案。
- `成品论文.pdf`：早期 Word 路线的论文导出，仅作对比，不是当前版本。

### 附件、附件备份、结果 —— 三者的对应关系

这是本仓库最容易混淆的地方，务必分清：

| 目录 | 性质 | 内容 |
| --- | --- | --- |
| `附件备份/` | **题目原始数据，禁止修改** | `附件1.xlsx`~`附件4.xlsx`；`附件5/` 是赛题发的**空白提交模板**（`result1/2/3/4-2/4-3.xlsx`） |
| `附件/` | 工作副本，可写 | `附件1.xlsx`~`附件4.xlsx` 与备份逐字节相同；`附件5/` 是**已填好的结果** |
| `结果/` | 求解输出与日志 | 五个 `result*.xlsx` 输出副本，加 `q2/q3/q4/q4_corr/q5/sens_r1r3` 六个运行日志 |

区分依据：`附件备份/附件5/` 的文件明显偏小（模板只有表头，如 `result2.xlsx` 18397 字节），`附件/附件5/` 同一文件已填入数据（`result2.xlsx` 350137 字节）。

`C题/result1.xlsx`（根目录下这一个）是脚本重跑时在赛题目录根落下的工作副本，不提交，已在 `.gitignore` 中排除；正式版只认 `附件/附件5/` 与 `结果/`。

### code/ —— 早期求解程序

第一版求解脚本，后来由 `latex/求解/` 取代，保留备查：

- `lp_core.py`：问题三、四共用的 LP 核心（注：其中注释提到的 `explore_fc2.py`、`explore_fc3.py` 两个探索脚本在本仓库中并不存在）
- `q1.py`、`q2.py`、`q3.py`、`q4.py`、`q4_corr.py`、`q5_sensitivity.py`、`sens_r1r3.py`

`__pycache__/` 是 Python 缓存，被忽略。

### pic/ —— 早期绘图

`qic1.py`~`qic4.py` 四个绘图脚本，加 15 张图：`q1_power_dispatch.png`、`q1_price_load_pv.png`、`q1_soc.png`、`q2_daily_cost.png`、`q2_four_days.png`、`q2_soc_heatmap.png`、`q3_cost_compare.png`、`q3_cum_saving.png`、`q3_err_boxplot.png`、`q3_forecast_error.png`、`q3_forecast_vs_actual.png`、`q3_plan_vs_adj.png`、`q4_cost_compare.png`、`q4_four_plan.png`、`q4_price_compare.png`。
现行图表在 `latex/求解/问题X/图片/`，此目录同样是早期版本。

### txt/ —— 检索用纯文本

- `paper_text.txt`：论文全文抽取，用于查重复表述
- `han_writing.txt`：韩中庚写作方法的文本
- `ai_detect.txt`：AI 痕迹检测方案的文本
- `tables_final.md`、`tables_q234.md`：论文表格的 Markdown 版

### thesis/

`参考文献.docx`，由根目录 `make_refs.py` 生成，供 Word 路线使用；LaTeX 论文的参考文献在 `latex/10.参考文献.tex`。

---

## papers_txt/ 与 2021/ 2023/ 2024/

`2021/`、`2023/`、`2024/` 三个目录收录历年 C 题真题与优秀论文，每个目录下另有一个存放真题与原始附件的子目录：

- `2021/`：4 篇优秀论文 PDF；`2021/C/` 放 `CUMCM2021-C.pdf` 及供应商、转运商数据与结果模板附件
- `2023/`：4 篇优秀论文 PDF；`2023/C题/` 放 `C题.pdf` 与 `附件1.xlsx`~`附件4.xlsx`
- `2024/`：4 篇优秀论文 PDF（文件名带双 `.pdf.pdf` 后缀）；`2024/C/` 放 `C题.pdf`、`附件1.xlsx`、`附件2.xlsx`，以及含结果模板的 `附件3/`（`result1_1.xlsx`、`result1_2.xlsx`、`result2.xlsx`）

`papers_txt/` 是这 12 篇优秀论文的纯文本版本，文件名去掉序号括号的 `.pdf` 后缀，与上面各目录的 PDF 一一对应（C038、C050、C063、C066、C085、C094、C126、C169、C228、C234、C235、C283）。用纯文本是为了快速检索章节结构、图表安排和写法，原文仍以 PDF 为准。

---

## 根目录文件

| 文件 | 说明 |
| --- | --- |
| `format2026.doc` | 赛方格式文件 |
| `make_paper.py` | 用 python-docx 生成 `2026数学建模国赛论文.docx` 的脚本 |
| `2026数学建模国赛论文.docx` | 上面脚本的产物，Word 路线的论文版本 |
| `make_refs.py` | 生成 `C题/thesis/参考文献.docx` |
| `.gitignore` | 见下 |

`.gitignore` 排除的内容：`papers_txt/_tmp_utf8/`、`__pycache__/` 与 `*.py[cod]`、Office 锁文件 `~$*`、系统垃圾文件 `Thumbs.db`/`Desktop.ini`/`.DS_Store`、`C题/_tmp/`、`C题/result*.xlsx` 与 `C题/q*_log.txt`、LaTeX 中间产物（`latex/**/*.aux|log|out|fls|fdb_latexmk|synctex.gz|xdv|auto/`）、`latex/**/_fonts_ready`。

---

## 常用命令

编译论文（在 `latex/` 下）：

```bash
latexmk -xelatex -interaction=nonstopmode 论文.tex
```

重跑某个问题的求解（在 `latex/求解/问题X/` 下，或任意目录）：

```bash
python 问题一/问题一.py
python 问题二/问题二.py
python 问题三/问题三.py
python 问题四/问题四.py
```

稳健性检验：

```bash
python 稳健性检验.py
```

重跑会在 `latex/求解/问题X/结果/` 与 `latex/求解/结果/` 下更新 `result*.xlsx`，并按需刷新 `图片/`。
