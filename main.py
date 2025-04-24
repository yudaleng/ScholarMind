import sys
import argparse
import pandas as pd
import logging
import numpy as np
from tqdm import tqdm
from typing import Dict

from src.config.config_manager import load_config
from src.api.journal_metrics import get_journal_metrics
from src.api.llm_api import create_llm_client
from src.api.prompt_templates import load_yaml_templates, OutputConfig
from src.parsers.parsers_manager import ParsersManager
from src.utils.excel_formatter import ExcelFormatter

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class CombinedProcessor:
    """处理多数据源的组合处理器"""
    
    def __init__(self, config: Dict, llm_client=None, get_journal_metrics_func=None):
        """初始化处理器"""
        self.config = config
        self.llm_client = llm_client
        self.get_journal_metrics_func = get_journal_metrics_func # 指标函数可能为 None
        
        # 从配置中获取控制标志
        self.journal_metrics_enabled = self.config.get("journal_metrics", {}).get("enabled", True)
        self.llm_enabled = self.config.get("llm", {}).get("enabled", True)
        
        # 仅在启用时获取相关配置
        if self.journal_metrics_enabled:
            metrics_config = self.config.get("journal_metrics", {})
            self.metrics_to_fetch = metrics_config.get("metrics_to_fetch", [])
            self.metrics_column_mapping = metrics_config.get("metrics_column_mapping", {})
        else:
            self.metrics_to_fetch = []
            self.metrics_column_mapping = {}
            self.get_journal_metrics_func = None
            
        if not self.llm_enabled:
            self.llm_client = None

        self.prompt_type = self.config.get("prompt", {}).get("default_type", "medical")
        self.batch_size = self.config.get("processing", {}).get("batch_size", 16)
        self.max_workers = self.config.get("processing", {}).get("max_workers", 4)
        self.ai_fields = OutputConfig.get_fields(self.prompt_type)

    def process_data(self, input_df: pd.DataFrame) -> pd.DataFrame:
        """处理来自多个数据源的合并数据"""
        df = input_df.copy()
        
        # 检测并处理数据重合的情况，优先使用WOS数据
        if 'source_type' in df.columns:
            logger.info("检测WOS、PUBMED和ScienceDirect数据重合情况...")
            
            # 重合判断前的记录总数
            total_before = len(df)
            
            # 1. 标准化doi字段，确保比较准确
            if 'doi' in df.columns:
                # 将列表类型转换为字符串
                df['doi'] = df['doi'].apply(
                    lambda x: x[0] if isinstance(x, list) and len(x) > 0 else 
                            (', '.join(x) if isinstance(x, list) else x)
                )
                
                # 移除PubMed特有的"[doi]"后缀和所有空格
                df['doi'] = df['doi'].apply(
                    lambda x: x.replace(" [doi]", "").strip().lower() if isinstance(x, str) else x
                )
                
                # 处理特殊格式的DOI
                def clean_doi(doi_str):
                    if not isinstance(doi_str, str) or pd.isna(doi_str):
                        return doi_str
                    
                    # 移除[doi]和[pii]标记
                    doi_str = doi_str.replace(" [doi]", "").replace(" [pii]", "")
                    
                    # 处理包含逗号的DOI，提取10.xxxx/开头的部分
                    if "," in doi_str:
                        parts = [part.strip() for part in doi_str.split(",")]
                        # 尝试找出有效的DOI部分（通常以10.开头）
                        valid_doi = None
                        for part in parts:
                            if part.startswith("10."):
                                valid_doi = part
                                break
                        return valid_doi if valid_doi else doi_str
                    
                    return doi_str.strip().lower()
                
                df['doi'] = df['doi'].apply(clean_doi)
                
            # 2. 创建标识数据重合的列
            df['is_duplicate'] = False
            
            # 3. 只根据doi判断重复记录
            if 'doi' in df.columns:
                # 过滤掉空的doi
                valid_doi_df = df[df['doi'].notna() & (df['doi'] != "")]
                
                # 用于存储已处理过的doi
                processed_dois = set()
                
                # 设置数据源优先级: wos > pubmed > sciencedirect
                source_priority = {'wos': 3, 'pubmed': 2, 'sciencedirect': 1}
                df['source_priority'] = df['source_type'].map(lambda x: source_priority.get(x, 0))
                df = df.sort_values(by='source_priority', ascending=False)
                
                for idx, row in df.iterrows():
                    doi = row['doi']
                    
                    # 如果doi不为空，则判断是否重复
                    if doi and pd.notna(doi) and doi != "":
                        # 标准化doi格式
                        if isinstance(doi, str):
                            # 移除[pii]标记
                            doi = doi.replace(" [pii]", "")
                            
                            # 处理包含逗号的DOI
                            if "," in doi:
                                parts = [p.strip() for p in doi.split(",")]
                                # 尝试找出有效的DOI部分（通常以10.开头）
                                valid_doi = None
                                for part in parts:
                                    if part.startswith("10."):
                                        valid_doi = part
                                        break
                                if valid_doi:
                                    doi = valid_doi
                            
                            # 移除可能的前缀
                            if doi.startswith("https://doi.org/"):
                                doi = doi[16:]
                            elif doi.startswith("doi:"):
                                doi = doi[4:]
                            doi = doi.strip().lower()
                        
                        if doi in processed_dois:
                            # 如果这个doi已经处理过，说明它是重复的
                            df.loc[idx, 'is_duplicate'] = True
                        else:
                            # 第一次遇到这个doi，添加到集合中
                            processed_dois.add(doi)
            
            # 4. 排除重复数据
            df = df[~df['is_duplicate']]
            # 删除临时列
            df = df.drop(['is_duplicate', 'source_priority'], axis=1)
            
            # 重合判断后的记录总数
            total_after = len(df)
            
            # 输出处理结果
            duplicates_removed = total_before - total_after
            if duplicates_removed > 0:
                logger.info(f"检测到 {duplicates_removed} 条重复记录，已按优先级保留数据")
            else:
                logger.info("未检测到重复记录")
        
        # 添加期刊指标
        if self.journal_metrics_enabled:
            df = self.add_journal_metrics(df)
            logger.info(f"期刊指标添加完成，共处理 {len(df)} 条记录")
        else:
            logger.info("期刊指标获取功能已禁用，跳过添加指标。")

        # 根据数据源类型生成链接
        if 'source_type' in df.columns:
            # 处理PubMed链接 - 检查pmid列是否存在
            if 'pmid' in df.columns:
                pubmed_mask = (df['source_type'] == 'pubmed') & df['pmid'].notna()
                if pubmed_mask.any():
                    df.loc[pubmed_mask, 'pubmed_link'] = df.loc[pubmed_mask, 'pmid'].apply(
                        lambda pmid: f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
                    )
            
            # 处理WOS链接 - 检查wos_id列是否存在
            if 'wos_id' in df.columns:
                wos_mask = (df['source_type'] == 'wos') & df['wos_id'].notna()
                if wos_mask.any():
                    df.loc[wos_mask, 'wos_link'] = df.loc[wos_mask, 'wos_id'].apply(
                        lambda wos_id: f"https://www.webofscience.com/wos/woscc/full-record/{wos_id}"
                    )
            
            # 处理ScienceDirect链接 - 检查url列是否存在
            if 'url' in df.columns:
                sciencedirect_mask = (df['source_type'] == 'sciencedirect') & df['url'].notna()
                if sciencedirect_mask.any():
                    df.loc[sciencedirect_mask, 'sciencedirect_link'] = df.loc[sciencedirect_mask, 'url']
        
        # 处理DOI链接
        if 'doi' in df.columns:
            try:
                def safe_doi_link(doi):
                    # 处理None或NaN
                    if doi is None:
                        return ""
                        
                    try:
                        if pd.isna(doi):
                            return ""
                    except (TypeError, ValueError):
                        pass
                    
                    # 定义DOI清洗函数
                    def clean_doi_format(d):
                        if not isinstance(d, str) or not d:
                            return d
                        
                        # 移除[doi]和[pii]标记
                        d = d.replace(" [doi]", "").replace(" [pii]", "")
                        
                        # 处理包含逗号的DOI
                        if "," in d:
                            parts = [p.strip() for p in d.split(",")]
                            # 尝试找出有效的DOI部分（通常以10.开头）
                            for part in parts:
                                if part.startswith("10."):
                                    d = part
                                    break
                        
                        # 移除可能的前缀
                        if d.startswith("https://doi.org/"):
                            d = d[16:]
                        elif d.startswith("doi:"):
                            d = d[4:]
                            
                        return d.strip()
                    
                    # 处理列表
                    if isinstance(doi, list):
                        # 如果是列表，使用第一个非空值
                        for d in doi:
                            try:
                                if d and not pd.isna(d):
                                    clean_d = clean_doi_format(d)
                                    if clean_d:
                                        return f"https://doi.org/{clean_d}"
                            except (TypeError, ValueError):
                                pass
                        return ""
                    
                    # 处理NumPy数组
                    if isinstance(doi, np.ndarray):
                        # 如果是NumPy数组，转换为列表处理
                        if doi.size > 0:
                            for d in doi:
                                try:
                                    if d and not pd.isna(d):
                                        clean_d = clean_doi_format(d)
                                        if clean_d:
                                            return f"https://doi.org/{clean_d}"
                                except (TypeError, ValueError):
                                    continue
                        return ""
                    
                    # 处理单个值
                    if doi and not pd.isna(doi):
                        clean_doi = clean_doi_format(doi)
                        if clean_doi:
                            return f"https://doi.org/{clean_doi}"
                    
                    return ""
                
                df['doi_link'] = df['doi'].apply(safe_doi_link)
                logger.info("成功创建DOI链接")
            except Exception as e:
                logger.error(f"创建DOI链接时出错: {str(e)}")
                df['doi_link'] = ""
        
        # 处理title超链接，根据不同来源使用不同的链接
        if 'title' in df.columns:
            # 初始化title_link列
            df['title_link'] = ""
            
            # WOS数据优先使用WOS链接
            if 'wos_link' in df.columns:
                wos_mask = df['wos_link'].notna() & (df['title_link'] == "")
                if wos_mask.any():
                    df.loc[wos_mask, 'title_link'] = df.loc[wos_mask, 'wos_link']
            
            # PubMed数据优先使用PubMed链接
            if 'pubmed_link' in df.columns:
                pubmed_mask = df['pubmed_link'].notna() & (df['title_link'] == "")
                if pubmed_mask.any():
                    df.loc[pubmed_mask, 'title_link'] = df.loc[pubmed_mask, 'pubmed_link']
            
            # ScienceDirect数据优先使用ScienceDirect链接
            if 'sciencedirect_link' in df.columns:
                sd_mask = df['sciencedirect_link'].notna() & (df['title_link'] == "")
                if sd_mask.any():
                    df.loc[sd_mask, 'title_link'] = df.loc[sd_mask, 'sciencedirect_link']
            
            # 如果上述都没有，则使用DOI链接
            if 'doi_link' in df.columns:
                doi_mask = df['doi_link'].notna() & (df['title_link'] == "")
                if doi_mask.any():
                    df.loc[doi_mask, 'title_link'] = df.loc[doi_mask, 'doi_link']
        
        # 添加AI生成的相关内容 (如果启用且有LLM客户端)
        if self.llm_enabled and self.llm_client and ('abstract' in df.columns):
            logger.info("开始使用AI进行摘要理解...")
            
            # 提取摘要
            abstracts = []
            for idx, row in df.iterrows():
                abstracts.append(str(row.get('abstract', '')))
            
            # 获取AI生成的JSON结果
            ai_results = self.llm_client.batch_generate_summaries(
                abstracts, 
                batch_size=self.max_workers, # 使用 max_workers 作为并发数
                prompt_type=self.prompt_type
            )
            
            # 创建新的空列
            if self.ai_fields:
                for field in self.ai_fields:
                    if field not in df.columns:
                        df[field] = ""
            
                for i, result in enumerate(ai_results):
                    if i < len(df):
                        for field, value in result.items():
                            if field in self.ai_fields:
                                df.iloc[i, df.columns.get_loc(field)] = value
            
                logger.info(f"摘要理解生成完成，共处理 {len(abstracts)} 条摘要")
            else:
                logger.warning("未配置AI生成字段（或提示词模板未定义字段），跳过AI摘要理解结果填充")
        elif not self.llm_enabled:
             logger.info("LLM 摘要理解功能已禁用，跳过处理。")
        elif not self.llm_client:
             logger.warning("LLM 客户端未成功初始化，跳过AI摘要理解功能。")
        elif 'abstract' not in df.columns:
             logger.warning("数据中缺少 'abstract' 列，跳过AI摘要理解功能。")
        # 如果禁用了LLM或者没有客户端/摘要，确保AI字段存在（如果定义了）但为空
        elif self.ai_fields:
             for field in self.ai_fields:
                 if field not in df.columns:
                     df[field] = ""

        return df
    
    def add_journal_metrics(self, df: pd.DataFrame) -> pd.DataFrame:
        """添加期刊指标"""
        # 再次检查是否启用，以及是否有获取函数
        if not self.journal_metrics_enabled or not self.get_journal_metrics_func:
            logger.info("期刊指标获取功能已禁用或未配置获取函数，跳过。")
             # 确保列存在，即使是空的
            for metric in self.metrics_to_fetch:
                column_name = self.metrics_column_mapping.get(metric, metric)
                if column_name not in df.columns:
                     df[column_name] = ""
            return df
        
        try:
            # 提取唯一的期刊名
            journals = set()
            if 'journal' in df.columns:
                # 排除空值
                journals.update([j for j in df['journal'].unique() if pd.notna(j) and j])
                
                # 标准化期刊名，用于后续映射
                df['journal_normalized'] = df['journal'].apply(
                    lambda j: str(j).strip().lower() if pd.notna(j) else ""
                )
            else:
                logger.warning("数据中缺少journal列，跳过期刊指标添加")
                # 确保列存在
                for metric in self.metrics_to_fetch:
                    column_name = self.metrics_column_mapping.get(metric, metric)
                    if column_name not in df.columns:
                        df[column_name] = ""
                return df
            
            logger.info(f"开始获取 {len(journals)} 种期刊的指标...")
            
            # 批量获取期刊指标
            metrics_dict = {}
            for journal in tqdm(journals, desc="获取期刊指标"):
                if not journal:
                    continue
                    
                # 获取该期刊的所有配置指标
                journal_metrics = self.get_journal_metrics_func(
                    journal_name=journal,
                    metrics_to_fetch=self.metrics_to_fetch,
                    metrics_column_mapping=self.metrics_column_mapping # 传递映射以正确解析结果
                )
                
                if journal_metrics:
                    # 使用标准化的期刊名作为键
                    metrics_dict[journal.strip().lower()] = journal_metrics
            
            # 为每个指标创建列 (使用映射后的列名)
            for metric_key in self.metrics_to_fetch:
                column_name = self.metrics_column_mapping.get(metric_key, metric_key)
                if column_name not in df.columns:
                    df[column_name] = ""
                
                # 根据标准化的期刊名映射添加指标列
                df[column_name] = df['journal_normalized'].map(
                    lambda j_norm: metrics_dict.get(j_norm, {}).get(column_name, '') # 使用映射后的列名查找
                    if isinstance(j_norm, str) else ''
                )
            
            # 删除临时列
            if 'journal_normalized' in df.columns:
                df = df.drop('journal_normalized', axis=1)
            
            logger.info(f"期刊指标获取完成，共处理 {len(journals)} 种期刊")
        except Exception as e:
            logger.error(f"获取期刊指标时出错: {str(e)}")
            # 创建所有配置的指标列，确保它们存在
            for metric in self.metrics_to_fetch:
                column_name = self.metrics_column_mapping.get(metric, metric)
                if column_name not in df.columns:
                    df[column_name] = ""
        
        return df

