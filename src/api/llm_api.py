import requests
import json
from typing import List, Dict, Optional, Any, Tuple
import time
import logging
from abc import ABC, abstractmethod
import concurrent.futures
import re
from tqdm import tqdm

from src.api.prompt_templates import PromptTemplate, create_prompt_template, OutputConfig
from openai import OpenAI, RateLimitError

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)


class ResponseParser:
    """响应解析器，用于处理LLM返回的响应"""

    @staticmethod
    def parse_json_response(text: str, fields: List[str], default_values: Dict[str, str] = None) -> Dict[str, str]:
        if default_values is None:
            default_values = {field: "未识别" if field != "ai_summary" else "" for field in fields}

        result = dict(default_values)

        if not text or not isinstance(text, str):
            return result

        try:
            # 1. 预处理文本：移除可能的代码块标记和多余空格
            cleaned_text = text.replace('```json', '')
            cleaned_text = cleaned_text.replace('```', '').strip()

            # 2. 尝试直接解析整个文本为JSON
            try:
                data = json.loads(cleaned_text)
                if isinstance(data, dict):
                    for field in fields:
                        if field in data:
                            result[field] = data.get(field, default_values[field])
                    return result
            except json.JSONDecodeError:
                pass

            # 3. 在文本中查找可能的JSON块
            json_pattern = r'\{[\s\S]*\}'
            match = re.search(json_pattern, cleaned_text)
            if match:
                try:
                    json_str = match.group(0)
                    data = json.loads(json_str)
                    if isinstance(data, dict):
                        for field in fields:
                            if field in data:
                                result[field] = data.get(field, default_values[field])
                        return result
                except json.JSONDecodeError:
                    pass

            # 4. 使用正则表达式从文本中提取字段值
            for field in fields:
                pattern = rf'"{field}"\s*:\s*"([^"]+)"'
                match = re.search(pattern, cleaned_text)
                if match:
                    result[field] = match.group(1)
                    continue

                # 尝试不同格式的字段匹配
                pattern = rf'"{field}"\s*:\s*(.+?)(?:,|\n|}})'
                match = re.search(pattern, cleaned_text)
                if match:
                    value = match.group(1).strip().strip('"').strip("'")
                    result[field] = value

            # 5. 特殊处理ai_summary - 如果找不到，可能整个文本就是摘要
            if 'ai_summary' in fields and result['ai_summary'] == default_values['ai_summary']:
                if not re.search(r'^\s*\{', cleaned_text) and len(cleaned_text) > 10:
                    result['ai_summary'] = cleaned_text

            return result
        except Exception as e:
            logger.error(f"解析响应失败: {str(e)}")
            return result


class BaseLLMClient(ABC):
    """LLM客户端基类，定义通用接口"""

    @abstractmethod
    def generate_summary(self, abstract: str, prompt_type: str = "medical") -> Dict[str, str]:
        """生成摘要的抽象方法"""
        pass

    @abstractmethod
    def batch_generate_summaries(self, abstracts: List[str],
                                 batch_size: int = 16, prompt_type: str = "medical",
                                 progress_callback: Optional[callable] = None) -> List[Dict[str, str]]:
        """批量生成摘要的抽象方法"""
        pass


