# ScholarMind

<div align="center">
  <img src="images/image.png" alt="ScholarMind Logo" width="400">
</div>

> 🚀 ScholarMind 是一款强大的学术文献处理工具，专为研究人员打造。支持多源数据整合、文献去重、期刊指标分析以及AI驱动的摘要理解功能。

---
简体中文 | [English](https://github.com/yudaleng/ScholarMind/blob/main/README.md)
## ✨ 特性亮点

- 📚 **多数据源集成**：支持 PubMed、Web of Science、ScienceDirect 等数据库  
- 🔁 **智能去重**：自动检测并清理重复文献条目  
- 📊 **期刊指标分析**：通过 EasyScholar API 获取 SCI 影响因子、分区等信息  
- 🧠 **AI 摘要理解**：利用大语言模型提取摘要核心信息  
- 🧰 **自定义提示词模板**：支持不同专业领域配置模板  
- ⚡ **高效批处理**：适用于大规模文献数据的处理分析

---

## 🛠 安装指南

### ✅ 环境要求

- Python >= 3.8
- pip 包管理器

### 📦 安装步骤

```bash
# 克隆仓库
git clone https://github.com/yudaleng/ScholarMind.git
cd ScholarMind

# 创建并激活一个虚拟环境
conda create -n ScholarMind python=3.11
conda activate ScholarMind

# 安装依赖
pip install -r requirements.txt
```
---
## 🚀 快速开始

ScholarMind 提供两种主要的启动方式：

### 🌐 Web 界面

为了更友好的用户体验，您可以启动 Web 应用程序。只需运行 `launch_app.py`：

```bash
python launch_app.py
```

启动后，您可以通过 Web 浏览器访问应用程序。以下是主页的预览：

<div align="center">
  <img src="images/home.png" alt="Web Interface Home Page" width="800">
</div>

### ⚙️ 命令行与配置文件

对于批量处理和高级用法，您可以通过命令行并使用配置文件来运行 ScholarMind：

```bash
# 使用 src/config/config.yaml 运行
python main.py
# 指定自定义配置文件
python main.py --config custom_config.yaml
```

---

## ⚙️ 配置说明

在 `src/config` 目录下创建 `config.yaml`（可复制 `config.yaml.example` 进行修改）：
```yaml
# 【必填】从 https://www.easyscholar.cc/console/user/open 获取 API Key
easyscholar_api_key: "YOUR_EASYSCHOLAR_API_KEY"

# 期刊指标配置
journal_metrics:
  enabled: true # 设置为 false 可禁用期刊指标获取功能
  # 需要获取的指标类型，请参考 https://www.easyscholar.cc/console/user/open 附录1，填写对应缩写
  metrics_to_fetch:
    - "sciif"
    - "sci"
    - "sciUp"
  # （可选）将指标缩写映射为输出表格中的列名
  metrics_column_mapping:
    sciif: "impact_factor"
    sciUp: "中科院分区"

# 文献数据源配置
# 请从以下平台导出数据，并填写对应的文件路径：
# - PubMed: 选择 "All results"，Format 为 PubMed，导出为 .txt 文件
# - Web of Science（WOS）：导出为 Plain Text，Record Content 选择 "Full Record"
# - ScienceDirect：使用 "Export citation to text" 功能导出
sources:
  - type: "pubmed"
    path: "data/input/pubmed-data.txt"
    enabled: true
  - type: "wos"
    path: "data/input/wos-data.txt"
    enabled: true
  - type: "sciencedirect"
    path: "data/input/sciencedirect-data.txt"
    enabled: true

# 输出配置
output:
  excel_path: "data/output/combined-output.xlsx"  # 结果输出的 Excel 路径
  separate_sheets: true  # 是否将不同来源的数据分在不同工作表中

# 大语言模型（LLM）配置
llm:
  enabled: true # 设置为 false 可禁用 LLM 摘要理解功能
  type: "vllm"  # 默认使用的模型类型，可选项包括 vllm / siliconflow / ollama 等
  vllm_api_url: "http://127.0.0.1:8000/v1/chat/completions"
  vllm_api_key: ""
  vllm_model: "qwen"

  siliconflow_api_key: "YOUR_SILICONFLOW_API_KEY"
  siliconflow_base_url: "https://api.siliconflow.cn/v1"
  siliconflow_model: "Pro/deepseek-ai/DeepSeek-V3"
  siliconflow_rpm: 1000   # SiliconFlow 每分钟请求数限制
  siliconflow_tpm: 50000 # SiliconFlow 每分钟令牌数限制

  ollama_api_url: "http://localhost:11434/api"
  ollama_model: "llama3"
  ollama_api_key: ""

  model_parameters:
    temperature: 0.7
    top_p: 0.9
    max_tokens: 4096 # 控制模型生成的最大令牌数

# 提示词配置
prompt:
  default_type: "medical"  # 默认使用的提示词类型，需对应 src/config/prompts 目录下的文件名
  templates_dir: "src/config/prompts"

# 数据处理参数
processing:
  disable_summary: false  # 是否禁用摘要生成
  batch_size: 16          # 批处理大小
  max_workers: 4          # 最大并发线程数
```
---

## 🧠 提示词模板

ScholarMind 提供多领域模板支持文献摘要理解：

### 医学模板（medical）

输出字段：
- `ai_summary`: 总结
- `research_purpose`: 研究目的
- `research_methods`: 研究方法
- `major_findings`: 主要发现
- `clinical_significance`: 临床意义

---

## ✏️ 创建自定义模板

在 `src/config/prompts/` 下新建 YAML 文件，例如 `my_template.yaml`：

````yaml
type: "my_template"
name: "我的自定义模板"
description: "这是一个自定义的提示词模板"

system: |
  你是一位专业的文献分析助手。

user_template: |
  请分析以下摘要并输出 JSON：
  {abstract}
  ```json
  {
    "field1": "字段1",
    "field2": "字段2",
    "field3": "字段3"
  }
  ```

fields:
  - "field1"
  - "field2"
  - "field3"

default_values:
  field1: ""
  field2: "未提供"
  field3: "未提供"
````

---

## 📂 支持字段

| 字段 | 说明 |
|------|------|
| `title` | 文章标题 |
| `abstract` | 摘要 |
| `authors` | 作者 |
| `journal` | 期刊名称 |
| `doi` | DOI |
| `pmid` | PubMed ID |
| `wos_id` | Web of Science ID |
| `publication_date` | 发表时间 |
| `source_type` | 数据源类型 |

---

## 📬 联系我们

如有任何问题，请提交 GitHub Issues 或发送邮件。

---

## ⭐ 鼓励我们

> 如果你喜欢 ScholarMind，请在 GitHub 上 star 一下，支持项目持续发展！