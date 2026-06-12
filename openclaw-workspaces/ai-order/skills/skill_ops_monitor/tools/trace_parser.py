"""
trace_parser - 链路解析器
解析思维链、工具链、用户反馈为结构化数据
"""

import re
import json
from typing import List, Dict, Optional


def parse_reasoning_steps(content: str) -> List[Dict]:
    """
    解析思维链内容，提取推理步骤
    
    Args:
        content: assistant 消息内容
    
    Returns:
        list: 推理步骤列表
    """
    steps = []
    
    # 方案 1: 匹配 **思考** 或 **思** 段落
    patterns = [
        r'\*\*(?:思|思考|推理|分析|判断)[^*]*?\*\*(.*?)(?=\*\*|$)',
        r'(?:思|思考|推理|分析|判断)[：:]\s*(.*?)(?:\n|$)',
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, content, re.DOTALL)
        for i, m in enumerate(matches):
            text = m.strip()
            if text and len(text) > 5:
                steps.append({
                    "step_num": len(steps) + 1,
                    "content": text[:500],
                    "pattern": pattern[:30]
                })
    
    # 方案 2: 按行解析（通用格式）
    if not steps:
        lines = content.split('\n')
        for line in lines:
            line = line.strip()
            # 跳过空行和代码块
            if not line or line.startswith('```') or line.startswith('##'):
                continue
            # 匹配序号格式：1. xxx / 2) xxx / - xxx
            if re.match(r'^\d+[.)]\s+', line) or re.match(r'^-\s+', line):
                steps.append({
                    "step_num": len(steps) + 1,
                    "content": re.sub(r'^\d+[.)]\s+', '', line)[:500],
                    "pattern": "line_parse"
                })
    
    return steps


def parse_tool_call(tool_call: Dict) -> Dict:
    """
    解析工具调用
    
    Args:
        tool_call: 原始 tool_call 对象
    
    Returns:
        dict: 解析后的工具调用
    """
    name = tool_call.get("name", "")
    arguments = tool_call.get("arguments", {})
    
    # 如果 arguments 是字符串，尝试解析为 JSON
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            arguments = {"raw": arguments}
    
    return {
        "tool_name": name,
        "tool_args": arguments,
        "args_summary": summarize_args(name, arguments)
    }


def summarize_args(tool_name: str, args: Dict) -> str:
    """
    生成工具参数摘要（用于快速查看）
    """
    if tool_name == "tools_parse" or tool_name == "order_parser":
        return f"输入类型: {args.get('order_type', 'unknown')}"
    
    elif tool_name == "_match_store":
        store_name = args.get("store_name", "")
        return f"门店: {store_name}"
    
    elif tool_name == "_match_sku":
        items = args.get("items", [])
        return f"SKU数量: {len(items)}"
    
    elif tool_name == "template_generator" or tool_name == "_generate_multi_store_template":
        stores = args.get("stores", [])
        return f"门店数: {len(stores)}, SKU数: {args.get('sku_count', 0)}"
    
    elif tool_name == "execute" or tool_name == "exec":
        cmd = args.get("command", args.get("cmd", ""))
        return f"命令: {cmd[:50]}..."
    
    else:
        keys = list(args.keys())[:3]
        return f"参数: {', '.join(keys)}"


def parse_user_feedback(content: str) -> Optional[Dict]:
    """
    解析用户反馈内容
    
    Args:
        content: user 消息内容
    
    Returns:
        dict: 反馈详情 或 None
    """
    content_lower = content.lower()
    content_str = str(content)
    
    # 判断动作类型
    action = None
    if 'confirm' in content_lower or '确认' in content_str:
        action = 'confirm'
    elif 'reject' in content_lower or '拒绝' in content_str:
        action = 'reject'
    elif 'modify' in content_lower or '修改' in content_str or '改' in content_str:
        action = 'modify'
    elif 'yes' in content_lower or '对' in content_str or '正确' in content_str:
        action = 'accept'
    elif 'no' in content_lower or '错' in content_str:
        action = 'reject'
    else:
        # 检查是否只是普通文本回复
        return None
    
    return {
        "action": action,
        "content": content_str[:500],
        "raw_length": len(content_str)
    }


def build_trace_tree(traces: List[Dict]) -> Dict:
    """
    将扁平 traces 构建为树形结构（按 session 和 step 组织）
    
    Args:
        traces: parse_session_traces 返回的数据
    
    Returns:
        dict: 树形结构
    """
    tree = {
        "reasoning_steps": [],
        "tool_calls": [],
        "user_actions": [],
        "summary": {}
    }
    
    for trace in traces:
        step_type = trace.get("step_type")
        
        if step_type == "reasoning":
            tree["reasoning_steps"].append(trace)
        elif step_type == "tool_call":
            tree["tool_calls"].append(trace)
        elif step_type == "user_action":
            tree["user_actions"].append(trace)
    
    # 生成摘要
    tree["summary"] = {
        "reasoning_count": len(tree["reasoning_steps"]),
        "tool_call_count": len(tree["tool_calls"]),
        "user_action_count": len(tree["user_actions"])
    }
    
    return tree


def format_trace_for_display(trace: Dict, max_length: int = 200) -> str:
    """
    格式化 trace 用于显示
    
    Args:
        trace: 单条 trace
        max_length: 最大显示长度
    
    Returns:
        str: 格式化后的文本
    """
    step_type = trace.get("step_type")
    
    if step_type == "reasoning":
        content = trace.get("content", "")
        return f"🤔 {content[:max_length]}"
    
    elif step_type == "tool_call":
        tool_name = trace.get("tool_name", "")
        args_summary = trace.get("args_summary", "")
        return f"🔧 [{tool_name}] {args_summary}"
    
    elif step_type == "user_action":
        action = trace.get("action", "")
        content = trace.get("content", "")[:100]
        return f"👤 用户[{action}]: {content}"
    
    return f"❓ 未知类型: {step_type}"