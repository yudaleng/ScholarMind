import os
import sys
import json
import logging
from datetime import datetime
from typing import Dict, List, Any
from pathlib import Path

from flask import Flask, request, jsonify, render_template, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config.config_manager import load_config
import yaml
from src.api.journal_metrics import get_journal_metrics
from src.api.llm_api import create_llm_client
from src.api.prompt_templates import load_yaml_templates, OutputConfig
from src.parsers.parsers_manager import ParsersManager
from src.utils.excel_formatter import ExcelFormatter
from main import CombinedProcessor

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

logging.getLogger('werkzeug').setLevel(logging.WARNING)

app = Flask(__name__, template_folder='web/templates', static_folder='web/static')
CORS(app)  # 启用跨域支持

UPLOAD_FOLDER = 'data/uploads'
OUTPUT_FOLDER = 'data/output'
ALLOWED_EXTENSIONS = {'txt'}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

app_config = None
processing_status = {
    'is_processing': False,
    'progress': 0,
    'message': '',
    'error': None,
    'result_file': None,
    'total_records': 0,
    'processed_records': 0,
    'remaining_records': 0
}

def save_config_to_file(config):
    """保存配置到yaml文件"""
    try:
        config_path = os.path.join('src', 'config', 'config.yaml')
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, indent=2)
        logger.info(f"配置已保存到: {config_path}")
    except Exception as e:
        logger.error(f"保存配置文件失败: {str(e)}")

