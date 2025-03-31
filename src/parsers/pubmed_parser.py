import pandas as pd
import os
import logging
import re

from src.parsers.base_parser import BaseParser

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class PubmedParser(BaseParser):
    """
    PubMed文件解析器，负责解析PubMed导出的TXT文件
    """
    
    def parse_file(self, file_path: str) -> pd.DataFrame:
        """
        解析PubMed TXT文件并转换为DataFrame
        
        参数:
            file_path: PubMed TXT文件路径
            
        返回:
            解析后的DataFrame
        """
        # 确保文件存在
        if not os.path.exists(file_path):
            logger.error(f"文件不存在: {file_path}")
            return pd.DataFrame()
        
        # 指定哪些字段可能重复，存储为列表
        multi_fields = {"IS", "LID", "FAU", "AU", "AD", "OT", "PHST"}

        records = []
        record = {}
        current_field = None

        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.rstrip("\n")
                
                # 遇到空行则认为一条记录结束
                if line.strip() == "":
                    if record:
                        records.append(record)
                        record = {}
                        current_field = None
                    continue

                match = re.match(r'^([A-Z0-9]+)\s*-\s*(.*)', line)
                if match:
                    field = match.group(1)
                    value = match.group(2).strip()

                    # 对 AID 字段进行特殊处理
                    if field == "AID":
                        aid_match = re.match(r'^(.*?)\s+\[(doi|pii)\]$', value, re.IGNORECASE)
                        if aid_match:
                            marker = aid_match.group(2).upper()  # 得到 DOI 或 PII
                            extracted_value = aid_match.group(1).strip()
                            key_to_store = marker  # 分别存入 DOI 或 PII 列
                        else:
                            key_to_store = field
                            extracted_value = value
                    else:
                        key_to_store = field
                        extracted_value = value

                    if key_to_store in multi_fields:
                        if key_to_store in record:
                            record[key_to_store].append(extracted_value)
                        else:
                            record[key_to_store] = [extracted_value]
                    else:
                        if key_to_store in record:
                            if isinstance(record[key_to_store], list):
                                record[key_to_store].append(extracted_value)
                            else:
                                record[key_to_store] = [record[key_to_store], extracted_value]
                        else:
                            record[key_to_store] = extracted_value
                    current_field = key_to_store
                else:
                    if current_field and current_field in record:
                        if current_field in multi_fields:
                            record[current_field][-1] += " " + line.strip()
                        else:
                            if isinstance(record[current_field], list):
                                record[current_field][-1] += " " + line.strip()
                            else:
                                record[current_field] += " " + line.strip()

        # 处理最后一个记录
        if record:
            records.append(record)

        # 如果没有数据，返回空DataFrame
        if not records:
            logger.warning(f"未能从文件中解析出任何记录: {file_path}")
            return pd.DataFrame()
        
        # 转换为DataFrame
        df = pd.DataFrame(records)
        
        return df
    
    def standardize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        标准化PubMed数据的列名
        
        参数:
            df: 原始PubMed DataFrame
            
        返回:
            标准化后的DataFrame
        """
        # 重命名常用列为标准名称
        column_mapping = {
            'PMID': 'pmid',
            'TI': 'title',
            'AB': 'abstract',
            'DP': 'publication_date',
            'AU': 'authors',
            'JT': 'journal',
            'TA': 'journal_abbreviation',
            'MH': 'mesh_terms',
            'FAU': 'full_authors',
            'AD': 'affiliation',
            'LID': 'doi',
            'IS': 'issn',
            'VI': 'volume',
            'IP': 'issue',
            'PG': 'pages',
            'LA': 'language',
            'PT': 'publication_type',
            'OT': 'keywords',
            'EDAT': 'entry_date',
            'CRDT': 'creation_date',
            'MHDA': 'medline_date',
            'CI': 'copyright_info',
            'SO': 'source'
        }
        
        # 重命名存在的列
        for old_col, new_col in column_mapping.items():
            if old_col in df.columns:
                df.rename(columns={old_col: new_col}, inplace=True)
        
        # 确保标准列存在，不存在则创建空列
        standard_columns = ['pmid', 'title', 'abstract', 'publication_date', 'authors', 'journal', 'doi', 'keywords', 'mesh_terms']
        for col in standard_columns:
            if col not in df.columns:
                df[col] = None
        
        # 添加数据源标记
        df['source_type'] = 'pubmed'
        
        return df
    
    def preprocess(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        对PubMed数据进行预处理
        
        参数:
            df: 标准化后的DataFrame
            
        返回:
            预处理后的DataFrame
        """
        # 先调用基类的预处理方法
        df = super().preprocess(df)
        
        # PubMed特有的预处理逻辑
        # 提取DOI（如果LID列包含DOI信息）
        if 'doi' in df.columns and df['doi'].notna().any():
            # 检查doi列的值是否包含[doi]标记，如果是则提取出纯DOI
            df['doi'] = df['doi'].apply(
                lambda x: re.sub(r'\s*\[doi\]$', '', x) if isinstance(x, str) and '[doi]' in x else x
            )
        
        return df
    
    def parse_and_preprocess(self, file_path: str) -> pd.DataFrame:
        """
        解析PubMed文件并预处理
        
        参数:
            file_path: PubMed TXT文件路径
            
        返回:
            处理后的DataFrame
        """
        logger.info(f"开始解析PubMed文件: {file_path}")
        df = self.parse_file(file_path)
        df = self.standardize_columns(df)
        df = self.preprocess(df)
        logger.info(f"PubMed文件解析完成: {file_path}，共{len(df)}条记录")
        return df 