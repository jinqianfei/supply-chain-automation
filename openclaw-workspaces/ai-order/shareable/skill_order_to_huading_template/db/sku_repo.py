"""
shipper_sku_mapping 表查询模块
"""
from typing import Optional, List, Dict
from db.connection import get_connection


def find_by_shipper(shipper_id: str, keyword: str, db_config: Optional[dict] = None) -> List[dict]:
    """按货主ID和关键词模糊匹配SKU"""
    conn = get_connection(db_config)
    cur = conn.cursor()
    
    cur.execute("""
        SELECT id, shipper_id, shipper_name,
               customer_sku_code, customer_sku_name,
               system_sku_code, system_sku_name,
               unit_conversion_rule, confidence, status
        FROM shipper_sku_mapping
        WHERE shipper_id = %s AND customer_sku_name LIKE %s
        ORDER BY LENGTH(customer_sku_name) ASC
    """, (shipper_id, f"%{keyword}%"))
    
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    return [
        {
            "id": r[0],
            "shipper_id": r[1],
            "shipper_name": r[2],
            "customer_sku_code": r[3],
            "customer_sku_name": r[4],
            "system_sku_code": r[5],
            "system_sku_name": r[6],
            "unit_conversion_rule": r[7],  # JSON dict
            "confidence": float(r[8]) if r[8] else 0,
            "status": r[9],
        }
        for r in rows
    ]


def find_by_exact_code(shipper_id: str, sku_code: str, db_config: Optional[dict] = None) -> Optional[dict]:
    """按货主ID和客户SKU编码精确匹配"""
    conn = get_connection(db_config)
    cur = conn.cursor()
    
    cur.execute("""
        SELECT id, shipper_id, shipper_name,
               customer_sku_code, customer_sku_name,
               system_sku_code, system_sku_name,
               unit_conversion_rule, confidence, status
        FROM shipper_sku_mapping
        WHERE shipper_id = %s AND customer_sku_code = %s
    """, (shipper_id, sku_code))
    
    r = cur.fetchone()
    cur.close()
    conn.close()
    
    if not r:
        return None
    
    return {
        "id": r[0],
        "shipper_id": r[1],
        "shipper_name": r[2],
        "customer_sku_code": r[3],
        "customer_sku_name": r[4],
        "system_sku_code": r[5],
        "system_sku_name": r[6],
        "unit_conversion_rule": r[7],
        "confidence": float(r[8]) if r[8] else 0,
        "status": r[9],
    }


def get_all_by_shipper(shipper_id: str, db_config: Optional[dict] = None) -> List[dict]:
    """获取某个货主的所有SKU映射"""
    conn = get_connection(db_config)
    cur = conn.cursor()
    
    cur.execute("""
        SELECT id, shipper_id, shipper_name,
               customer_sku_code, customer_sku_name,
               system_sku_code, system_sku_name,
               unit_conversion_rule, confidence, status
        FROM shipper_sku_mapping
        WHERE shipper_id = %s AND status = 'ACTIVE'
        ORDER BY customer_sku_name
    """, (shipper_id,))
    
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    return [
        {
            "id": r[0],
            "shipper_id": r[1],
            "shipper_name": r[2],
            "customer_sku_code": r[3],
            "customer_sku_name": r[4],
            "system_sku_code": r[5],
            "system_sku_name": r[6],
            "unit_conversion_rule": r[7],
            "confidence": float(r[8]) if r[8] else 0,
            "status": r[9],
        }
        for r in rows
    ]
