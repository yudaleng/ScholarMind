# ScholarMind

<div align="center">
  <img src="docs/images/image.png" alt="ScholarMind Logo" width="400">
</div>

> 🚀 ScholarMind is a powerful academic literature processing tool, designed specifically for researchers. It supports multi-source data integration, literature deduplication, journal indicator analysis, and AI-driven abstract understanding features.

---
English | [简体中文](https://github.com/yudaleng/ScholarMind/blob/main/docs/README.zh-CN.md)
## ✨ Features

- 📚 **Multi-Source Integration**: Supports PubMed, Web of Science, ScienceDirect, and more  
- 🔁 **Smart Deduplication**: Automatically detects and removes duplicate entries  
- 📊 **Journal Metrics Analysis**: Fetches SCI impact factors and journal rankings via EasyScholar API  
- 🧠 **AI Abstract Understanding**: Uses large language models to extract key insights from abstracts  
- 🧰 **Custom Prompt Templates**: Allows customization for different domains  
- ⚡ **Efficient Batch Processing**: Handles large-scale data efficiently

---

## 🛠 Installation

### ✅ Requirements

- Python >= 3.8

### 📦 Steps

```bash
# Clone the repository
git clone https://github.com/yudaleng/ScholarMind.git
cd ScholarMind

# Create and activate a virtual environment
conda create -n ScholarMind python=3.11
conda activate ScholarMind

# Install dependencies
pip install -r requirements.txt
```

---


## 🚀 Quick Start

ScholarMind offers two primary ways to get started:

### 🌐 Web Interface

For a user-friendly experience, you can launch the web application. Simply run `launch_app.py`:

```bash
python launch_app.py
```

Once launched, you can access the application through your web browser. Here's a preview of the home page:

<div align="center">
  <img src="docs/images/home.png" alt="Web Interface Home Page" width="800">
</div>

### ⚙️ Command Line with Configuration File

For batch processing and advanced usage, you can run ScholarMind via the command line using a configuration file:

```bash
# Use src/config/config.yaml
python main.py
# Specify a custom config file
python main.py --config custom_config.yaml
```

---


## ⚙️ Configuration

Create `config.yaml` under `src/config` (or copy from `config.yaml.example`):

```yaml
# [Required] Get your API Key from: https://www.easyscholar.cc/console/user/open
easyscholar_api_key: "YOUR_EASYSCHOLAR_API_KEY"

# Journal metrics configuration
journal_metrics:
  enabled: true # Set to false to disable fetching journal metrics
  # Specify which metrics to fetch. Refer to Appendix 1 at https://www.easyscholar.cc/console/user/open for available abbreviations.
  metrics_to_fetch:
    - "sciif"
    - "sci"
    - "sciUp"
  # (Optional) Map metric abbreviations to column names in the output Excel
  metrics_column_mapping:
    sciif: "impact_factor"
    sciUp: "CAS_Zone"

# Source data configuration
# Please export and specify paths to your data files as follows:
# - PubMed: Export as PubMed format with "All results" selected, save as .txt file
# - Web of Science (WOS): Export as "Plain Text", and choose "Full Record" as Record Content
# - ScienceDirect: Use the "Export citation to text" feature
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

# Output configuration
output:
  excel_path: "data/output/combined-output.xlsx"  # Path for the final Excel output
  separate_sheets: true  # Whether to separate data from different sources into individual sheets

# Large Language Model (LLM) configuration
llm:
  enabled: true # Set to false to disable LLM summary generation
  type: "vllm"  # Available types: vllm / siliconflow / ollama
  vllm_api_url: "http://127.0.0.1:8000/v1/chat/completions"
  vllm_api_key: ""
  vllm_model: "qwen"

  siliconflow_api_key: "YOUR_SILICONFLOW_API_KEY"
  siliconflow_base_url: "https://api.siliconflow.cn/v1"
  siliconflow_model: "Pro/deepseek-ai/DeepSeek-V3"
  siliconflow_rpm: 1000   # Requests Per Minute limit for SiliconFlow
  siliconflow_tpm: 50000 # Tokens Per Minute limit for SiliconFlow

  ollama_api_url: "http://localhost:11434/api"
  ollama_model: "llama3"
  ollama_api_key: ""

  model_parameters:
    temperature: 0.7
    top_p: 0.9
    max_tokens: 4096 # Maximum number of tokens the model can generate

# Prompt template configuration
prompt:
  default_type: "medical"  # Default prompt type, should correspond to a file in src/config/prompts
  templates_dir: "src/config/prompts"

# Data processing settings
processing:
  disable_summary: false  # Whether to disable automatic summarization
  batch_size: 16          # Number of entries to process per batch
  max_workers: 4          # Number of concurrent threads
```

---

## 🧠 Prompt Templates

ScholarMind supports domain-specific prompt templates for abstract summarization.

### Example: `medical` template

Output fields:

- `ai_summary`: Summary
- `research_purpose`: Research Purpose
- `research_methods`: Methods
- `major_findings`: Findings
- `clinical_significance`: Significance

---

## ✏️ Create Custom Template

1. Create a YAML file under `src/config/prompts/`:
````yaml
type: "my_template"
name: "My Custom Template"
description: "This is a user-defined prompt template."

system: |
  You are a professional literature analysis assistant.

user_template: |
  Please analyze the abstract below and output as JSON:

  {abstract}

  ```json
  {
    "field1": "Content of field1",
    "field2": "Content of field2",
    "field3": "Content of field3"
  }
  ```

fields:
  - "field1"
  - "field2"
  - "field3"

default_values:
  field1: ""
  field2: "N/A"
  field3: "N/A"
````

2. Reference your template in `config.yaml`:

```yaml
prompt:
  default_type: "my_template"
```

---

## 📂 Supported Fields

Each entry should include the following:

| Field | Description |
|-------|-------------|
| `title` | Title |
| `abstract` | Abstract |
| `authors` | Authors |
| `journal` | Journal Name |
| `doi` | Digital Object Identifier |
| `pmid` | PubMed ID |
| `wos_id` | Web of Science ID |
| `publication_date` | Publication Date |
| `source_type` | Source (pubmed, wos, sciencedirect) |

---

## 📬 Contact

For issues or suggestions, please file an issue on [GitHub](https://github.com/yudaleng/ScholarMind/issues).

---

## ⭐ Show Support

> If you like ScholarMind, please give us a ⭐️ on GitHub to support the project!