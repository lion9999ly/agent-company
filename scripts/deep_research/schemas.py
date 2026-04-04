"""
@description: 深度研究结构化数据 Schema 定义
@dependencies: 无
@last_modified: 2026-04-04
"""

OPTICAL_BENCHMARK_SCHEMA = {
    "product": "string - 产品名称",
    "manufacturer": "string - 制造商",
    "product_type": "string - helmet_integrated / clip_on / smartglasses",
    "display_tech": {"value": "string|null", "source": "string", "confidence": "high|medium|low"},
    "fov_diagonal_deg": {"value": "number|null", "source": "string", "confidence": "high|medium|low"},
    "fov_horizontal_deg": {"value": "number|null", "source": "string", "confidence": "high|medium|low"},
    "resolution": {"value": "string|null", "source": "string", "confidence": "high|medium|low"},
    "brightness_panel_nits": {"value": "number|null", "source": "string", "confidence": "high|medium|low"},
    "brightness_eye_nits": {"value": "number|null", "source": "string", "confidence": "high|medium|low"},
    "eye_box_mm": {"value": "string|null", "source": "string", "confidence": "high|medium|low"},
    "virtual_image_distance_m": {"value": "number|null", "source": "string", "confidence": "high|medium|low"},
    "battery_hours": {"value": "number|null", "source": "string", "confidence": "high|medium|low"},
    "weight_g": {"value": "number|null", "source": "string", "confidence": "high|medium|low"},
    "price_usd": {"value": "number|null", "source": "string", "confidence": "high|medium|low"},
    "display_position": {"value": "string|null - right_eye/left_eye/binocular/visor", "source": "string", "confidence": "high|medium|low"},
    "status": "string - on_sale / announced / prototype / discontinued",
    "notable_issues": "string|null - 已知问题或用户投诉",
    "data_gaps": ["string - 哪些参数搜不到"]
}

LAYOUT_ANALYSIS_SCHEMA = {
    "product": "string",
    "hud_position": {"value": "string|null - 描述显示区域在视野中的位置", "source": "string", "confidence": "high|medium|low"},
    "info_layout": {"value": "string|null - 全屏/分区/单角/多角/底部条", "source": "string", "confidence": "high|medium|low"},
    "simultaneous_elements": {"value": "number|null - 同时显示最多几个信息元素", "source": "string", "confidence": "high|medium|low"},
    "priority_mechanism": {"value": "string|null - 信息优先级切换方式", "source": "string", "confidence": "high|medium|low"},
    "direction_indication": {"value": "string|null - 是否支持方向指示（预警方向）", "source": "string", "confidence": "high|medium|low"}
}

HARDWARE_LAYOUT_SCHEMA = {
    "product": "string",
    "button_count": {"value": "number|null", "source": "string", "confidence": "high|medium|low"},
    "button_position": {"value": "string|null", "source": "string", "confidence": "high|medium|low"},
    "battery_position": {"value": "string|null", "source": "string", "confidence": "high|medium|low"},
    "battery_capacity_mah": {"value": "number|null", "source": "string", "confidence": "high|medium|low"},
    "camera_position": {"value": "string|null", "source": "string", "confidence": "high|medium|low"},
    "camera_specs": {"value": "string|null", "source": "string", "confidence": "high|medium|low"},
    "total_weight_g": {"value": "number|null", "source": "string", "confidence": "high|medium|low"},
    "charging_port": {"value": "string|null", "source": "string", "confidence": "high|medium|low"},
    "led_light_position": {"value": "string|null", "source": "string", "confidence": "high|medium|low"},
    "certification": {"value": "string|null", "source": "string", "confidence": "high|medium|low"}
}

GENERAL_SCHEMA = {
    "topic": "string",
    "key_findings": [{"finding": "string", "source": "string", "confidence": "high|medium|low"}],
    "data_gaps": ["string"]
}