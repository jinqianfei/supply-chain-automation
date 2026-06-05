"""
customer 表查询模块
"""
from typing import Optional, List, Dict
from db.connection import get_connection


def get_by_id(customer_id: str, db_config: Optional[dict] = None) -> Optional[dict]:
    """按货主ID查询"""
    conn = get_connection(db_config)
    cur = conn.cursor()
    
    cur.execute("""
        SELECT customer_id, customer_name, customer_type, contact_person,
               contact_phone, address, warehouse_name, status
        FROM customer
        WHERE customer_id = %s
    """, (customer_id,))
    
    r = cur.fetchone()
    cur.close()
    conn.close()
    
    if not r:
        return None
    
    return {
        "customer_id": r[0],
        "customer_name": r[1],
        "customer_type": r[2],
        "contact_person": r[3],
        "contact_phone": r[4],
        "address": r[5],
        "warehouse_name": r[6],
        "status": r[7],
    }


def search_by_name(name: str, db_config: Optional[dict] = None) -> List[dict]:
    """按名称模糊搜索货主"""
    conn = get_connection(db_config)
    cur = conn.cursor()
    
    cur.execute("""
        SELECT customer_id, customer_name, customer_type, contact_person,
               contact_phone, address, warehouse_name, status
        FROM customer
        WHERE status = 'ACTIVE' AND customer_name LIKE %s
        ORDER BY customer_name
        LIMIT 10
    """, (f"%{name}%",))
    
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    return [
        {
            "customer_id": r[0],
            "customer_name": r[1],
            "customer_type": r[2],
            "contact_person": r[3],
            "contact_phone": r[4],
            "address": r[5],
            "warehouse_name": r[6],
            "status": r[7],
        }
        for r in rows
    ]
