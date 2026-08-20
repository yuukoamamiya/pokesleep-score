# pokesleep-box-score

从 MuMu 模拟器批量采集 Pokémon Sleep 盒子详情，OCR 提取个体信息，并生成本地评分、大福对照、个人规则结果和带标记的盒子长图。

这个仓库的重点是“以后重新克隆，Agent 或人都能快速接手”：代码、算法规则和可公开数据进入 Git；截图、浏览器状态、进度与评分结果统一留在被忽略的 `workspace/`。

> 非 Pokémon、SELECT BUTTON、The Pokémon Company 或相关权利方的官方项目。游戏名称、角色、图像和其他素材的权利归各自权利人所有。

## 能做什么

- 通过 ADB 从 MuMu 采集每只宝可梦的四页详情，并支持断点续跑。
- 用 RapidOCR、图标匹配与合法组合约束识别物种、换皮形态、等级、技能、性格和三格食材。
- 以 Lv.70 培养上限进行本地评分，也可选择提交到大福复算。
- 对食材型的非 `AAA`/`ABB` 分布追加 `×0.70` 的个人规则，但保留原始大福结果。
- 生成 OCR 质检清单、CSV 汇总，以及标出増田/SS/未到 S 的盒子长图。

## 快速开始（Windows）

需要 Python 3.12+；完整采集还需要 MuMu 模拟器和可用的 ADB。

```powershell
git clone <你的仓库地址>
cd pokesleep-box-score
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\bootstrap.ps1
.\.venv\Scripts\pokesleep-score.exe doctor
.\.venv\Scripts\pokesleep-score.exe demo
```

`demo` 不需要 MuMu、不联网，也不含真实用户数据；结果写入 `workspace/demo/results/`。

Linux/macOS 可运行 `bash scripts/bootstrap.sh`。OCR、算法和演示可跨平台使用；现有 MuMu 自动采集流程是按 Windows/MuMu 的画面与 ADB 路径调校的。

## 实际工作流

1. 启动 MuMu，进入 Pokémon Sleep 的宝可梦盒子，并保持窗口、分辨率与缩放稳定。
2. 先检查环境：

   ```powershell
   pokesleep-score doctor
   ```

3. 完整采集、本地算分：

   ```powershell
   pokesleep-score full
   ```

4. 如需大福对照：

   ```powershell
   pokesleep-score full --with-daifuku
   ```

已有截图时可用 `pokesleep-score offline`；已有 `box_ocr.csv` 时可用 `pokesleep-score offline --reuse-ocr`。只重建质检、个人规则和长图时使用 `pokesleep-score report`。

可以用 `--workspace D:\somewhere\my-box` 改变私人工作目录，或设置环境变量 `POKESLEEP_WORKSPACE`。ADB 可通过 `POKESLEEP_ADB` 和 `POKESLEEP_ADB_SERIAL` 覆盖；大福代理可通过 `DAIFUKU_PROXY` 设置。

## 算法口径

- 统一评估到 Lv.70；主技能无论当前等级均按 Lv.5 上限计算。
- 子技能槽按 10/25/50/70/80 级解锁，因此 Lv.70 纳入前四槽。
- 树果型看总树果能量；食材型看食材产能及三格实际分布。
- 合法食材组合为 `AAA/AAB/AAC/ABA/ABB/ABC`；食材型只有 `AAA`、`ABB` 不受个人折扣，其余额外 `×0.70`。
- 蜥蜴王（ジュカイン）虽然游戏分类为技能型，本地评级按树果型口径处理。
- 伊布会枚举所有可选进化分支。
- 大福输出与个人修正分列保存，避免把个人偏好伪装成第三方原始结果。

精确定义和修改注意事项见 [docs/SCORING_POLICY.md](docs/SCORING_POLICY.md)。

## 数据来源与许可边界

评分所需的宝可梦、树果、食材、速度、性格、技能等结构化数据，来自/改编自 [bennyhe/pokeSleepCalc](https://github.com/bennyhe/pokeSleepCalc)，本仓库采用的数据快照对应上游提交 `332967486d840f72a02fdbcd591a55ed9d7c6c64`。具体文件和生成关系见 [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) 与 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

本仓库的 MIT License 只覆盖本项目原创代码和文档，不改变第三方数据、图像、商标或网站的原有权利状态。大福是可选的第三方服务，本项目与其无隶属关系；其页面变化可能导致自动化失效。

## 隐私与公开前检查

不要提交 `workspace/`、`pw-profile/`、截图、真实评分 CSV、浏览器会话或 ADB 调试图。发布前运行：

```powershell
python scripts/public_release_check.py
python -m unittest discover -s tests -v
```

更完整的目录说明、排错与贡献方式见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)、[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) 和 [CONTRIBUTING.md](CONTRIBUTING.md)。
