import yaml
import os
from typing import List, Dict, Tuple
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 模型输出参数集中配置
class OutputConfig:
    """输出配置类，用于中心化管理各类提示词模板的输出字段"""
    
    # 字段映射 - 会被YAML模板更新
    FIELD_MAPPING = {}
    
    # 默认值映射 - 会被YAML模板更新
    DEFAULT_VALUE_MAPPING = {}
    
    @classmethod
    def get_fields(cls, prompt_type: str) -> List[str]:
        """获取指定提示词类型的输出字段"""
        if prompt_type not in cls.FIELD_MAPPING:
            logger.warning(f"提示词类型 '{prompt_type}' 不存在，使用第一个可用类型")
            # 使用第一个可用的模板类型
            if cls.FIELD_MAPPING:
                prompt_type = next(iter(cls.FIELD_MAPPING))
            else:
                return []
                
        return cls.FIELD_MAPPING.get(prompt_type, [])
    
    @classmethod
    def get_default_values(cls, prompt_type: str) -> Dict[str, str]:
        """获取指定提示词类型的默认值"""
        if prompt_type not in cls.DEFAULT_VALUE_MAPPING:
            logger.warning(f"提示词类型 '{prompt_type}' 不存在默认值，使用第一个可用类型")
            # 使用第一个可用的模板类型
            if cls.DEFAULT_VALUE_MAPPING:
                prompt_type = next(iter(cls.DEFAULT_VALUE_MAPPING))
            else:
                return {}
                
        return dict(cls.DEFAULT_VALUE_MAPPING.get(prompt_type, {}))

class YAMLPromptLoader:
    """YAML提示词模板加载器"""
    
    @staticmethod
    def load_templates(templates_dir: str) -> Dict[str, Dict]:
        """
        从提示词模板目录加载所有YAML模板
        
        参数:
            templates_dir: 模板目录路径
            
        返回:
            提示词模板字典，键为模板类型
        """
        templates = {}
        
        # 确保目录存在
        if not os.path.exists(templates_dir):
            logger.warning(f"提示词模板目录不存在: {templates_dir}")
            return templates
        
        # 遍历目录中的所有YAML文件
        for filename in os.listdir(templates_dir):
            if filename.endswith(('.yaml', '.yml')):
                try:
                    file_path = os.path.join(templates_dir, filename)
                    with open(file_path, 'r', encoding='utf-8') as f:
                        template_data = yaml.safe_load(f)
                    
                    # 确保模板包含必要的字段
                    if 'type' in template_data:
                        template_type = template_data['type']
                        templates[template_type] = template_data
                    else:
                        logger.warning(f"提示词模板缺少type字段: {filename}")
                        
                except Exception as e:
                    logger.error(f"加载提示词模板出错 {filename}: {str(e)}")
                    
        return templates

    @staticmethod
    def update_output_config(templates: Dict[str, Dict]) -> None:
        """
        使用YAML模板更新OutputConfig
        
        参数:
            templates: 提示词模板字典
        """
        # 清空现有映射
        OutputConfig.FIELD_MAPPING.clear()
        OutputConfig.DEFAULT_VALUE_MAPPING.clear()
        
        # 更新FIELD_MAPPING和DEFAULT_VALUE_MAPPING
        for template_type, template_data in templates.items():
            if 'fields' in template_data:
                OutputConfig.FIELD_MAPPING[template_type] = template_data['fields']
            if 'default_values' in template_data:
                OutputConfig.DEFAULT_VALUE_MAPPING[template_type] = template_data['default_values']

class PromptTemplate:
    """提示词模板接口"""
    
    def __init__(self, prompt_type: str):
        """
        初始化提示词模板
        
        参数:
            prompt_type: 提示词类型
        """
        self.prompt_type = prompt_type
        self.output_fields = OutputConfig.get_fields(prompt_type)
        self.default_values = OutputConfig.get_default_values(prompt_type)
    
    def get_system_prompt(self) -> str:
        """获取系统提示词"""
        raise NotImplementedError("子类必须实现get_system_prompt方法")
    
    def get_user_prompt(self, abstract: str) -> str:
        """获取用户提示词"""
        raise NotImplementedError("子类必须实现get_user_prompt方法")
    
    def get_messages(self, abstract: str) -> List[Dict[str, str]]:
        """获取消息列表，用于API请求"""
        return [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": self.get_user_prompt(abstract)}
        ]
    
    def get_output_fields(self) -> List[str]:
        """获取输出字段列表"""
        return self.output_fields
    
    def get_default_values(self) -> Dict[str, str]:
        """获取默认值"""
        return dict(self.default_values)

class YAMLPromptTemplate(PromptTemplate):
    """YAML提示词模板类"""
    
    def __init__(self, template_data: Dict):
        self.type = template_data.get('type', '')
        self.name = template_data.get('name', '')
        
        # 支持两种字段命名方式
        self.system_prompt = template_data.get('system', template_data.get('system_prompt', ''))
        self.user_template = template_data.get('user_template', template_data.get('user_prompt', ''))
        
        self.fields = template_data.get('fields', [])
        self.default_values = template_data.get('default_values', {})
        
        # 调用父类初始化方法
        super().__init__(self.type)
    
    
    def get_system_prompt(self) -> str:
        """获取系统提示词"""
        return self.system_prompt
    
    def get_user_prompt(self, abstract: str) -> str:
        """获取用户提示词，替换{abstract}占位符"""
        return self.user_template.replace('{abstract}', abstract)

# 全局变量保存加载的YAML模板
_YAML_TEMPLATES = {}

def load_yaml_templates(templates_dir: str) -> Tuple[Dict[str, Dict], List[str]]:
    """
    加载所有YAML提示词模板
    
    参数:
        templates_dir: 模板目录路径
        
    返回:
        模板字典，以及可用的提示词类型列表
    """
    global _YAML_TEMPLATES
    _YAML_TEMPLATES = YAMLPromptLoader.load_templates(templates_dir)
    YAMLPromptLoader.update_output_config(_YAML_TEMPLATES)
    
    # 返回可用的提示词类型列表
    available_types = list(_YAML_TEMPLATES.keys())
    
    return _YAML_TEMPLATES, available_types

def create_prompt_template(prompt_type: str) -> PromptTemplate:
    """
    创建提示词模板工厂函数
    
    参数:
        prompt_type: 提示词类型
    
    返回:
        提示词模板实例
    """
    if not prompt_type:
        prompt_type = ""
    else:
        prompt_type = prompt_type.lower()
    
    # 尝试使用YAML模板
    if prompt_type in _YAML_TEMPLATES:
        return YAMLPromptTemplate(_YAML_TEMPLATES[prompt_type])
    
    # 如果找不到指定类型，尝试使用第一个可用类型
    if _YAML_TEMPLATES:
        first_type = next(iter(_YAML_TEMPLATES))
        logger.warning(f"提示词类型 {prompt_type} 不存在，使用类型 {first_type}")
        return YAMLPromptTemplate(_YAML_TEMPLATES[first_type])
    
    raise ValueError("未找到任何可用的提示词模板，请检查提示词模板目录")