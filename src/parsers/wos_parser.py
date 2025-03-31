import pandas as pd
import os
import logging
import re

from src.parsers.base_parser import BaseParser

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class WosParser(BaseParser):
    """
    Web of Science文件解析器，负责解析WOS导出的TXT文件
    """
    
    def parse_file(self, file_path: str) -> pd.DataFrame:
        """
        解析WOS文件并转换为DataFrame
        
        参数:
            file_path: WOS导出的文件路径
            
        返回:
            解析后的DataFrame
        """
        # 确保文件存在
        if not os.path.exists(file_path):
            logger.error(f"文件不存在: {file_path}")
            return pd.DataFrame()
        
        # 检查文件扩展名，确定文件类型
        file_ext = os.path.splitext(file_path)[1].lower()
        
        # 根据文件类型使用不同的解析方法
        if file_ext == '.txt':
            return self._parse_txt_file(file_path)
        elif file_ext == '.csv':
            return self._parse_csv_file(file_path)
        elif file_ext == '.xls' or file_ext == '.xlsx':
            return self._parse_excel_file(file_path)
        else:
            logger.error(f"不支持的文件类型: {file_ext}")
            return pd.DataFrame()
    
    def _parse_txt_file(self, file_path: str) -> pd.DataFrame:
        """解析WOS TXT格式文件"""
        data = []
        current_record = {}
        field_code = None
        record_count = 0
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    
                    # 跳过空行和文件头
                    if not line or line.startswith('FN ') or line.startswith('VR '):
                        continue
                    
                    # 检查是否是文件结束标记
                    if line == 'EF':
                        break
                    
                    # 检查是否是新记录开始（通常由 'PT ' 开头）
                    if line.startswith('PT '):
                        # 保存前一条记录（如果存在）
                        if current_record:
                            data.append(current_record)
                            record_count += 1
                            logger.debug(f"添加记录 {record_count}: {current_record.get('PT', 'Unknown')}")
                        
                        # 开始新记录
                        current_record = {'PT': line[3:].strip()}
                        field_code = 'PT'
                    # 检查是否是新字段（两个大写字母后跟空格）
                    elif re.match(r'^[A-Z][A-Z0-9] ', line):
                        field_code = line[:2]
                        field_value = line[3:].strip()
                        
                        # 处理可能有多个值的字段（如AU, AF等）
                        if field_code in current_record:
                            if isinstance(current_record[field_code], list):
                                current_record[field_code].append(field_value)
                            else:
                                current_record[field_code] = [current_record[field_code], field_value]
                        else:
                            current_record[field_code] = field_value
                    # 字段内容的延续（以空格开头的行）
                    elif field_code and line.startswith('   '):
                        # 如果字段已是列表，则追加到最后一个元素
                        if isinstance(current_record[field_code], list):
                            current_record[field_code][-1] += ' ' + line.strip()
                        else:
                            current_record[field_code] += ' ' + line.strip()
            
            # 添加最后一条记录
            if current_record:
                data.append(current_record)
                record_count += 1
                logger.debug(f"添加最后一条记录 {record_count}: {current_record.get('PT', 'Unknown')}")
        
        except Exception as e:
            logger.error(f"解析WOS TXT文件时出错: {str(e)}")
            return pd.DataFrame()
        
        # 转换为DataFrame
        df = pd.DataFrame(data)
        return df
    
    def _parse_csv_file(self, file_path: str) -> pd.DataFrame:
        """解析WOS CSV格式文件"""
        try:
            # 尝试使用不同的编码和分隔符
            encodings = ['utf-8', 'latin1', 'iso-8859-1']
            separators = [',', '\t', ';']
            
            df = None
            for encoding in encodings:
                for sep in separators:
                    try:
                        df = pd.read_csv(file_path, encoding=encoding, sep=sep)
                        if len(df.columns) > 1:  # 确保正确解析了多列
                            logger.info(f"成功使用编码 {encoding} 和分隔符 '{sep}' 解析CSV文件")
                            break
                    except Exception:
                        continue
                if df is not None and len(df.columns) > 1:
                    break
            
            if df is None or len(df.columns) <= 1:
                logger.error("无法正确解析CSV文件，请检查文件格式")
                return pd.DataFrame()
                
            return df
            
        except Exception as e:
            logger.error(f"解析WOS CSV文件时出错: {str(e)}")
            return pd.DataFrame()
    
    def _parse_excel_file(self, file_path: str) -> pd.DataFrame:
        """解析WOS Excel格式文件"""
        try:
            df = pd.read_excel(file_path)
            return df
        except Exception as e:
            logger.error(f"解析WOS Excel文件时出错: {str(e)}")
            return pd.DataFrame()
    
    def standardize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        标准化WOS数据的列名，使其与其他数据源保持一致
        
        参数:
            df: 原始WOS DataFrame
            
        返回:
            标准化后的DataFrame
        """
        column_mapping = {
            'UT': 'wos_id',
            'TI': 'title',
            'AB': 'abstract',
            'PY': 'publication_year',
            'PD': 'publication_date',
            'AU': 'authors',
            'AF': 'full_authors',
            'C1': 'affiliation',
            'SO': 'journal',
            'DI': 'doi',
            'SN': 'issn',
            'DE': 'keywords',
            'ID': 'keywords_plus',
            'PT': 'publication_type',
            'VL': 'volume',
            'IS': 'issue',
            'BP': 'begin_page',
            'EP': 'end_page',
            'PG': 'pages',
            'LA': 'language',
            'TC': 'times_cited',
            'Z9': 'total_times_cited',
            'RP': 'corresponding_author',
            
            'Article Title': 'title',
            'Authors': 'authors',
            'Author Full Names': 'full_authors',
            'Abstract': 'abstract',
            'Journal': 'journal',
            'DOI': 'doi',
            'Publication Year': 'publication_year',
            'Publication Date': 'publication_date',
            'ISSN': 'issn',
            'WOS': 'wos_id',
            'Keywords': 'keywords',
            'Author Keywords': 'keywords',
            'Volume': 'volume',
            'Issue': 'issue',
            'Beginning Page': 'begin_page',
            'Ending Page': 'end_page',
            'Article Number': 'article_number',
            'Language': 'language',
            'Document Type': 'publication_type',
            'Authors with affiliations': 'authors_with_affiliations',
            'Addresses': 'affiliation',
            'Times Cited, All Databases': 'times_cited'
        }
        
        # 重命名存在的列
        for old_col, new_col in column_mapping.items():
            if old_col in df.columns:
                df.rename(columns={old_col: new_col}, inplace=True)
        
        # 确保标准列存在，不存在则创建空列
        standard_columns = ['title', 'abstract', 'publication_date', 'authors', 'journal', 'doi', 'wos_id', 'keywords', 'affiliation']
        for col in standard_columns:
            if col not in df.columns:
                df[col] = None
        
        # 添加数据源标记
        df['source_type'] = 'wos'
        
        return df