class VllmClient(BaseLLMClient):
    """
    VLLM客户端类，用于与本地VLLM API服务交互
    """

    def __init__(self, api_url: str, api_key: Optional[str] = None,
                 model: str = "qwen", max_retries: int = 3, timeout: int = 120,
                 temperature: float = 0.7, top_p: float = 0.9, max_tokens: int = 4096):
        """
        初始化VLLM客户端

        参数:
            api_url: VLLM服务的API URL
            api_key: 可选的API密钥
            model: 使用的模型名称
            max_retries: 最大重试次数
            timeout: 请求超时时间(秒)
            temperature: 温度参数，控制生成文本的随机性
            top_p: Top-p 采样参数
            max_tokens: 控制生成的最大令牌数
        """
        self.api_url = api_url
        if api_key != "":
            self.api_key = api_key
        else:
            self.api_key = None
        self.model = model
        self.max_retries = max_retries
        self.timeout = timeout
        self.temperature = temperature
        self.top_p = top_p
        self.max_tokens = max_tokens

    def _prepare_headers(self) -> Dict[str, str]:
        """准备请求头"""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def generate_summary(self, abstract: str, prompt_type: str = "medical") -> Dict[str, str]:
        """
        生成摘要理解

        参数:
            abstract: 文章摘要文本
            prompt_type: 提示词类型

        返回:
            包含提示词类型定义的字段的字典
        """
        if not abstract or not isinstance(abstract, str):
            # 获取默认值
            default_values = OutputConfig.get_default_values(prompt_type)
            return default_values

        # 使用提示词模板
        prompt_template = create_prompt_template(prompt_type)
        messages = prompt_template.get_messages(abstract=abstract)
        output_fields = prompt_template.get_output_fields()
        default_values = prompt_template.get_default_values()

        # 构造请求数据
        payload = {
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "top_p": self.top_p,
            "stop": None,
            "model": self.model
        }

        # 发送请求并重试
        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    self.api_url,
                    headers=self._prepare_headers(),
                    json=payload,
                    timeout=self.timeout
                )
                response.raise_for_status()
                result = response.json()

                if "choices" in result and len(result["choices"]) > 0:
                    answer = result.get("choices", [])[0].get("message", {}).get("content", "")
                    return ResponseParser.parse_json_response(answer, output_fields, default_values)
                else:
                    logger.warning(f"无效的API响应: {result}")
                    return default_values

            except Exception as e:
                logger.error(f"生成摘要时出错 (尝试 {attempt + 1}/{self.max_retries}): {str(e)}")
                if attempt == self.max_retries - 1:
                    return default_values
                time.sleep(2 ** attempt)  # 指数退避

        return default_values

    def batch_generate_summaries(self, abstracts: List[str],
                                 batch_size: int = 16, prompt_type: str = "medical",
                                 progress_callback: Optional[callable] = None) -> List[Dict[str, str]]:
        """
        批量生成摘要理解

        参数:
            abstracts: 文章摘要文本列表
            batch_size: 批处理大小，默认为16
            prompt_type: 提示词类型

        返回:
            生成的摘要字典列表
        """
        # 获取默认值
        prompt_template = create_prompt_template(prompt_type)
        default_values = prompt_template.get_default_values()

        # 创建结果列表
        results = [None] * len(abstracts)

        # 处理空摘要
        for i, abstract in enumerate(abstracts):
            if not abstract or not isinstance(abstract, str):
                results[i] = dict(default_values)

        # 使用ThreadPoolExecutor并行处理请求
        with concurrent.futures.ThreadPoolExecutor(max_workers=batch_size) as executor:
            # 创建future到摘要索引的映射
            future_to_index = {}
            # 提交任务到线程池
            for i, abstract in enumerate(abstracts):
                if not abstract or not isinstance(abstract, str):
                    continue

                future = executor.submit(self.generate_summary, abstract, prompt_type)
                future_to_index[future] = i

            # 收集结果并更新进度
            completed_count = 0
            total_tasks = len(future_to_index)
            
            for future in concurrent.futures.as_completed(future_to_index):
                index = future_to_index[future]
                try:
                    summary = future.result()
                    results[index] = summary
                except Exception as e:
                    logger.error(f"处理摘要 {index} 时出错: {str(e)}")
                    results[index] = dict(default_values)
                
                completed_count += 1
                # 调用进度回调
                if progress_callback:
                    progress_callback(completed_count, len(abstracts), 'ai_analysis')

        # 过滤掉None值，这些是我们已经在前面处理过的空摘要
        final_results = []
        for result in results:
            if result is not None:
                final_results.append(result)
            else:
                final_results.append(dict(default_values))

        return final_results


