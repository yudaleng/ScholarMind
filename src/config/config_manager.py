import logging
import os
import json
import yaml
import sys

def load_config(config_path=None):
    """
    加载配置文件，获取API密钥和其他配置
    
    配置文件可以是YAML或JSON格式
    
    参数:
        config_path: 配置文件路径，如果为None则使用默认路径
    
    返回:
        配置字典
    """
    # 如果未指定配置文件路径，使用默认路径
    if config_path is None:
        default_yaml_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")
        
        if os.path.exists(default_yaml_path):
            config_path = default_yaml_path
        else:
            logging.error(f"未找到配置文件，请创建以下文件: {default_yaml_path}")
            logging.error("文件内容应包含: easyscholar_api_key, llm配置等")
            sys.exit(1)
    
    if not os.path.exists(config_path):
        logging.error(f"未找到配置文件: {config_path}")
        sys.exit(1)
    
    file_ext = os.path.splitext(config_path)[1].lower()
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            if file_ext in ['.yaml', '.yml']:
                config = yaml.safe_load(f)
            else:  # 默认作为JSON处理
                config = json.load(f)
    except Exception as e:
        logging.error(f"加载配置文件失败: {str(e)}")
        sys.exit(1)
    
    if "easyscholar_api_key" not in config:
        logging.error("配置文件中缺少easyscholar_api_key字段")
        sys.exit(1)
    
    if "llm" not in config:
        logging.info("配置文件中缺少llm字段（用于大语言模型配置），创建默认配置")
        config["llm"] = {
            "type": "vllm",
            "vllm_api_url": "http://localhost:8000/v1/completions",
            "vllm_api_key": "",
            "vllm_model": "qwen",
            "model_parameters": {
                "temperature": 0.7,
                "top_p": 0.9
            }
        }
    
    if "type" not in config["llm"]:
        config["llm"]["type"] = "vllm"
    
    if "model_parameters" not in config["llm"]:
        config["llm"]["model_parameters"] = {
            "temperature": 0.7,
            "top_p": 0.9
        }
    
    if "temperature" not in config["llm"]["model_parameters"]:
        config["llm"]["model_parameters"]["temperature"] = 0.7
    
    if "top_p" not in config["llm"]["model_parameters"]:
        config["llm"]["model_parameters"]["top_p"] = 0.9
    
    model_type = config["llm"]["type"].lower()
    
    if model_type == "vllm":
        if "vllm_api_url" not in config["llm"]:
            logging.info("LLM配置中缺少vllm_api_url字段（用于摘要理解生成）")
            logging.info("使用默认值: http://localhost:8000/v1/completions")
            config["llm"]["vllm_api_url"] = "http://localhost:8000/v1/completions"
        
        if "vllm_api_key" not in config["llm"]:
            config["llm"]["vllm_api_key"] = ""
            
        if "vllm_model" not in config["llm"]:
            config["llm"]["vllm_model"] = "qwen"
    
    elif model_type == "siliconflow":
        if "siliconflow_api_key" not in config["llm"]:
            logging.info("LLM配置中缺少siliconflow_api_key字段")
            sys.exit(1)
        
        if "siliconflow_base_url" not in config["llm"]:
            config["llm"]["siliconflow_base_url"] = "https://api.siliconflow.cn/v1"
        
        if "siliconflow_model" not in config["llm"]:
            config["llm"]["siliconflow_model"] = "deepseek-ai/DeepSeek-V3"
    
    elif model_type == "ollama":
        if "ollama_api_url" not in config["llm"]:
            config["llm"]["ollama_api_url"] = "http://localhost:11434/api"
        
        if "ollama_model" not in config["llm"]:
            config["llm"]["ollama_model"] = "llama3"
            
        if "ollama_api_key" not in config["llm"]:
            config["llm"]["ollama_api_key"] = ""
    
    if "vllm_api_url" not in config["llm"]:
        config["llm"]["vllm_api_url"] = "http://localhost:8000/v1/completions"
    if "vllm_api_key" not in config["llm"]:
        config["llm"]["vllm_api_key"] = ""
    if "vllm_model" not in config["llm"]:
        config["llm"]["vllm_model"] = "qwen"
    
    if "siliconflow_api_key" not in config["llm"] and model_type != "siliconflow":
        config["llm"]["siliconflow_api_key"] = ""
    if "siliconflow_base_url" not in config["llm"]:
        config["llm"]["siliconflow_base_url"] = "https://api.siliconflow.cn/v1"
    if "siliconflow_model" not in config["llm"]:
        config["llm"]["siliconflow_model"] = "deepseek-ai/DeepSeek-V3"
    
    if "ollama_api_url" not in config["llm"]:
        config["llm"]["ollama_api_url"] = "http://localhost:11434/api"
    if "ollama_model" not in config["llm"]:
        config["llm"]["ollama_model"] = "llama3"
    if "ollama_api_key" not in config["llm"]:
        config["llm"]["ollama_api_key"] = ""
    
    # 确保processing配置存在
    if "processing" not in config:
        config["processing"] = {
            "disable_summary": False,
            "batch_size": 16,
            "max_workers": 4
        }
    
    if "prompt" not in config:
        config["prompt"] = {
            "default_type": "medical",
            "templates_dir": "config/prompts",
        }
    
    return config 