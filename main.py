import sys
import argparse
import pandas as pd
import logging
import numpy as np
from tqdm import tqdm

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
    
    def __init__(self, llm_client=None, get_journal_metrics_func=None, prompt_type="medical", 
                batch_size=16, max_workers=4, ai_fields=None):
        """初始化处理器"""
        self.llm_client = llm_client
        self.get_journal_metrics_func = get_journal_metrics_func
        self.prompt_type = prompt_type
        self.batch_size = batch_size
        self.max_workers = max_workers
        self.ai_fields = ai_fields
        
        # 从配置文件获取期刊指标配置
        config = load_config()
        metrics_config = config.get("journal_metrics", {})
        self.metrics_to_fetch = metrics_config.get("metrics_to_fetch", ["sciif", "sci"])
        self.metrics_column_mapping = metrics_config.get("metrics_column_mapping", {})
    
    def process_data(self, input_df: pd.DataFrame) -> pd.DataFrame:
        """处理来自多个数据源的合并数据"""
        df = input_df.copy()
        
        # 检测并处理数据重合的情况，优先使用WOS数据
        if 'source_type' in df.columns:
            logger.info("检测WOS、PUBMED和ScienceDirect数据重合情况...")
            
            # 重合判断前的记录总数
            total_before = len(df)
            
            # 1. 先标准化title和doi字段，确保比较准确
            for col in ['title', 'doi']:
                if col in df.columns:
                    # 将列表类型转换为字符串
                    df[col] = df[col].apply(
                        lambda x: x[0] if isinstance(x, list) and len(x) > 0 else 
                                (', '.join(x) if isinstance(x, list) else x)
                    )
                    
                    # 对于doi字段，移除PubMed特有的"[doi]"后缀
                    if col == 'doi':
                        df[col] = df[col].apply(
                            lambda x: x.replace(" [doi]", "").strip() if isinstance(x, str) else x
                        )
                    
                    # 标准化：去除空格、转换为小写
                    df[col] = df[col].apply(
                        lambda x: str(x).strip().lower() if pd.notna(x) else ""
                    )
            
            # 2. 创建标识数据重合的列
            df['is_duplicate'] = False
            
            # 3. 找出title和doi相同的记录
            if 'title' in df.columns and 'doi' in df.columns:
                # 用于存储已处理过的(title, doi)组合
                processed_pairs = set()
                
                # 设置数据源优先级: wos > pubmed > sciencedirect
                # 按source_type排序，确保WOS最优先
                source_priority = {'wos': 3, 'pubmed': 2, 'sciencedirect': 1}
                df['source_priority'] = df['source_type'].map(lambda x: source_priority.get(x, 0))
                df = df.sort_values(by='source_priority', ascending=False)
                
                for idx, row in df.iterrows():
                    title = row['title']
                    doi = row['doi']
                    source_type = row['source_type']
                    
                    # 如果title和doi都不为空，则判断是否重复
                    if title and doi:
                        pair = (title, doi)
                        
                        if pair in processed_pairs:
                            # 如果这个组合已经处理过，说明它是重复的
                            df.loc[idx, 'is_duplicate'] = True
                        else:
                            # 第一次遇到这个组合，添加到集合中
                            processed_pairs.add(pair)
            
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
        df = self.add_journal_metrics(df)
        
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
                    
                    # 移除可能存在的[doi]后缀
                    if isinstance(doi, str) and " [doi]" in doi:
                        doi = doi.replace(" [doi]", "").strip()
                    
                    # 处理列表
                    if isinstance(doi, list):
                        # 如果是列表，使用第一个非空值
                        for d in doi:
                            try:
                                if d and not pd.isna(d):
                                    # 处理字符串中的[doi]后缀
                                    if isinstance(d, str) and " [doi]" in d:
                                        d = d.replace(" [doi]", "").strip()
                                    return f"https://doi.org/{d}"
                            except (TypeError, ValueError):
                                if d:
                                    # 处理字符串中的[doi]后缀
                                    if isinstance(d, str) and " [doi]" in d:
                                        d = d.replace(" [doi]", "").strip()
                                    return f"https://doi.org/{d}"
                        return ""
                    
                    # 处理NumPy数组
                    if isinstance(doi, np.ndarray):
                        # 如果是NumPy数组，转换为列表处理
                        if doi.size > 0:
                            for d in doi:
                                try:
                                    if d and not pd.isna(d):
                                        # 处理字符串中的[doi]后缀
                                        if isinstance(d, str) and " [doi]" in d:
                                            d = d.replace(" [doi]", "").strip()
                                        return f"https://doi.org/{d}"
                                except (TypeError, ValueError):
                                    continue
                        return ""
                    
                    # 处理单个值
                    if doi and not pd.isna(doi):
                        return f"https://doi.org/{doi}"
                    else:
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
        
        # 添加AI生成的相关内容
        if not self.llm_client or ('abstract' not in df.columns):
            # 如果没有LLM客户端或没有摘要，跳过摘要理解功能
            logger.warning("跳过摘要理解功能: " + 
                          ("未配置LLM客户端" if not self.llm_client else "缺少abstract字段"))
            # 添加空的摘要理解列
            df['summary'] = ""
        else:
            logger.info("开始使用AI进行摘要理解...")
            
            # 提取摘要
            abstracts = []
            for idx, row in df.iterrows():
                abstracts.append(str(row.get('abstract', '')))
            
            # 获取AI生成的JSON结果
            ai_results = self.llm_client.batch_generate_summaries(
                abstracts, 
                batch_size=self.batch_size,
                prompt_type=self.prompt_type
            )
            
            # 创建新的空列
            if self.ai_fields is not None:
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
                logger.warning("未配置AI生成字段，跳过摘要理解功能")
        
        return df
    
    def add_journal_metrics(self, df: pd.DataFrame) -> pd.DataFrame:
        """添加期刊指标"""
        if not self.get_journal_metrics_func:
            logger.warning("未配置期刊指标获取函数，跳过期刊指标添加")
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
                    metrics_column_mapping=self.metrics_column_mapping
                )
                
                if journal_metrics:
                    metrics_dict[journal.lower()] = {}
                    
                    # 重命名指标列
                    for metric_key, metric_value in journal_metrics.items():
                        column_name = self.metrics_column_mapping.get(metric_key, metric_key)
                        metrics_dict[journal.lower()][column_name] = metric_value
            
            # 为每个指标创建列
            for metric in self.metrics_to_fetch:
                column_name = self.metrics_column_mapping.get(metric, metric)
                
                # 根据期刊名映射添加指标列
                df[column_name] = df['journal_normalized'].map(
                    lambda j: metrics_dict.get(j, {}).get(column_name, '')
                    if isinstance(j, str) else ''
                )
            
            # 删除临时列
            if 'journal_normalized' in df.columns:
                df = df.drop('journal_normalized', axis=1)
            
            logger.info(f"期刊指标获取完成，共处理 {len(journals)} 种期刊")
        except Exception as e:
            logger.error(f"获取期刊指标时出错: {str(e)}")
            # 创建所有配置的指标列
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
    
    # 从配置文件获取处理参数
    disable_summary = config.get("processing", {}).get("disable_summary", False)
    batch_size = config.get("processing", {}).get("batch_size", 16)
    max_workers = config.get("processing", {}).get("max_workers", 4)
    
    logger.info(f"批处理大小: {batch_size}, 最大线程数: {max_workers}")
    
    # 初始化LLM客户端（如果启用摘要理解功能）
    llm_client = None
    if not disable_summary:
        try:
            # 从配置文件获取LLM类型
            llm_type = config.get("llm", {}).get("type", "vllm")
            # 获取模型参数
            model_params = config.get("llm", {}).get("model_parameters", {})
            temperature = model_params.get("temperature", 0.7)
            top_p = model_params.get("top_p", 0.9)
            
            if llm_type == "vllm":
                llm_client = create_llm_client(
                    "vllm",
                    api_url=config["llm"]["vllm_api_url"],
                    api_key=config["llm"]["vllm_api_key"],
                    model=config["llm"].get("vllm_model", "qwen"),
                    temperature=temperature,
                    top_p=top_p
                )
                logger.info(f"使用本地VLLM模型: {config['llm'].get('vllm_model', 'qwen')}")
            elif llm_type == "siliconflow":
                llm_client = create_llm_client(
                    "siliconflow",
                    api_key=config["llm"]["siliconflow_api_key"],
                    base_url=config["llm"]["siliconflow_base_url"],
                    model=config["llm"]["siliconflow_model"],
                    temperature=temperature,
                    top_p=top_p
                )
                logger.info(f"使用硅基流动大模型: {config['llm']['siliconflow_model']}")
            elif llm_type == "ollama":
                llm_client = create_llm_client(
                    "ollama",
                    api_url=config["llm"].get("ollama_api_url", "http://localhost:11434/api"),
                    model=config["llm"].get("ollama_model", "llama3"),
                    temperature=temperature,
                    top_p=top_p,
                    api_key=config["llm"].get("ollama_api_key", "")
                )
                logger.info(f"使用Ollama模型: {config['llm'].get('ollama_model', 'llama3')}")
            else:
                raise ValueError(f"不支持的LLM类型: {llm_type}")
        except Exception as e:
            logger.warning(f"初始化LLM客户端失败，摘要理解功能将被禁用: {str(e)}")
    
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
        llm_client=llm_client,
        get_journal_metrics_func=get_journal_metrics,
        prompt_type=prompt_type,
        batch_size=batch_size,
        max_workers=max_workers,
        ai_fields=ai_fields
    )
    
    # 处理合并数据
    processed_df = combined_processor.process_data(combined_df)
    
    # 使用ExcelFormatter格式化并保存
    formatter = ExcelFormatter()
    success = formatter.format_excel(processed_df, output_excel_path, separate_sheets=output_config.get("separate_sheets", True), ai_fields=ai_fields)
    
    if success:
        logger.info(f"多数据源处理完成，结果已保存到: {output_excel_path}")
    else:
        logger.error("保存结果失败")
        sys.exit(1)

if __name__ == "__main__":
    main()
