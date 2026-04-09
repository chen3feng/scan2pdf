[English](README.md) | 简体中文

# scan2pdf

将扫描版 PDF 书籍转换为紧凑的文字 PDF，基于 OCR 技术。

输入一个大体积的扫描版 PDF（图片格式），对每一页进行 OCR 识别，输出一个轻量的文字版 PDF，排版清晰美观——通常可实现 **99% 以上的压缩率**。

## 功能特性

- **OCR 驱动转换** — 使用 Tesseract 从扫描页面中提取文字
- **字号感知渲染** — 从 OCR 数据中检测标题/正文字号，保留相对排版关系
- **单页保证** — 每一页扫描内容严格对应一页输出（内容溢出时自动缩小字号）
- **均匀垂直分布** — 文字均匀填满整个页面高度，而非堆积在顶部
- **封面页保留** — 封面页以压缩图片形式保留
- **并行处理** — 多线程 OCR，加速转换
- **打印机风格页码选择** — 支持 `1,3-5,10-20` 等语法指定处理页面

## scan2pdf vs ocrmypdf

两者都使用 Tesseract OCR，但**目标完全不同**：

| | **ocrmypdf** | **scan2pdf** |
|---|---|---|
| **目标** | 给扫描 PDF 添加隐藏文字层（可搜索/可复制） | 将扫描 PDF **重新生成**为纯文字 PDF |
| **输出** | 原始图片 + 透明文字叠加层 | 纯文字排版，丢弃原始图片 |
| **体积** | 与原文件大小相近（图片仍在） | **99% 以上压缩率**（只保留文字） |
| **外观** | 看起来和原件一模一样 | 重新排版的文字页面 |

**scan2pdf 的独特之处：**

- **极致压缩** — 190MB 的扫描书籍可压缩至几百 KB
- **智能排版重建** — 从 hOCR 边界框推算字号，区分标题与正文，均匀分布文字填满整页
- **严格单页对应** — 每页扫描内容只在对应的一页输出，内容溢出时自动缩小字号（最小 6pt）
- **封面页特殊处理** — 封面页保留为压缩图片，文字页转为纯文字
- **OCR 文本清洗流水线** — 修复 OCR 瑕疵、合并断行、过滤页眉页脚，输出干净可读的文字

**何时选择哪个：**

| 场景 | 推荐 |
|------|------|
| 需要保留原始扫描外观，只是想搜索/复制文字 | **ocrmypdf** |
| 需要极致压缩，在手机/Kindle 上阅读 | **scan2pdf** |
| 存档扫描文档，保持法律效力 | **ocrmypdf** |
| 大量扫描小说/教材，只关心文字内容 | **scan2pdf** |

> **一句话总结** — ocrmypdf 是给扫描件"贴上隐形字幕"，scan2pdf 是把扫描件"翻译成电子书"。

## 前置要求