class SiliconFlowClient(BaseLLMClient):
    """
    硅基流动大模型客户端类，使用OpenAI兼容接口
    """

    def __init__(self, api_key: str, base_url: str = "https://api.siliconflow.cn/v1",
                 model: str = "deepseek-ai/DeepSeek-V3", max_retries: int = 5, timeout: int = 120,
                 temperature: float = 0.1, top_p: float = 1.0,
                 rpm: int = 3000, tpm: int = 200000, max_tokens: int = 4096):
        """
        初始化硅基流动客户端

        参数:
            api_key: API密钥
            base_url: API基础URL
            model: 模型名称
            max_retries: 最大重试次数
            timeout: 请求超时时间(秒)
            temperature: 温度参数，控制生成文本的随机性
            top_p: Top-p 采样参数
            rpm: 每分钟请求数限制 (当前实现中暂未使用)
            tpm: 每分钟令牌数限制 (当前实现中暂未使用)
            max_tokens: 控制生成的最大令牌数
        """
        try:
            # 禁用httpx日志输出
            logging.getLogger("httpx").setLevel(logging.WARNING)
            self.client = OpenAI(api_key=api_key, base_url=base_url, max_retries=0)
            self.model = model
            self.max_retries = max_retries
            self.timeout = timeout
            self.temperature = temperature
            self.top_p = top_p
            self.rpm = rpm
            self.tpm = tpm
            self.max_tokens = max_tokens
        except ImportError:
            logger.error("未安装OpenAI库，请使用 'pip install openai' 安装")
            raise

    def generate_summary(self, abstract: str, prompt_type: str = "medical") -> Dict[str, str]:
        """
        生成摘要理解

        参数:
            abstract: 文章摘要文本
            prompt_type: 提示词类型

        返回:
            包含提示词类型定义的字段的字典
        """
        if not abstract or not isinstance(abstract, str):
            # 获取默认值
            default_values = OutputConfig.get_default_values(prompt_type)
            return default_values

        # 使用提示词模板
        prompt_template = create_prompt_template(prompt_type)
        messages = prompt_template.get_messages(abstract=abstract)
        output_fields = prompt_template.get_output_fields()
        default_values = prompt_template.get_default_values()

        current_retry = 0
        while current_retry < self.max_retries:
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    top_p=self.top_p,
                    timeout=self.timeout
                )

                answer = response.choices[0].message.content.strip()
                return ResponseParser.parse_json_response(answer, output_fields, default_values)

            except RateLimitError as e:
                wait_time = 2 ** current_retry
                logger.warning(f"遭遇速率限制 (尝试 {current_retry + 1}/{self.max_retries})，等待 {wait_time} 秒后重试。错误: {str(e)}")
                time.sleep(wait_time)
                current_retry += 1
            except Exception as e:
                wait_time = 2 ** current_retry
                logger.error(f"使用硅基流动生成摘要时出错 (尝试 {current_retry + 1}/{self.max_retries})，等待 {wait_time} 秒后重试。错误: {str(e)}")
                time.sleep(wait_time)
                current_retry += 1

        logger.error(f"已达到最大重试次数 {self.max_retries}，无法生成摘要。")
        return default_values

    def batch_generate_summaries(self, abstracts: List[str],
                                 batch_size: int = 16, prompt_type: str = "medical",
                                 progress_callback: Optional[callable] = None) -> List[Dict[str, str]]:
        """
        批量生成摘要理解

        参数:
            abstracts: 文章摘要文本列表
            batch_size: 批处理大小，默认为 16
            prompt_type: 提示词类型

        返回:
            生成的摘要字典列表
        """
        # 获取默认值
        prompt_template = create_prompt_template(prompt_type)
        default_values = prompt_template.get_default_values()

        # 创建结果列表
        results = [None] * len(abstracts)

        # 处理空摘要
        for i, abstract in enumerate(abstracts):
            if not abstract or not isinstance(abstract, str):
                results[i] = dict(default_values)

        # 使用ThreadPoolExecutor并行处理请求
        with concurrent.futures.ThreadPoolExecutor(max_workers=batch_size) as executor:
            # 创建future到摘要索引的映射
            future_to_index = {}
            # 提交任务到线程池
            for i, abstract in enumerate(abstracts):
                if not abstract or not isinstance(abstract, str):
                    continue

                future = executor.submit(self.generate_summary, abstract, prompt_type)
                future_to_index[future] = i

            # 收集结果并更新进度
            completed_count = 0
            total_tasks = len(future_to_index)
            
            for future in concurrent.futures.as_completed(future_to_index):
                index = future_to_index[future]
                try:
                    summary = future.result()
                    results[index] = summary
                except Exception as e:
                    logger.error(f"处理摘要 {index} 时出错: {str(e)}")
                    results[index] = dict(default_values)
                
                completed_count += 1
                # 调用进度回调
                if progress_callback:
                    progress_callback(completed_count, len(abstracts), 'ai_analysis')

        # 过滤掉None值，这些是我们已经在前面处理过的空摘要
        final_results = []
        for result in results:
            if result is not None:
                final_results.append(result)
            else:
                final_results.append(dict(default_values))

        return final_results


