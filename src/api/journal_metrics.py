import logging
import requests
import time
from typing import Dict, Any, Optional, List

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 缓存字典，用于存储已查询过的期刊信息
_journal_metrics_cache = {}

# 上一次请求的时间戳
_last_request_time = 0

def get_journal_metrics(journal_name: str, api_key: Optional[str] = None,
                        metrics_to_fetch: Optional[List[str]] = None,
                        metrics_column_mapping: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """
    调用easyscholar API获取期刊指标，实现缓存功能

    参数:
        journal_name: 期刊名称
        api_key: API密钥，如果为None则尝试使用环境变量或配置文件中的密钥
        metrics_to_fetch: 需要获取的指标列表，None表示不获取任何指标
        metrics_column_mapping: 指标名称到列名的映射，用于自定义输出列名

    返回:
        期刊指标字典，包含用户配置的指标信息
    """
    if not journal_name:
        logger.warning("警告: 期刊名称为空")
        return {}

    # 检查缓存中是否已存在该期刊的指标
    if journal_name in _journal_metrics_cache:
        return _journal_metrics_cache[journal_name]

    # 尝试从配置中加载API密钥和指标配置
    if api_key is None:
        try:
            from src.config.config_manager import load_config
            config = load_config()
            api_key = config.get("easyscholar_api_key", "")

            # 加载要获取的指标
            if metrics_to_fetch is None and "journal_metrics" in config:
                metrics_to_fetch = config.get("journal_metrics", {}).get("metrics_to_fetch", [])

            # 加载列名映射
            if metrics_column_mapping is None and "journal_metrics" in config:
                metrics_column_mapping = config.get("journal_metrics", {}).get("metrics_column_mapping", {})
        except Exception as e:
            logger.error(f"加载API密钥或指标配置时出错: {str(e)}")
            return {}

    # 如果没有API密钥或要获取的指标为空，直接返回
    if not api_key:
        logger.warning("警告: 未提供API密钥，无法获取期刊指标")
        return {}

    # 如果没有要获取的指标，直接返回空结果
    if not metrics_to_fetch:
        logger.info(f"未配置要获取的期刊指标，跳过查询期刊: {journal_name}")
        return {}

    # 如果未指定列名映射，使用默认映射
    if not metrics_column_mapping:
        metrics_column_mapping = {metric: metric for metric in metrics_to_fetch}

    url = "https://www.easyscholar.cc/open/getPublicationRank"
    params = {
        "secretKey": api_key,
        "publicationName": journal_name
    }

    try:
        # 控制API请求频率，确保每秒最多发送2次请求
        global _last_request_time
        current_time = time.time()
        elapsed_time = current_time - _last_request_time

        if elapsed_time < 0.5:
            wait_time = 0.5 - elapsed_time
            time.sleep(wait_time)

        # 更新最后请求时间
        _last_request_time = time.time()

        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        # 预先创建空结果，确保始终返回相同结构的数据
        empty_result = {metrics_column_mapping.get(metric, metric): "" for metric in metrics_to_fetch}

        # 检查API返回的基本结构是否正确
        if not isinstance(data, dict):
            logger.warning(f"获取期刊 {journal_name} 指标时返回了非字典数据: {type(data)}")
            _journal_metrics_cache[journal_name] = empty_result
            return empty_result

        if data.get("code") != 200 or "data" not in data:
            logger.warning(f"获取期刊 {journal_name} 指标失败，API返回: {data}")
            _journal_metrics_cache[journal_name] = empty_result
            return empty_result

        # 确保data["data"]不是None
        if data["data"] is None:
            logger.warning(f"获取期刊 {journal_name} 指标时返回了空数据")
            _journal_metrics_cache[journal_name] = empty_result
            return empty_result

        # 构建结果字典，根据用户配置的指标
        result = {}

        # 获取数据
        api_data = data["data"]

        if api_data["officialRank"]["all"] is None and api_data["officialRank"]["select"] is None:
            logger.debug(f"期刊 {journal_name} 无具体数据，跳过...")
            return empty_result

        # 从officialRank获取官方指标
        if "officialRank" in api_data and api_data["officialRank"] is not None:
            # 优先使用select集合，如果没有则使用all集合
            if "select" in api_data["officialRank"] and api_data["officialRank"]["select"]:
                official_data = api_data["officialRank"]["select"]
            elif "all" in api_data["officialRank"]:
                official_data = api_data["officialRank"]["all"]
            else:
                official_data = {}

            # 从官方数据中提取需要的指标
            for metric in metrics_to_fetch:
                # 跳过自定义指标，它们在customRank部分处理
                if metric.startswith("custom_"):
                    continue

                # 获取指标对应的列名
                column_name = metrics_column_mapping.get(metric, metric)
                # 从API响应中获取指标值
                result[column_name] = official_data.get(metric, "")

        # 处理自定义数据集 (customRank)
        if "customRank" in api_data and api_data["customRank"] is not None and any(m.startswith("custom_") for m in metrics_to_fetch):
            if "rankInfo" in api_data["customRank"] and api_data["customRank"]["rankInfo"] is not None and "rank" in api_data["customRank"] and api_data["customRank"]["rank"] is not None:
                custom_rank_info = {item["uuid"]: item for item in api_data["customRank"]["rankInfo"] if isinstance(item, dict) and "uuid" in item}

                for rank_item in api_data["customRank"]["rank"]:
                    if not isinstance(rank_item, str):
                        continue

                    parts = rank_item.split("&&&")
                    if len(parts) == 2:
                        uuid, rank_number = parts
                        if uuid in custom_rank_info:
                            custom_dataset = custom_rank_info[uuid]
                            if not isinstance(custom_dataset, dict):
                                continue

                            abbName = custom_dataset.get("abbName", "")

                            # 根据等级(1-5)获取对应等级文本
                            rank_field_mapping = {
                                "1": "oneRankText",
                                "2": "twoRankText",
                                "3": "threeRankText",
                                "4": "fourRankText",
                                "5": "fiveRankText"
                            }

                            rank_field = rank_field_mapping.get(rank_number, "")
                            if not rank_field:
                                continue

                            rank_text = custom_dataset.get(rank_field, "")

                            # 保存自定义数据集结果
                            custom_key = f"custom_{abbName}"
                            if custom_key in metrics_to_fetch:
                                column_name = metrics_column_mapping.get(custom_key, custom_key)
                                result[column_name] = f"{abbName} {rank_text}" if rank_text else ""

        # 将结果保存到缓存
        _journal_metrics_cache[journal_name] = result
        return result
    except Exception as e:
        logger.warning(f"获取期刊 {journal_name} 指标时出错: {str(e)}")
        _journal_metrics_cache[journal_name] = empty_result
        return empty_result

# 清除缓存的函数，在需要重新获取数据时调用
def clear_journal_metrics_cache():
    """清除期刊指标缓存"""
    global _journal_metrics_cache
    _journal_metrics_cache = {}