- **Python** ≥ 3.10
- **Tesseract OCR** — [安装指南](https://github.com/tesseract-ocr/tesseract)
- **Poppler**（提供 `pdftoppm`）— [Windows](https://github.com/oschwartz10612/poppler-windows/releases)、[macOS](https://formulae.brew.sh/formula/poppler)（`brew install poppler`）、[Linux](https://poppler.freedesktop.org/)（`apt install poppler-utils`）

## 安装

```bash
# 克隆仓库
git clone <repo-url>
cd scan2pdf

# 安装依赖
pip install -r requirements.txt

# 或作为包安装
pip install .
```

## 使用方法

### 基本用法

```bash
# 转换整本书（输出：book-text.pdf）
python -m scan2pdf book.pdf

# 指定输出文件
python -m scan2pdf book.pdf -o output.pdf
```

### 快速测试

```bash
# 只转换第 3 到 10 页
python -m scan2pdf book.pdf -n 3-10

# 转换指定页面
python -m scan2pdf book.pdf -n 1,5,10-20
```

### 高级选项

```bash
# 自定义封面页、语言和并发数
python -m scan2pdf book.pdf --cover 1 2 3 --lang eng --workers 8

# 降低 DPI 以加快处理速度
python -m scan2pdf book.pdf --dpi 200

# 详细输出
python -m scan2pdf book.pdf -v      # INFO 级别
python -m scan2pdf book.pdf -vv     # DEBUG 级别

# 保留临时文件以便调试
python -m scan2pdf book.pdf --keep-temp
```

### 全部选项

| 选项 | 默认值 | 说明 |
|------|--------|------|
| `input` | *（必填）* | 输入的扫描版 PDF 文件 |
| `-o, --output` | `<input>-text.pdf` | 输出 PDF 文件 |
| `-n, --pages` | 全部 | 页码范围（如 `1-10`、`1,3,5-20`） |
| `--cover` | `1` | 作为封面/图片页处理的页码 |
| `--lang` | `eng` | OCR 语言 |
| `--dpi` | `300` | 页面渲染 DPI |
| `--cover-quality` | `60` | 封面页 JPEG 质量 |
| `--cover-max-width` | `1200` | 封面图片最大宽度（像素） |
| `--workers` | `4` | 并行 OCR 工作线程数 |
| `--tesseract` | `tesseract` | Tesseract 可执行文件路径 |
| `--keep-temp` | 关闭 | 保留临时文件以便调试 |
| `-v, --verbose` | 关闭 | 增加输出详细程度（`-v` INFO，`-vv` DEBUG） |

## 开发与测试

### 环境搭建

```bash
# 克隆并以可编辑模式安装
git clone https://github.com/chen3feng/scan2pdf.git
cd scan2pdf
pip install -e ".[fast]"

# 安装开发依赖
pip install ruff pytest
```

### 代码风格

本项目使用 [Ruff](https://docs.astral.sh/ruff/) 进行代码检查和格式化：

```bash
# 检查 lint 错误
ruff check .

# 自动修复 lint 错误
ruff check . --fix

# 检查代码格式
ruff format --check .

# 自动格式化代码
ruff format .
```

### 运行测试

```bash
# 运行全部测试
pytest tests/ -v

# 运行指定测试文件
pytest tests/test_text_cleaner.py -v

# 简短错误输出
pytest tests/ --tb=short
```

### 持续集成

每次向 `master` 分支 push 或提交 Pull Request 时，会自动触发 [GitHub Actions](.github/workflows/ci.yml)：

1. **Lint** — `ruff check` + `ruff format --check`
2. **Test** — 在 Python 3.10 / 3.11 / 3.12 / 3.13 上运行 `pytest`

## 架构

```
scan2pdf/
├── cli.py            # 命令行接口与参数解析
├── pipeline.py       # 编排完整的转换流程
├── pdf_splitter.py   # 将页面提取为图片（pikepdf + poppler）
├── ocr_engine.py     # 运行 Tesseract OCR，生成 hOCR
├── hocr_parser.py    # 解析 hOCR 输出，提取文字和字号
├── text_cleaner.py   # 清理 OCR 瑕疵，合并行为段落
├── pdf_generator.py  # 生成排版后的文字 PDF（ReportLab）
└── pdf_merger.py     # 合并各页 PDF 为最终输出
```

### 处理流程

```
扫描版 PDF
    │
    ├─ 封面页 ──→ 渲染为图片 ──→ JPEG 压缩 ──→ 封装为 PDF
    │
    └─ 文字页 ──→ 渲染为图片 ──→ Tesseract OCR ──→ 解析 hOCR
                                                        │
                       合并为最终 PDF ←── 生成 PDF ←── 清理文字
```

## 依赖

| 包 | 用途 |
|----|------|
| `pikepdf` | PDF 页面提取 |
| `pypdf` | PDF 读取与合并 |
| `reportlab` | 文字 PDF 生成 |
| `lxml` | hOCR（HTML/XML）解析 |
| `Pillow` | 图片处理 |

## 许可证

MIT