class OllamaClient(BaseLLMClient):
    """
    Ollama客户端类，用于与Ollama API服务交互
    """

    def __init__(self, api_url: str = "http://localhost:11434/api",
                 model: str = "llama3", max_retries: int = 3, timeout: int = 120,
                 temperature: float = 0.7, top_p: float = 0.9, api_key: Optional[str] = None,
                 max_tokens: int = 4096):
        """
        初始化Ollama客户端

        参数:
            api_url: Ollama API服务的URL
            model: 使用的模型名称
            max_retries: 最大重试次数
            timeout: 请求超时时间(秒)
            temperature: 温度参数，控制生成文本的随机性
            top_p: Top-p 采样参数
            api_key: 可选的API密钥
            max_tokens: 控制生成的最大令牌数
        """
        self.api_url = api_url
        self.model = model
        self.max_retries = max_retries
        self.timeout = timeout
        self.temperature = temperature
        self.top_p = top_p
        self.api_key = api_key if api_key and api_key != "" else None
        self.max_tokens = max_tokens

    def _prepare_headers(self) -> Dict[str, str]:
        """准备请求头"""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def generate_summary(self, abstract: str, prompt_type: str = "medical") -> Dict[str, str]:
        """
        生成摘要理解

        参数:
            abstract: 文章摘要文本
            prompt_type: 提示词类型

        返回:
            包含提示词类型定义的字段的字典
        """
        if not abstract or not isinstance(abstract, str):
            # 获取默认值
            default_values = OutputConfig.get_default_values(prompt_type)
            return default_values

        # 使用提示词模板
        prompt_template = create_prompt_template(prompt_type)
        messages = prompt_template.get_messages(abstract=abstract)
        output_fields = prompt_template.get_output_fields()
        default_values = prompt_template.get_default_values()

        # 将messages格式转换为Ollama格式
        ollama_messages = [{"role": msg["role"], "content": msg["content"]} for msg in messages]

        # 构造请求数据
        payload = {
            "model": self.model,
            "messages": ollama_messages,
            "options": {
                "temperature": self.temperature,
                "top_p": self.top_p,
                "num_predict": self.max_tokens
            },
            "stream": False
        }

        # 发送请求并重试
        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    f"{self.api_url}/chat",
                    headers=self._prepare_headers(),
                    json=payload,
                    timeout=self.timeout
                )
                response.raise_for_status()
                result = response.json()

                if "message" in result and "content" in result["message"]:
                    answer = result["message"]["content"].strip()
                    return ResponseParser.parse_json_response(answer, output_fields, default_values)
                else:
                    logger.warning(f"无效的Ollama API响应: {result}")
                    return default_values

            except Exception as e:
                logger.error(f"使用Ollama生成摘要时出错 (尝试 {attempt + 1}/{self.max_retries}): {str(e)}")
                if attempt == self.max_retries - 1:
                    return default_values
                time.sleep(2 ** attempt)  # 指数退避

        return default_values

    def batch_generate_summaries(self, abstracts: List[str],
                                 batch_size: int = 5, prompt_type: str = "medical",
                                 progress_callback: Optional[callable] = None) -> List[Dict[str, str]]:
        """
        批量生成摘要理解

        参数:
            abstracts: 文章摘要文本列表
            batch_size: 批处理大小，默认为5
            prompt_type: 提示词类型

        返回:
            生成的摘要字典列表
        """
        # 获取默认值
        prompt_template = create_prompt_template(prompt_type)
        default_values = prompt_template.get_default_values()

        # 创建结果列表
        results = [None] * len(abstracts)

        # 处理空摘要
        for i, abstract in enumerate(abstracts):
            if not abstract or not isinstance(abstract, str):
                results[i] = dict(default_values)

        # 使用ThreadPoolExecutor并行处理请求
        with concurrent.futures.ThreadPoolExecutor(max_workers=batch_size) as executor:
            # 创建future到摘要索引的映射
            future_to_index = {}
            # 提交任务到线程池
            for i, abstract in enumerate(abstracts):
                if not abstract or not isinstance(abstract, str):
                    continue

                future = executor.submit(self.generate_summary, abstract, prompt_type)
                future_to_index[future] = i

            # 收集结果并更新进度
            completed_count = 0
            total_tasks = len(future_to_index)
            
            for future in concurrent.futures.as_completed(future_to_index):
                index = future_to_index[future]
                try:
                    summary = future.result()
                    results[index] = summary
                except Exception as e:
                    logger.error(f"处理摘要 {index} 时出错: {str(e)}")
                    results[index] = dict(default_values)
                
                completed_count += 1
                # 调用进度回调
                if progress_callback:
                    progress_callback(completed_count, len(abstracts), 'ai_analysis')

        # 过滤掉None值，这些是我们已经在前面处理过的空摘要
        final_results = []
        for result in results:
            if result is not None:
                final_results.append(result)
            else:
                final_results.append(dict(default_values))

        return final_results


