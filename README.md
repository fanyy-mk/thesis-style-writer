# thesis-style-writer

本科毕业论文风格模仿与「去 AI 味」写作工具：从范文提取**可量化的风格画像**，按章节生成中文论文正文，并用「词句 → 节奏 → 具体性」三层门禁强制去除 AI 腔。

核心不是同义词润色，而是让正文具备三样东西：**可核查的具体信息、真实的取舍与限制、自然的句段节奏**。目标是把论文写具体、写自然，而不是绕过检测器。

## 特性

- **量化风格画像**：从 `.docx/.txt/.md` 范文自动统计句长分布、段落节奏、标点密度、人称、具体性（数字/引用/英文术语）等基线。
- **分层去 AI 味检查**：A 级硬禁词 0 容忍、B 级配额词按千字限流、C 级节奏/结构告警、D 级内容空洞判定，输出 `总分 + 阻断项 + 配额 + 告警` 报告。
- **门禁通过才交付**：总分 ≥ 85 且阻断项为 0，未达标返回退出码 1。
- **基础 Word 导出**：Markdown → 宋体小四 / 1.5 倍行距 / 首行缩进的 `.docx` 初稿。
- **仅标准库**：核心分析（画像 + 检查）只用 Python 标准库，无需额外依赖。

## 安装

需要 Python 3.9+。

```bash
# 仅当需要把正文导出为 Word 时安装
pip install python-docx
```

核心功能（`style_profile.py`、`ai_check.py`）不需要任何第三方依赖。

## 快速开始

```bash
# 1. 建风格画像（从 3 篇以上同体裁范文）
python scripts/style_profile.py 范文1.docx 范文2.docx 范文3.docx \
  --name "本校某专业本科论文" \
  --json thesis/style-profile.json \
  --md thesis/style-profile-stats.md

# 2. 分章起草，逐章检查
python scripts/ai_check.py thesis/draft/ch1.md \
  --baseline thesis/style-profile.json \
  --json thesis/check-ch1.json

# 3. 合并全文后再次门禁检查
python scripts/ai_check.py thesis/final.md \
  --baseline thesis/style-profile.json \
  --json thesis/check-final.json

# 4. 导出 Word 初稿
python scripts/md2docx.py thesis/final.md thesis/final.docx --title "论文题目"
```

完整工作流、铁律与分章规范见 `SKILL.md` 和 `references/`。

## 目录结构

```
SKILL.md                  技能入口：工作流、铁律、分章规范
references/                参考文档
  style-profile-schema.md  风格画像模板与填写规范
  style-profile-example.md 填好的画像示例
  thesis-structure-zh.md   章节功能、篇幅、引用与图表规范
  ai-tells-zh.md           AI 腔分层清单与改写手术
  rewriting-playbook.md    三遍法与段落展开模型
  quality-gates.md         门禁口径、失败处理、交付清单
scripts/
  style_profile.py         范文 → 统计基线 + targets
  ai_check.py              草稿 → 分数、阻断项、配额、节奏、具体性报告
  md2docx.py               Markdown → 基础排版 Word（需 python-docx）
  ai_patterns.json         A/B/C 级规则库，可增删
  thesis_style_lib.py      共享分析库（仅标准库）
```

## 使用前提与边界

- **范文需自行提供**：本仓库不包含任何真实论文、同学作业或学校范文，也没有任何隐私数据。上传时已通过 `.gitignore` 排除 `范例/` 与 `thesis/` 工作目录。
- **不编造**：数据、文献、实验结果必须有来源；没有就写 `【待补：具体内容】`。
- **门禁是写作质量启发式，不是「AI 检测准确率」**：通过门禁 ≠ 保证「不是 AI 写的」，只是没有明显模板特征。事实、逻辑、引用真伪、数据一致性必须由作者本人负责。
- **导出的是初稿**：封面、目录、页眉页脚、页码、三线表需按学校模板套用。

## License

[MIT](LICENSE)
