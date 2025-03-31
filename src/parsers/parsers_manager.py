from typing import List, Dict, Any
import pandas as pd
import logging
import re
from src.parsers import BaseParser, PubmedParser, WosParser, ScienceDirectParser

logger = logging.getLogger(__name__)

class ParsersManager:
    """
    解析器管理器，负责根据配置解析并预处理多个数据源的数据
    该类替代了原有的SourceManager，不再依赖processors
    """
    
    def __init__(self, sources_config: List[Dict[str, Any]]):
        """
        初始化解析器管理器
        
        参数:
            sources_config: 数据源配置列表，每个数据源包含type和path属性
        """
        self.sources_config = sources_config
        self._parsers = {}  # 缓存创建的解析器实例
    
    def parse_all_sources(self) -> pd.DataFrame:
        """解析所有启用的数据源并合并结果"""
        combined_data = []
        
        for source in self.sources_config:
            if not source.get('enabled', True):
                logger.info(f"跳过禁用的数据源: {source.get('type')} - {source.get('path')}")
                continue
                
            source_type = source.get('type')
            source_path = source.get('path')
            
            if not source_type or not source_path:
                logger.warning(f"数据源配置缺少type或path: {source}")
                continue
                
            logger.info(f"开始解析数据源: {source_type} - {source_path}")
            
            try:
                # 获取或创建解析器
                parser = self._get_parser(source)
                
                # 解析数据源文件
                raw_data = parser.parse_file(source_path)
                
                # 标准化列名和数据格式
                data_df = parser.standardize_columns(raw_data)
                
                # 预处理数据（提取年份、处理作者列表等）
                data_df = self._preprocess_data(data_df, source_type)
                
                # 添加数据源类型标记
                data_df['source_type'] = source_type
                
                if not data_df.empty:
                    combined_data.append(data_df)
                    logger.info(f"成功解析 {len(data_df)} 条 {source_type} 数据")
                else:
                    logger.warning(f"数据源 {source_type} 解析结果为空")
            except Exception as e:
                logger.error(f"解析数据源 {source_type} 时出错: {str(e)}")
        
        # 合并所有解析后的数据
        if combined_data:
            return pd.concat(combined_data, ignore_index=True)
        else:
            logger.warning("所有数据源解析结果均为空")
            return pd.DataFrame()
    
    def _get_parser(self, source: Dict[str, Any]) -> BaseParser:
        """根据数据源类型获取或创建对应的解析器"""
        source_type = source.get('type')
        
        # 如果已经创建过此类型的解析器，则直接返回
        if source_type in self._parsers:
            return self._parsers[source_type]
        
        # 创建新的解析器实例
        if source_type.lower() == "wos":
            parser = WosParser()
        elif source_type == 'pubmed':
            parser = PubmedParser()
        elif source_type == 'sciencedirect':
            parser = ScienceDirectParser()
        else:
            logger.warning(f"未知的数据源类型: {source_type}，使用基础解析器")
            parser = BaseParser()
        
        # 缓存解析器实例
        self._parsers[source_type] = parser
        return parser
    
    def _preprocess_data(self, df: pd.DataFrame, source_type: str) -> pd.DataFrame:
        """
        对解析后的数据进行预处理，包括提取发布年份、处理作者列表等
        
        参数:
            df: 解析后的DataFrame
            source_type: 数据源类型
            
        返回:
            预处理后的DataFrame
        """
        if df.empty:
            return df
        
        # 1. 提取发布年份
        df = self._extract_publication_year(df, source_type)
        
        # 2. 处理作者列表
        df = self._process_authors(df, source_type)
        
        # 3. 标准化数据格式（处理列表类型等）
        df = self._standardize_data_format(df)
        
        return df
    
    def _extract_publication_year(self, df: pd.DataFrame, source_type: str) -> pd.DataFrame:
        """从各种日期字段中提取发布年份"""
        # 确保publication_year字段存在
        if 'publication_year' not in df.columns:
            df['publication_year'] = ""
            
            # 对WOS数据 - 从PY字段获取年份
            if source_type == 'wos' and 'PY' in df.columns:
                wos_mask = df['PY'].notna()
                if wos_mask.any():
                    df.loc[wos_mask, 'publication_year'] = df.loc[wos_mask, 'PY'].apply(
                        lambda py: str(py).strip() if pd.notna(py) else ""
                    )
                    logger.info("从PY字段获取WOS数据的publication_year")
            
            # 对PubMed数据 - 从DP字段获取年份
            elif source_type == 'pubmed' and 'DP' in df.columns:
                pubmed_mask = df['DP'].notna()
                if pubmed_mask.any():
                    df.loc[pubmed_mask, 'publication_year'] = df.loc[pubmed_mask, 'DP'].apply(
                        lambda dp: re.search(r'(\d{4})', str(dp)).group(1) if pd.notna(dp) and re.search(r'(\d{4})', str(dp)) else ""
                    )
                    logger.info("从DP字段获取PubMed数据的publication_year")
            
            # 对ScienceDirect数据 - 从year字段获取年份
            elif source_type == 'sciencedirect' and 'year' in df.columns:
                sd_mask = df['year'].notna()
                if sd_mask.any():
                    df.loc[sd_mask, 'publication_year'] = df.loc[sd_mask, 'year'].apply(
                        lambda y: str(y).strip() if pd.notna(y) else ""
                    )
                    logger.info("从year字段获取ScienceDirect数据的publication_year")
            
            # 如果以上都没有，检查publication_date
            if 'publication_date' in df.columns and df['publication_year'].isin(["", None]).any():
                date_mask = df['publication_date'].notna() & df['publication_year'].isin(["", None])
                if date_mask.any():
                    df.loc[date_mask, 'publication_year'] = df.loc[date_mask, 'publication_date'].apply(
                        lambda x: re.search(r'(\d{4})', str(x)).group(1) if pd.notna(x) and re.search(r'(\d{4})', str(x)) else ""
                    )
        
        # 删除不再需要的publication_date和year字段
        for field in ['publication_date', 'year']:
            if field in df.columns:
                df = df.drop(field, axis=1)
                
        return df
    
    def _process_authors(self, df: pd.DataFrame, source_type: str) -> pd.DataFrame:
        """处理作者列表，确保格式统一"""
        # 对于PubMed数据生成full_authors字段(从FAU字段)
        if source_type == 'pubmed' and 'FAU' in df.columns:
            df['full_authors'] = df['FAU'].apply(
                lambda fau_list: ', '.join(fau_list) if isinstance(fau_list, list) 
                else (fau_list if pd.notna(fau_list) else "")
            )
            logger.info("为PubMed数据生成full_authors字段，包含所有作者")
        
        # 处理WOS的AU字段作为authors
        if source_type == 'wos' and 'AU' in df.columns and 'authors' not in df.columns:
            df['authors'] = df['AU'].apply(
                lambda au: ', '.join(au) if isinstance(au, list) 
                else (au if pd.notna(au) else "")
            )
            logger.info("为WOS数据从AU字段生成authors字段")
        
        # 对于ScienceDirect确保authors字段格式统一
        if source_type == 'sciencedirect' and 'authors' in df.columns:
            df['authors'] = df['authors'].apply(
                lambda auth: ', '.join(auth) if isinstance(auth, list) 
                else (auth if pd.notna(auth) else "")
            )
            logger.info("标准化ScienceDirect数据的authors字段格式")
            
        return df
    
    def _standardize_data_format(self, df: pd.DataFrame) -> pd.DataFrame:
        """标准化数据格式，处理列表类型等"""
        # 需要标准化的数组字段
        array_fields = [
            'doi', 'authors', 'pmid', 'IS', 'issn', 'LID', 'FAU', 'full_authors', 
            'AU', 'AD', 'affiliation', 'OT', 'PHST', 'AUID', 'CRDT', 'MH', 
            'keywords', 'mesh_terms'
        ]
        
        # 遍历所有列，将列表类型转换为字符串
        for col in df.columns:
            # 跳过FAU字段，它在process_authors中特殊处理
            if col == 'FAU':
                continue
                
            # 对于应该保持为数组的字段，跳过
            if col in array_fields:
                sample_value = df[col].iloc[0] if not df.empty else None
                if isinstance(sample_value, list):
                    df[col] = df[col].apply(
                        lambda x: ', '.join(map(str, x)) if isinstance(x, list) 
                        else (x if pd.notna(x) else "")
                    )
            
            # 处理其他可能是列表的字段
            else:
                sample_value = df[col].iloc[0] if not df.empty else None
                if isinstance(sample_value, list):
                    df[col] = df[col].apply(
                        lambda x: x[0] if isinstance(x, list) and len(x) > 0 
                        else (', '.join(map(str, x)) if isinstance(x, list) 
                              else x)
                    )
        
        # 对于doi字段，特殊处理：移除[doi]后缀
        if 'doi' in df.columns:
            df['doi'] = df['doi'].apply(
                lambda d: d.replace(" [doi]", "").strip() if isinstance(d, str) and " [doi]" in d else d
            )
            
        return df 