def allowed_file(filename):
    """检查文件扩展名是否允许"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    """主页"""
    return render_template('index.html')

@app.route('/api/config', methods=['GET'])
def get_config():
    """获取当前配置"""
    try:
        global app_config
        if app_config is None:
            # 尝试加载默认配置
            try:
                app_config = load_config()
            except:
                # 如果没有配置文件，返回默认配置结构
                app_config = {
                    'journal_metrics': {'enabled': True, 'metrics_to_fetch': ['sciif', 'sci', 'sciUp']},
                    'llm': {'enabled': True, 'type': 'vllm'},
                    'sources': [],
                    'output': {'excel_path': 'data/output/combined-output.xlsx', 'separate_sheets': True},
                    'prompt': {'default_type': 'medical'},
                    'processing': {'batch_size': 16, 'max_workers': 4}
                }
        
        return jsonify({
            'success': True,
            'config': app_config
        })
    except Exception as e:
        logger.error(f"获取配置失败: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/config', methods=['POST'])
def update_config():
    """更新配置"""
    try:
        global app_config
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': '无效的配置数据'
            }), 400
        
        app_config = data
        
        # 保存配置到文件
        save_config_to_file(app_config)
        
        return jsonify({
            'success': True,
            'message': '配置更新成功'
        })
    except Exception as e:
        logger.error(f"更新配置失败: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/upload', methods=['POST'])
def upload_file():
    """上传文件"""
    try:
        if 'file' not in request.files:
            return jsonify({
                'success': False,
                'error': '没有选择文件'
            }), 400
        
        file = request.files['file']
        source_type = request.form.get('source_type', 'pubmed')
        
        if file.filename == '':
            return jsonify({
                'success': False,
                'error': '没有选择文件'
            }), 400
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            # 添加时间戳避免文件名冲突
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{source_type}_{timestamp}_{filename}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            return jsonify({
                'success': True,
                'message': '文件上传成功',
                'filename': filename,
                'filepath': filepath,
                'source_type': source_type
            })
        else:
            return jsonify({
                'success': False,
                'error': '不支持的文件类型，请上传.txt文件'
            }), 400
            
    except Exception as e:
        logger.error(f"文件上传失败: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/process', methods=['POST'])
def process_data():
    """处理数据"""
    global processing_status, app_config
    
    try:
        if processing_status['is_processing']:
            return jsonify({
                'success': False,
                'error': '正在处理中，请等待当前任务完成'
            }), 400
        
        data = request.get_json()
        sources = data.get('sources', [])
        config_updates = data.get('config', {})
        
        if not sources:
            return jsonify({
                'success': False,
                'error': '没有选择数据源文件'
            }), 400
        
        # 更新配置
        if app_config is None:
            app_config = load_config()
        
        # 应用配置更新并保存到配置文件
        config_updated = False
        for key, value in config_updates.items():
            if key in app_config:
                if isinstance(app_config[key], dict) and isinstance(value, dict):
                    app_config[key].update(value)
                    config_updated = True
                else:
                    app_config[key] = value
                    config_updated = True
            elif key == 'easyscholar_api_key':
                # 特殊处理API密钥
                app_config['easyscholar_api_key'] = value
                config_updated = True
        
        # 保存更新后的配置到文件
        if config_updated:
            save_config_to_file(app_config)
        
        # 设置处理状态
        processing_status = {
            'is_processing': True,
            'progress': 0,
            'message': '开始处理数据...',
            'result_file': None,
            'error': None,
            'total_records': 0,
            'processed_records': 0,
            'remaining_records': 0
        }
        
        # 在后台处理数据
        import threading
        thread = threading.Thread(target=process_data_background, args=(sources, app_config))
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'success': True,
            'message': '数据处理已开始，请查看处理状态'
        })
        
    except Exception as e:
        logger.error(f"启动数据处理失败: {str(e)}")
        processing_status['is_processing'] = False
        processing_status['error'] = str(e)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

def process_data_background(sources: List[Dict], config: Dict):
    """后台处理数据"""
    global processing_status
    
    try:
        processing_status['message'] = '准备数据源...'
        processing_status['progress'] = 1
        processing_status['total_records'] = 0
        processing_status['processed_records'] = 0
        processing_status['remaining_records'] = 0
        
        # 准备数据源配置
        sources_config = []
        for source in sources:
            sources_config.append({
                'type': source['source_type'],
                'path': source['filepath'],
                'enabled': True
            })
        
        processing_status['message'] = '解析数据文件...'
        processing_status['progress'] = 2
        
        # 创建解析器管理器并解析数据
        parser_manager = ParsersManager(sources_config)
        combined_df = parser_manager.parse_all_sources()
        
        if combined_df.empty:
            raise Exception("没有解析到有效数据")
        
        # 更新总记录数
        total_records = len(combined_df)
        processing_status['total_records'] = total_records
        processing_status['remaining_records'] = total_records
        processing_status['message'] = f'成功解析 {total_records} 条记录，开始处理...'
        processing_status['progress'] = 4
        
        # 创建LLM客户端（如果启用）
        llm_client = None
        if config.get('llm', {}).get('enabled', False):
            try:
                llm_config = config.get('llm', {})
                llm_type = llm_config.get('type', 'siliconflow')
                model_params = llm_config.get('model_parameters', {})
                
                # 构建客户端参数
                client_kwargs = {
                    'temperature': model_params.get('temperature', 0.7),
                    'top_p': model_params.get('top_p', 0.9),
                    'max_tokens': model_params.get('max_tokens', 4096)
                }
                
                if llm_type == 'siliconflow':
                    client_kwargs.update({
                        'api_key': llm_config.get('siliconflow_api_key', ''),
                        'base_url': llm_config.get('siliconflow_base_url', 'https://api.siliconflow.cn/v1'),
                        'model': llm_config.get('siliconflow_model', 'Qwen/Qwen2.5-7B-Instruct'),
                        'rpm': llm_config.get('siliconflow_rpm', 1000),
                        'tpm': llm_config.get('siliconflow_tpm', 50000)
                    })
                elif llm_type == 'vllm':
                    client_kwargs.update({
                        'api_key': llm_config.get('vllm_api_key', ''),
                        'api_url': llm_config.get('vllm_api_url', 'http://127.0.0.1:8000/v1/chat/completions'),
                        'model': llm_config.get('vllm_model', 'qwen')
                    })
                elif llm_type == 'ollama':
                    client_kwargs.update({
                        'api_key': llm_config.get('ollama_api_key', ''),
                        'api_url': llm_config.get('ollama_api_url', 'http://localhost:11434/api'),
                        'model': llm_config.get('ollama_model', 'llama3')
                    })
                
                llm_client = create_llm_client(llm_type, **client_kwargs)
                processing_status['message'] = 'LLM客户端创建成功'
            except Exception as e:
                logger.warning(f"LLM客户端创建失败: {str(e)}")
        
        processing_status['progress'] = 9
        
        # 创建期刊指标获取函数（如果启用）
        get_metrics_func = None
        if config.get('journal_metrics', {}).get('enabled', False):
            get_metrics_func = get_journal_metrics
        
        processing_status['message'] = '处理数据中...'
        processing_status['progress'] = 10
        
        # 创建处理器并处理数据
        processor = CombinedProcessor(config, llm_client, get_metrics_func)
        
        # 创建自定义的进度回调函数
        def update_progress_callback(current, total, stage):
            global processing_status
            
            # 分别显示当前阶段的处理状态
            processing_status['processed_records'] = current
            processing_status['remaining_records'] = total - current
            
            # 计算整体进度权重：期刊30%，AI 65%，其他5%
            if stage == 'journal_metrics':
                progress = 10.00 + (current / total) * 30.00  # 10-40%
                processing_status['message'] = f'获取期刊指标中... ({current}/{total})'
            elif stage == 'ai_analysis':
                progress = 40.00 + (current / total) * 65.00  # 40-105%，但会被限制在80%
                processing_status['message'] = f'AI分析处理中... ({current}/{total})'
            else:
                progress = 105.00 + (current / total) * 5.00  # 105-110%，但会被限制在80%
                processing_status['message'] = f'数据处理中... ({current}/{total})'
            
            # 保留2位小数，最大不超过80%
            processing_status['progress'] = round(min(80.00, progress), 2)
        
        # 传递进度回调函数给处理器
        processed_df = processor.process_data(combined_df, progress_callback=update_progress_callback)
        
        processing_status['message'] = '生成Excel文件...'
        processing_status['progress'] = 80
        processing_status['processed_records'] = total_records
        processing_status['remaining_records'] = 0
        
        # 生成输出文件
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_filename = f'scholarmind_result_{timestamp}.xlsx'
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)
        
        # 格式化并保存Excel
        formatter = ExcelFormatter()
        ai_fields = OutputConfig.get_fields(config.get('prompt', {}).get('default_type', 'medical'))
        
        success = formatter.format_excel(
            processed_df, 
            output_path, 
            config.get('output', {}).get('separate_sheets', True),
            ai_fields
        )
        
        if not success:
            raise Exception("Excel文件生成失败")
        
        processing_status = {
            'is_processing': False,
            'progress': 100,
            'message': f'处理完成！共处理 {len(processed_df)} 条记录',
            'result_file': output_filename,
            'error': None,
            'total_records': total_records,
            'processed_records': total_records,
            'remaining_records': 0
        }
        
        logger.info(f"数据处理完成，结果保存到: {output_path}")
        
    except Exception as e:
        logger.error(f"数据处理失败: {str(e)}")
        processing_status = {
            'is_processing': False,
            'progress': 0,
            'message': '',
            'result_file': None,
            'error': str(e),
            'total_records': 0,
            'processed_records': 0,
            'remaining_records': 0
        }

@app.route('/api/status', methods=['GET'])
def get_status():
    """获取处理状态"""
    return jsonify({
        'success': True,
        'status': processing_status
    })

@app.route('/api/download/<filename>', methods=['GET'])
def download_file(filename):
    """下载结果文件"""
    try:
        filepath = os.path.join(app.config['OUTPUT_FOLDER'], filename)
        if os.path.exists(filepath):
            return send_file(filepath, as_attachment=True)
        else:
            return jsonify({
                'success': False,
                'error': '文件不存在'
            }), 404
    except Exception as e:
        logger.error(f"文件下载失败: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/templates', methods=['GET'])
def get_templates():
    """获取可用的提示词模板"""
    try:
        templates_dir = 'src/config/prompts'
        templates, available_types = load_yaml_templates(templates_dir)
        
        template_list = []
        for template_type, template_data in templates.items():
            template_list.append({
                'type': template_type,
                'name': template_data.get('name', template_type),
                'description': template_data.get('description', ''),
                'fields': template_data.get('fields', [])
            })
        
        return jsonify({
            'success': True,
            'templates': template_list
        })
    except Exception as e:
        logger.error(f"获取模板失败: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/templates/<template_type>', methods=['GET'])
def get_template_detail(template_type):
    """获取指定模板的详细信息"""
    try:
        templates_dir = 'src/config/prompts'
        template_file = os.path.join(templates_dir, f"{template_type}.yaml")
        
        if not os.path.exists(template_file):
            return jsonify({
                'success': False,
                'error': '模板不存在'
            }), 404
        
        with open(template_file, 'r', encoding='utf-8') as f:
            template_data = yaml.safe_load(f)
        
        return jsonify({
            'success': True,
            'template': template_data
        })
    except Exception as e:
        logger.error(f"获取模板详情失败: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/templates/<template_type>', methods=['PUT'])
def save_template(template_type):
    """保存模板"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': '无效的请求数据'
            }), 400
        
        templates_dir = 'src/config/prompts'
        template_file = os.path.join(templates_dir, f"{template_type}.yaml")
        
        # 确保目录存在
        os.makedirs(templates_dir, exist_ok=True)
        
        # 保存模板文件
        with open(template_file, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        
        # 重新加载模板
        load_yaml_templates(templates_dir)
        
        return jsonify({
            'success': True,
            'message': '模板保存成功'
        })
    except Exception as e:
        logger.error(f"保存模板失败: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/templates', methods=['POST'])
def create_template():
    """创建新模板"""
    try:
        data = request.get_json()
        if not data or 'type' not in data:
            return jsonify({
                'success': False,
                'error': '缺少模板类型'
            }), 400
        
        template_type = data['type']
        templates_dir = 'src/config/prompts'
        template_file = os.path.join(templates_dir, f"{template_type}.yaml")
        
        # 检查模板是否已存在
        if os.path.exists(template_file):
            return jsonify({
                'success': False,
                'error': '模板已存在'
            }), 409
        
        # 确保目录存在
        os.makedirs(templates_dir, exist_ok=True)
        
        # 创建默认模板结构
        default_template = {
            'type': template_type,
            'name': data.get('name', template_type),
            'description': data.get('description', ''),
            'system': data.get('system', '你是一位专业的文献分析助手。'),
            'user_template': data.get('user_template', '请分析以下文献摘要：\n\n{abstract}'),
            'fields': data.get('fields', ['ai_summary']),
            'default_values': data.get('default_values', {'ai_summary': ''})
        }
        
        # 保存模板文件
        with open(template_file, 'w', encoding='utf-8') as f:
            yaml.dump(default_template, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        
        # 重新加载模板
        load_yaml_templates(templates_dir)
        
        return jsonify({
            'success': True,
            'message': '模板创建成功',
            'template': default_template
        })
    except Exception as e:
        logger.error(f"创建模板失败: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/templates/<template_type>', methods=['DELETE'])
def delete_template(template_type):
    """删除模板"""
    try:
        templates_dir = 'src/config/prompts'
        template_file = os.path.join(templates_dir, f"{template_type}.yaml")
        
        if not os.path.exists(template_file):
            return jsonify({
                'success': False,
                'error': '模板不存在'
            }), 404
        
        # 删除模板文件
        os.remove(template_file)
        
        # 重新加载模板
        load_yaml_templates(templates_dir)
        
        return jsonify({
            'success': True,
            'message': '模板删除成功'
        })
    except Exception as e:
        logger.error(f"删除模板失败: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/clear-data', methods=['POST'])
def clear_data():
    """清空data目录下的所有文件"""
    try:
        data_dir = Path('data')
        if not data_dir.exists():
            return jsonify({
                'success': True,
                'message': 'data目录不存在，无需清空'
            })
        
        # 清空uploads和output目录
        for subdir in ['uploads', 'output']:
            subdir_path = data_dir / subdir
            if subdir_path.exists():
                for file_path in subdir_path.iterdir():
                    if file_path.is_file():
                        file_path.unlink()
                    elif file_path.is_dir():
                        import shutil
                        shutil.rmtree(file_path)
        
        logger.info("data目录文件清空成功")
        return jsonify({
            'success': True,
            'message': 'data目录文件清空成功'
        })
    except Exception as e:
        logger.error(f"清空data目录失败: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/clear-api-keys', methods=['POST'])
def clear_api_keys():
    """清空所有API密钥信息"""
    try:
        config_file = 'config.yaml'
        
        # 读取当前配置
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}
        else:
            config = {}
        
        # 清空API密钥
        if 'llm' in config:
            config['llm']['siliconflow_api_key'] = ''
            config['llm']['vllm_api_key'] = ''
            config['llm']['ollama_api_key'] = ''
        
        if 'journal_metrics' in config:
            config['journal_metrics']['easyscholar_api_key'] = ''
        
        # 保存配置
        with open(config_file, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
        
        # 重新加载全局配置
        global app_config
        app_config = load_config()
        
        logger.info("API密钥清空成功")
        return jsonify({
            'success': True,
            'message': 'API密钥清空成功'
        })
    except Exception as e:
        logger.error(f"清空API密钥失败: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

if __name__ == '__main__':
    # 加载提示词模板
    try:
        templates_dir = 'src/config/prompts'
        templates, available_types = load_yaml_templates(templates_dir)
        logger.info(f"加载了 {len(templates)} 个提示词模板")
    except Exception as e:
        logger.warning(f"加载提示词模板失败: {str(e)}")
    
    # 启动Flask应用
    logger.info("启动ScholarMind Web应用...")
    app.run(host='0.0.0.0', port=8080, debug=True)