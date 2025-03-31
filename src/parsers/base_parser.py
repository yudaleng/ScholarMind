from abc import ABC, abstractmethod
import pandas as pd
import logging

logger = logging.getLogger(__name__)

class BaseParser(ABC):
    """
    数据解析器基类，定义数据源解析接口
    所有特定数据源的解析器应继承这个基类并实现其抽象方法
    """
    
    @abstractmethod
    def parse_file(self, file_path: str) -> pd.DataFrame:
        """
        解析文件并转换为标准DataFrame格式
        
        参数:
            file_path: 输入文件路径
            
        返回:
            标准化的DataFrame，包含统一的列名和格式
        """
        pass
    
    @abstractmethod
    def standardize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        标准化列名和格式，确保不同数据源生成统一的DataFrame结构
        
        参数:
            df: 原始DataFrame
            
        返回:
            标准化后的DataFrame
        """
        pass
    
    def preprocess(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        对DataFrame进行预处理
        
        参数:
            df: 原始DataFrame
            
        返回:
            预处理后的DataFrame
        """
        if 'abstract' in df.columns and df['abstract'].notna().any():
            df = df[df['abstract'].notna()]
        else:
            logger.warning("数据中没有abstract列或所有abstract都为空，跳过摘要过滤")
        
        return df
        
    def get_source_type(self) -> str:
        """
        返回数据源类型标识
        
        返回:
            数据源类型字符串
        """
        # 默认使用类名作为数据源类型
        return self.__class__.__name__.replace('Parser', '').lower()
        
    def parse_and_preprocess(self, file_path: str) -> pd.DataFrame:
        """
        解析文件并进行标准化和预处理
        
        参数:
            file_path: 输入文件路径
            
        返回:
            处理后的DataFrame
        """
        df = self.parse_file(file_path)
        df = self.standardize_columns(df)
        df = self.preprocess(df)
        return df 