def main():
    """处理多数据源并合并输出的主程序入口"""
    parser = argparse.ArgumentParser(description='处理多个数据源并合并结果到一个Excel文件')
    parser.add_argument('--config', help='配置文件路径，默认使用config/config.yaml')
    
    args = parser.parse_args()
    
    # 加载配置
    config = load_config(args.config)
    
    # 获取数据源配置
    sources = config.get("sources", [])
    if not sources:
        logger.error("未找到可用的数据源配置，请检查config.yaml文件")
        sys.exit(1)
    
    # 获取输出配置
    output_config = config.get("output", {})
    output_excel_path = output_config.get("excel_path", "data/combined-output.xlsx")
    
    # 加载YAML提示词模板
    templates_dir = config.get("prompt", {}).get("templates_dir", "config/prompts")
    _, available_types = load_yaml_templates(templates_dir)
    
    if not available_types:
        logger.error(f"未找到可用的提示词模板，请检查目录 {templates_dir}")
        sys.exit(1)
    
    # 从配置文件获取提示词类型
    prompt_type = config.get("prompt", {}).get("default_type")
    
    # 确保提示词类型是可用的
    if not prompt_type or prompt_type not in available_types:
        prompt_type = available_types[0]
        logger.warning(f"未指定有效的提示词类型，使用: {prompt_type}")
    
    logger.info(f"当前使用的提示词类型: {prompt_type}")
    
    # 获取处理参数
    processing_config = config.get("processing", {})
    batch_size = processing_config.get("batch_size", 16)
    max_workers = processing_config.get("max_workers", 4)
    
    logger.info(f"批处理大小: {batch_size}, 最大线程数: {max_workers}")
    
    # 获取功能启用标志
    llm_enabled = config.get("llm", {}).get("enabled", True)
    journal_metrics_enabled = config.get("journal_metrics", {}).get("enabled", True)
    
    # 初始化LLM客户端（如果启用）
    llm_client = None
    if llm_enabled:
        try:
            llm_config = config.get("llm", {})
            llm_type = llm_config.get("type", "vllm")
            model_params = llm_config.get("model_parameters", {})
            temperature = model_params.get("temperature", 0.7)
            top_p = model_params.get("top_p", 0.9)
            max_tokens = model_params.get("max_tokens", 4096)
            
            if llm_type == "vllm":
                client_kwargs = {
                    "api_url": llm_config["vllm_api_url"],
                    "api_key": llm_config["vllm_api_key"],
                    "model": llm_config.get("vllm_model", "qwen"),
                    "temperature": temperature,
                    "top_p": top_p,
                    "max_tokens": max_tokens
                }
                llm_client = create_llm_client("vllm", **client_kwargs)
                logger.info(f"使用本地VLLM模型: {client_kwargs['model']}")
            elif llm_type == "siliconflow":
                client_kwargs = {
                    "api_key": llm_config["siliconflow_api_key"],
                    "base_url": llm_config["siliconflow_base_url"],
                    "model": llm_config["siliconflow_model"],
                    "temperature": temperature,
                    "top_p": top_p,
                    "rpm": llm_config["siliconflow_rpm"],
                    "tpm": llm_config["siliconflow_tpm"],
                    "max_tokens": max_tokens
                }
                llm_client = create_llm_client("siliconflow", **client_kwargs)
                logger.info(f"使用硅基流动大模型: {client_kwargs['model']}")
            elif llm_type == "ollama":
                client_kwargs = {
                    "api_url": llm_config.get("ollama_api_url", "http://localhost:11434/api"),
                    "model": llm_config.get("ollama_model", "llama3"),
                    "temperature": temperature,
                    "top_p": top_p,
                    "api_key": llm_config.get("ollama_api_key", ""),
                    "max_tokens": max_tokens
                }
                llm_client = create_llm_client("ollama", **client_kwargs)
                logger.info(f"使用Ollama模型: {client_kwargs['model']}")
            else:
                raise ValueError(f"不支持的LLM类型: {llm_type}")
        except KeyError as e:
            logger.error(f"初始化LLM客户端失败，缺少配置项: {e}。摘要理解功能将被禁用。")
            llm_client = None
        except Exception as e:
            logger.warning(f"初始化LLM客户端失败: {str(e)}。摘要理解功能将被禁用。")
            llm_client = None # 确保客户端为 None
    else:
        logger.info("LLM 摘要理解功能已在配置中禁用。")
        
    # 决定是否使用期刊指标函数
    journal_metrics_func = get_journal_metrics if journal_metrics_enabled else None
    if not journal_metrics_enabled:
         logger.info("期刊指标获取功能已在配置中禁用。")
         if config.get("easyscholar_api_key") == "*" or not config.get("easyscholar_api_key"):
             logger.warning("未配置 easyscholar_api_key，即使启用也无法获取期刊指标。")
    
    # 创建解析器管理器，解析和预处理所有数据源
    parsers_manager = ParsersManager(sources)
    
    # 解析所有数据源，获取处理后的合并数据
    combined_df = parsers_manager.parse_all_sources()
    
    if combined_df.empty:
        logger.error("未能从任何数据源中解析到有效数据")
        sys.exit(1)
    
    logger.info(f"成功解析 {len(combined_df)} 条记录")

    # 获取当前提示词模板定义的字段
    ai_fields = OutputConfig.get_fields(prompt_type)
    
    # 创建组合处理器，进行合并后的数据处理
    combined_processor = CombinedProcessor(
        config=config,
        llm_client=llm_client,
        get_journal_metrics_func=journal_metrics_func
    )
    
    # 处理合并数据
    processed_df = combined_processor.process_data(combined_df)
    
    # 使用ExcelFormatter格式化并保存
    formatter = ExcelFormatter()
    success = formatter.format_excel(
        processed_df,
        output_excel_path,
        separate_sheets=output_config.get("separate_sheets", True),
        ai_fields=ai_fields
    )
    
    if success:
        logger.info(f"多数据源处理完成，结果已保存到: {output_excel_path}")
    else:
        logger.error("保存结果失败")
        sys.exit(1)

if __name__ == "__main__":
    main()