class CustomPromptClient(BaseLLMClient):
    """
    自定义提示词客户端，允许用户提供自定义提示词模板
    """

    def __init__(self, client: BaseLLMClient, prompt_template: PromptTemplate):
        """
        初始化自定义提示词客户端

        参数:
            client: 基础LLM客户端实例
            prompt_template: 自定义提示词模板
        """
        self.client = client
        self.prompt_template = prompt_template

    def generate_summary(self, abstract: str, prompt_type: str = None) -> Dict[str, str]:
        """使用自定义提示词生成摘要"""
        # 忽略prompt_type参数，使用传入的提示词模板
        return self.client.generate_summary(abstract, self.prompt_template.prompt_type or prompt_type)

    def batch_generate_summaries(self, abstracts: List[str],
                                 batch_size: int = 5, prompt_type: str = None) -> List[Dict[str, str]]:
        """批量使用自定义提示词生成摘要"""
        return self.client.batch_generate_summaries(abstracts, batch_size,
                                                    self.prompt_template.prompt_type or prompt_type)


def create_llm_client(model_type: str, **kwargs) -> BaseLLMClient:
    """
    创建LLM客户端工厂函数

    参数:
        model_type: 模型类型 ("vllm", "siliconflow" 或 "ollama")
        **kwargs: 传递给客户端构造函数的额外参数

    返回:
        LLM客户端实例
    """
    # 提取prompt_template参数，如果存在
    prompt_template = kwargs.pop('prompt_template', None)

    # 从 kwargs 中提取模型参数，如果不存在则使用默认值
    kwargs.setdefault('temperature', 0.7)
    kwargs.setdefault('top_p', 0.9)
    kwargs.setdefault('max_tokens', 4096)

    # 创建基础客户端
    if model_type.lower() == "vllm":
        client = VllmClient(**kwargs)
    elif model_type.lower() == "siliconflow":
        if 'rpm' not in kwargs or 'tpm' not in kwargs:
            try:
                from ..config.config_manager import load_config
                config = load_config()
                llm_config = config.get("llm", {})
                kwargs.setdefault('rpm', llm_config.get('siliconflow_rpm', 3000))
                kwargs.setdefault('tpm', llm_config.get('siliconflow_tpm', 200000))
            except Exception:
                kwargs.setdefault('rpm', 3000)
                kwargs.setdefault('tpm', 200000)
                logger.warning("无法从配置中加载 RPM/TPM，使用默认值。")
        client = SiliconFlowClient(**kwargs)
    elif model_type.lower() == "ollama":
        client = OllamaClient(**kwargs)
    else:
        raise ValueError(f"不支持的模型类型: {model_type}，支持的类型为 'vllm'、'siliconflow' 和 'ollama'")

    # 如果提供了自定义提示词模板，创建自定义提示词客户端
    if prompt_template is not None:
        return CustomPromptClient(client, prompt_template)

    return client