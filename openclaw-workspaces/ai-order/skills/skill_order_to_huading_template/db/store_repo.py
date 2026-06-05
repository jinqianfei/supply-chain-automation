"""
store_list 表查询模块
"""
from typing import Optional, List, Dict
from db.connection import get_connection


def find_store(name: str, db_config: Optional[dict] = None) -> List[dict]:
    """按名称模糊匹配门店"""
    conn = get_connection(db_config)
    cur = conn.cursor()
    
    cur.execute("""
        SELECT store_code, store_name, owner_code, owner_name,
               province, city, district, address, phone, contact_person,
               warehouse
        FROM store_list
        WHERE store_name LIKE %s
    """, (f"%{name}%",))
    
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    return [
        {
            "store_code": r[0] or "",
            "store_name": r[1] or "",
            "owner_code": r[2] or "",
            "owner_name": r[3] or "",
            "province": r[4] or "",
            "city": r[5] or "",
            "district": r[6] or "",
            "address": r[7] or "",
            "phone": r[8] or "",
            "contact_person": r[9] or "",
            "warehouse": r[10] or "",
        }
        for r in rows
    ]


def get_by_code(code: str, db_config: Optional[dict] = None) -> Optional[dict]:
    """按门店编码精确查询"""
    conn = get_connection(db_config)
    cur = conn.cursor()
    
    cur.execute("""
        SELECT store_code, store_name, owner_code, owner_name,
               province, city, district, address, phone, contact_person,
               warehouse
        FROM store_list
        WHERE store_code = %s
    """, (code,))
    
    r = cur.fetchone()
    cur.close()
    conn.close()
    
    if not r:
        return None
    
    return {
        "store_code": r[0] or "",
        "store_name": r[1] or "",
        "owner_code": r[2] or "",
        "owner_name": r[3] or "",
        "province": r[4] or "",
        "city": r[5] or "",
        "district": r[6] or "",
        "address": r[7] or "",
        "phone": r[8] or "",
        "contact_person": r[9] or "",
        "warehouse": r[10] or "",
    }


def get_by_owner(owner_code: str, db_config: Optional[dict] = None) -> List[dict]:
    """按货主ID查询所有门店"""
    conn = get_connection(db_config)
    cur = conn.cursor()
    
    cur.execute("""
        SELECT store_code, store_name, owner_code, owner_name,
               province, city, district, address, phone, contact_person,
               warehouse
        FROM store_list
        WHERE owner_code = %s
        LIMIT 20
    """, (owner_code,))
    
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    return [
        {
            "store_code": r[0] or "",
            "store_name": r[1] or "",
            "owner_code": r[2] or "",
            "owner_name": r[3] or "",
            "province": r[4] or "",
            "city": r[5] or "",
            "district": r[6] or "",
            "address": r[7] or "",
            "phone": r[8] or "",
            "contact_person": r[9] or "",
            "warehouse": r[10] or "",
        }
        for r in rows
    ]



def find_by_phone(phone: str, db_config: Optional[dict] = None) -> Optional[dict]:
    """按手机号精确查询门店"""
    if not phone:
        return None
    conn = get_connection(db_config)
    cur = conn.cursor()
    
    cur.execute("""
        SELECT store_code, store_name, owner_code, owner_name,
               province, city, district, address, phone, contact_person,
               warehouse
        FROM store_list
        WHERE phone = %s
        LIMIT 1
    """, (phone,))
    
    r = cur.fetchone()
    cur.close()
    conn.close()
    
    if not r:
        return None
    
    return {
        "store_code": r[0] or "",
        "store_name": r[1] or "",
        "owner_code": r[2] or "",
        "owner_name": r[3] or "",
        "province": r[4] or "",
        "city": r[5] or "",
        "district": r[6] or "",
        "address": r[7] or "",
        "phone": r[8] or "",
        "contact_person": r[9] or "",
        "warehouse": r[10] or "",
    }
