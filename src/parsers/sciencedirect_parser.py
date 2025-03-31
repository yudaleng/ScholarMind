import pandas as pd
import os
import logging
import re
from typing import Dict, Any

from src.parsers.base_parser import BaseParser

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ScienceDirectParser(BaseParser):
    """
    ScienceDirect文件解析器，负责解析ScienceDirect导出的TXT文件
    """
    
    def parse_file(self, file_path: str) -> pd.DataFrame:
        """
        解析ScienceDirect TXT文件并转换为DataFrame
        
        参数:
            file_path: ScienceDirect TXT文件路径
            
        返回:
            解析后的DataFrame
        """
        # 确保文件存在
        if not os.path.exists(file_path):
            logger.error(f"文件不存在: {file_path}")
            return pd.DataFrame()
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 每篇论文之间通常以两个或多个连续的换行符分隔
        # 使用正则表达式分割不同的论文条目
        paper_entries = re.split(r'\n{2,}', content)
        records = []
        
        for entry in paper_entries:
            if not entry.strip():
                continue
            
            record = self._parse_paper_entry(entry.strip())
            if record:
                records.append(record)
        
        # 如果没有数据，返回空DataFrame
        if not records:
            logger.warning(f"未能从文件中解析出任何记录: {file_path}")
            return pd.DataFrame()
        
        # 转换为DataFrame
        df = pd.DataFrame(records)
        
        return df
    
    def _parse_paper_entry(self, entry_text: str) -> Dict[str, Any]:
        """
        解析单个论文条目
        
        参数:
            entry_text: 论文条目文本
            
        返回:
            包含论文信息的字典
        """
        # 初始化记录
        record = {
            'authors': '',
            'full_authors': '',  # 添加full_authors字段
            'title': '',
            'journal': '',
            'volume': '',
            'issue': '',
            'year': '',
            'pages': '',
            'doi': '',
            'url': '',
            'abstract': '',
            'keywords': ''
        }
        
        lines = entry_text.split('\n')
        
        # 第一行通常是作者
        if lines:
            # 作者通常格式为：Smith, J., Johnson, M., Williams, R.
            authors = lines[0].strip()
            # 清理作者信息结尾的逗号
            authors = authors.rstrip(',').strip()
            record['authors'] = authors
            record['full_authors'] = authors  # 保存完整作者字符串用于显示
            
            # 尝试解析作者并提取更多信息
            try:
                # 按逗号分隔，但避免分割作者姓名中的逗号
                # 例如：Smith, J., Johnson, M., Williams, R. 应该是三个作者
                author_pattern = r'([^,]+,[^,]+),\s*'
                author_matches = re.findall(author_pattern, authors + ',')
                if author_matches:
                    # 清理每个作者名称
                    cleaned_authors = [author.strip() for author in author_matches]
                    record['authors'] = cleaned_authors
                    record['full_authors'] = authors  # 保留原始格式的完整作者信息
            except Exception as e:
                # 如果解析失败，仍使用原始作者字符串
                logger.warning(f"解析作者名称失败: {str(e)}")
                record['authors'] = authors
                record['full_authors'] = authors
        
        # 第二行通常是标题
        if len(lines) > 1:
            record['title'] = lines[1].strip()
        
        # 第三行通常是期刊名称
        if len(lines) > 2:
            journal = lines[2].strip()
            # 清理期刊名称结尾的逗号
            journal = journal.rstrip(',').strip()
            record['journal'] = journal
        
        # 处理卷号、期号、年份和页码
        volume_issue_pattern = r'Volume\s+(\d+),\s+Issue\s+(\d+)'
        year_pattern = r'(\d{4})'
        pages_pattern = r'(?:pages|Pages)\s+([A-Za-z0-9-]+)'
        article_id_pattern = r'([0-9a-zA-Z]+),'  # 例如 e25469
        
        for line in lines:
            # 提取DOI
            if 'https://doi.org/' in line or 'doi:' in line or 'DOI:' in line or '/10.' in line:
                doi_match = re.search(r'(?:https://doi\.org/|[Dd][Oo][Ii]:|/)(10\.[0-9.]+/[^\s,]+)', line)
                if doi_match:
                    record['doi'] = doi_match.group(1).strip().rstrip('.')
            
            # 提取URL
            if 'sciencedirect.com' in line:
                url_match = re.search(r'(https?://[^\s)]+)', line)
                if url_match:
                    record['url'] = url_match.group(1).strip().rstrip('.')
            
            # 提取卷号和期号
            volume_issue_match = re.search(volume_issue_pattern, line)
            if volume_issue_match:
                record['volume'] = volume_issue_match.group(1)
                record['issue'] = volume_issue_match.group(2)
            else:
                # 单独匹配卷号
                volume_match = re.search(r'Volume\s+(\d+)', line)
                if volume_match:
                    record['volume'] = volume_match.group(1)
                
                # 单独匹配期号
                issue_match = re.search(r'Issue\s+(\d+)', line)
                if issue_match:
                    record['issue'] = issue_match.group(1)
            
            # 提取年份
            year_match = re.search(year_pattern, line)
            if year_match and not record['year']:
                record['year'] = year_match.group(1)
            
            # 提取页码
            pages_match = re.search(pages_pattern, line)
            if pages_match:
                record['pages'] = pages_match.group(1)
            elif not record['pages']:
                # 尝试匹配文章ID（如果没有传统页码）
                article_id_match = re.search(article_id_pattern, line)
                if article_id_match and line.startswith(article_id_match.group(1)):
                    record['pages'] = article_id_match.group(1)
            
            # 提取摘要
            if line.startswith('Abstract:') or line == 'Abstract':
                abstract_index = lines.index(line)
                
                # 寻找摘要结束位置（通常是关键词开始前）
                keywords_index = None
                for i in range(abstract_index + 1, len(lines)):
                    if lines[i].startswith('Keywords:') or lines[i] == 'Keywords':
                        keywords_index = i
                        break
                
                # 提取摘要文本
                abstract_end = keywords_index if keywords_index else len(lines)
                abstract_lines = lines[abstract_index + 1:abstract_end]
                record['abstract'] = ' '.join(line.strip() for line in abstract_lines if line.strip())
            
            # 提取关键词
            if line.startswith('Keywords:') or line == 'Keywords':
                keywords_index = lines.index(line)
                
                # 关键词可能在下一行或多行
                if keywords_index < len(lines) - 1:
                    # 查找关键词结束位置
                    next_section_index = len(lines)
                    for i in range(keywords_index + 1, len(lines)):
                        if lines[i].strip() and (lines[i].strip().endswith(':') or lines[i].strip() == 'Background' or lines[i].strip() == 'Methods' or lines[i].strip() == 'Results' or lines[i].strip() == 'Conclusion'):
                            next_section_index = i
                            break
                    
                    # 提取关键词文本
                    keywords_lines = lines[keywords_index + 1:next_section_index]
                    keywords_text = ' '.join(line.strip() for line in keywords_lines if line.strip())
                    
                    # 移除关键词前的冒号
                    keywords_text = keywords_text.lstrip(':').strip()
                    
                    # 关键词通常以分号分隔
                    record['keywords'] = keywords_text.replace(';', ', ')
        
        # 特殊处理：如果能在文本中找到Abstract部分
        if not record['abstract']:
            abstract_start = entry_text.find('Abstract')
            if abstract_start != -1:
                # 查找关键词部分的开始位置
                keywords_start = entry_text.find('Keywords', abstract_start)
                if keywords_start != -1:
                    # 提取摘要部分（从Abstract后到Keywords前）
                    abstract_text = entry_text[abstract_start + 8:keywords_start].strip()
                    record['abstract'] = abstract_text
                else:
                    # 尝试查找其他可能的结束标记
                    possible_ends = ['Background', 'Methods', 'Results', 'Conclusion']
                    end_pos = float('inf')
                    
                    for marker in possible_ends:
                        pos = entry_text.find(marker, abstract_start)
                        if pos != -1 and pos < end_pos:
                            end_pos = pos
                    
                    if end_pos < float('inf'):
                        abstract_text = entry_text[abstract_start + 8:end_pos].strip()
                        record['abstract'] = abstract_text
        
        # 特殊处理：如果能在文本中找到Keywords部分
        if not record['keywords']:
            keywords_start = entry_text.find('Keywords')
            if keywords_start != -1:
                # 找到Keywords之后的内容直到下一个结构化部分
                remaining_text = entry_text[keywords_start + 8:].strip()
                
                # 移除关键词前的冒号
                remaining_text = remaining_text.lstrip(':').strip()
                
                # 关键词通常在一行中，用分号分隔
                # 查找下一个段落的开始
                next_para = remaining_text.find('\n\n')
                if next_para != -1:
                    keywords_text = remaining_text[:next_para].strip()
                else:
                    keywords_text = remaining_text.strip()
                
                record['keywords'] = keywords_text.replace(';', ', ')
        
        return record
    
    def standardize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        标准化ScienceDirect数据的列名
        
        参数:
            df: 原始ScienceDirect DataFrame
            
        返回:
            标准化后的DataFrame
        """
        # 确保标准列存在，不存在则创建空列
        standard_columns = ['title', 'abstract', 'authors', 'journal', 'doi', 'keywords', 'publication_date']
        for col in standard_columns:
            if col not in df.columns:
                df[col] = None
        
        # 创建publication_date列，将year转换为publication_date
        if 'year' in df.columns:
            df['publication_date'] = df['year']
        
        # 添加数据源标记
        df['source_type'] = 'sciencedirect'
        
        return df
    
    def preprocess(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        对ScienceDirect数据进行预处理
        
        参数:
            df: 标准化后的DataFrame
            
        返回:
            预处理后的DataFrame
        """
        # 先调用基类的预处理方法
        df = super().preprocess(df)
        
        # 清理标题中可能的多余内容
        if 'title' in df.columns:
            df['title'] = df['title'].str.replace(r',\s*$', '', regex=True)
        
        # 清理DOI中可能的多余内容
        if 'doi' in df.columns:
            df['doi'] = df['doi'].str.replace(r'[,\.]$', '', regex=True)
        
        return df
    
    def parse_and_preprocess(self, file_path: str) -> pd.DataFrame:
        """
        解析ScienceDirect文件并预处理
        
        参数:
            file_path: ScienceDirect TXT文件路径
            
        返回:
            处理后的DataFrame
        """
        logger.info(f"开始解析ScienceDirect文件: {file_path}")
        df = super().parse_and_preprocess(file_path)
        return df 