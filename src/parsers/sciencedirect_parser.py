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
            包含论文信息的字典，如果不是有效的学术文章格式则返回None
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
        
        # 格式验证: 检查是否符合学术文章基本格式
        if len(lines) < 3:  # 至少应包含作者、标题和期刊信息
            logger.debug("条目行数过少，不符合学术文章格式")
            return None
            
        # 检查是否包含卷号信息
        has_volume = False
        for line in lines:
            if re.search(r'Volume\s+\d+', line):
                has_volume = True
                break
                
        # 检查是否包含Abstract和Keywords部分
        has_abstract = 'Abstract' in entry_text or 'Abstract:' in entry_text
        has_keywords = 'Keywords' in entry_text or 'Keywords:' in entry_text
        
        # 如果缺少卷号、摘要或关键词，可能不是标准学术文章
        if not (has_volume and has_abstract and has_keywords):
            logger.debug(f"条目缺少标准学术文章格式元素: Volume存在:{has_volume}, Abstract存在:{has_abstract}, Keywords存在:{has_keywords}")
            return None
        
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
        
        # 提取摘要 - 改进的解析逻辑
        abstract_text = ''
        abstract_start_idx = -1
        keywords_start_idx = -1
        
        # 找到Abstract和Keywords的开始位置
        for i, line in enumerate(lines):
            if (line.startswith('Abstract:') or line == 'Abstract') and abstract_start_idx == -1:
                abstract_start_idx = i
                # 如果Abstract后面有冒号，可能摘要在同一行
                if ':' in line:
                    abstract_text = line.split(':', 1)[1].strip() + ' '
            elif (line.startswith('Keywords:') or line == 'Keywords') and keywords_start_idx == -1:
                keywords_start_idx = i
                break
        
        # 如果找到了Abstract和Keywords标记，提取中间的内容作为摘要
        if abstract_start_idx != -1 and keywords_start_idx != -1:
            # 从Abstract的下一行到Keywords的前一行
            start_line = abstract_start_idx + 1
            # 如果Abstract后面有冒号且已经提取了部分摘要，不需要再次包含第一行
            if abstract_text and ':' in lines[abstract_start_idx]:
                start_line = abstract_start_idx + 1
            
            abstract_lines = lines[start_line:keywords_start_idx]
            additional_abstract = ' '.join(line.strip() for line in abstract_lines if line.strip())
            abstract_text += additional_abstract
            record['abstract'] = abstract_text.strip()
        
        # 提取关键词 - 改进的解析逻辑
        if keywords_start_idx != -1:
            # 从Keywords后开始，直到下一个段落开始
            keywords_text = ''
            i = keywords_start_idx + 1
            
            # 检查Keywords行是否包含冒号，如果有冒号，可能关键词在同一行
            keywords_line = lines[keywords_start_idx]
            if ':' in keywords_line:
                # 提取冒号后的内容作为关键词的开始
                keywords_text = keywords_line.split(':', 1)[1].strip()
            
            # 继续提取后续行的关键词，直到遇到空行或新段落标志
            while i < len(lines) and lines[i].strip():
                if lines[i].strip().startswith(('Background', 'Methods', 'Results', 'Conclusion')):
                    break
                keywords_text += ' ' + lines[i].strip()
                i += 1
            
            # 清理关键词文本
            keywords_text = keywords_text.strip()
            
            # 如果关键词文本不为空，进行后续处理
            if keywords_text:
                # 关键词通常以分号或逗号分隔
                if ';' in keywords_text:
                    record['keywords'] = keywords_text.replace(';', ', ')
                else:
                    record['keywords'] = keywords_text
        
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