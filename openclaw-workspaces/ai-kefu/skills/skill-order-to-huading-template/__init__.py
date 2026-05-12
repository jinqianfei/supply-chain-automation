"""
skill-order-to-huading-template

将客户订单Excel转换为华鼎出库单模板（31字段）
"""

import os
from typing import Dict, Any, Optional
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from openpyxl.utils import get_column_letter
import pandas as pd
import psycopg2


class OrderToHuadingTemplate:
    """订单转华鼎出库单模板Skill"""
    
    VERSION = "1.0"
    
    # 华鼎模板31字段
    HUADING_FIELDS = [
        "序号", "门店编号", "门店三方编码", "仓库编码", "加急程度\n（0：普通，1：加急）",
        "商品SKU编号", "商品三方SPEC编号", "单位类型", "出库数量",
        "指定库存状态", "出库类型", "配送方式", "指定车型（专配）",
        "是否垫付", "付款方式", "快递公司", "单价", "总金额",
        "是否制定批次", "批次号", "生产日期", "备注", "生产厂家编号",
        "门店收货地址编码", "三方单号", "业务模式", "业务类型",
        "收货人", "联系电话", "收货地址", "C端快递公司"
    ]
    
    # 仓库编码映射
    WAREHOUSE_CODE_MAP = {
        "廊坊仓": 5,
        "天津仓": 8
    }
    
    # 有默认值的字段
    DEFAULT_VALUES = {
        "加急程度": 0,
        "指定库存状态": "正常",
        "出库类型": 201,
        "配送方式": "共配",
        "是否垫付": "否",
        "是否制定批次": "否"
    }
    
    def __init__(self, db_config: Optional[Dict] = None):
        """初始化数据库连接配置"""
        self.db_config = db_config or {
            "host": "localhost",
            "port": 5432,
            "database": "ai_cs_support",
            "user": "jinqianfei"
        }
    
    def execute(self, order_file: str, shipper_id: str, output_file: str = None) -> Dict[str, Any]:
        """
        执行订单转华鼎模板
        
        Args:
            order_file: 客户订单Excel文件路径
            shipper_id: 货主ID
            output_file: 输出文件路径（可选，默认生成到output目录）
        
        Returns:
            Dict包含 success, output_file, order_no, store_code, item_count, message
        """
        try:
            # Step 1: 解析订单
            order_data = self._parse_order(order_file)
            if not order_data:
                return {"success": False, "message": "订单解析失败"}
            
            # Step 2: 门店匹配
            store_info = self._match_store(order_data["store_name"], shipper_id)
            
            # Step 3: SKU匹配
            sku_results = self._match_sku(order_data["items"], shipper_id)
            
            # Step 4: 生成模板
            if not output_file:
                output_dir = "/Users/jinqianfei/openclaw-workspaces/ai-kefu/output"
                os.makedirs(output_dir, exist_ok=True)
                output_file = os.path.join(output_dir, f"华鼎出库单_{order_data['order_no']}.xlsx")
            
            self._generate_template(order_data, store_info, sku_results, output_file)
            
            return {
                "success": True,
                "output_file": output_file,
                "order_no": order_data["order_no"],
                "store_code": store_info.get("store_code", "") if store_info else "",
                "item_count": len(sku_results),
                "message": "模板生成成功"
            }
            
        except Exception as e:
            return {"success": False, "message": f"错误: {str(e)}"}
    
    def _parse_order(self, order_file: str) -> Optional[Dict]:
        """解析客户订单Excel"""
        try:
            df_raw = pd.read_excel(order_file, header=None)
            
            # 解析抬头信息
            order_no = str(df_raw.iloc[1, 1]) if pd.notna(df_raw.iloc[1, 1]) else ""
            store_name = str(df_raw.iloc[2, 1]) if pd.notna(df_raw.iloc[2, 1]) else ""
            
            # 解析商品明细（从第6行开始，第5行是表头）
            items = []
            for i in range(6, len(df_raw)):
                seq = df_raw.iloc[i, 0]
                if pd.isna(seq) or seq == "合计：":
                    continue
                
                product_name = str(df_raw.iloc[i, 2]) if pd.notna(df_raw.iloc[i, 2]) else ""
                quantity = df_raw.iloc[i, 5] if pd.notna(df_raw.iloc[i, 5]) else 0
                remark = df_raw.iloc[i, 8] if pd.notna(df_raw.iloc[i, 8]) else ""
                
                if product_name:
                    items.append({
                        "seq": int(seq) if isinstance(seq, (int, float)) else 1,
                        "product_name": product_name,
                        "quantity": int(quantity) if isinstance(quantity, (int, float)) else 0,
                        "remark": str(remark).strip()
                    })
            
            return {
                "order_no": order_no,
                "store_name": store_name,
                "items": items
            }
            
        except Exception as e:
            print(f"订单解析错误: {e}")
            return None
    
    def _match_store(self, store_name: str, shipper_id: str) -> Optional[Dict]:
        """门店匹配"""
        try:
            conn = psycopg2.connect(**self.db_config)
            cur = conn.cursor()
            
            # 模糊匹配
            cur.execute("""
                SELECT store_code, warehouse, address, contact_person, phone
                FROM store_list
                WHERE store_name LIKE %s
                AND owner_code = %s
                LIMIT 1
            """, (f"%{store_name}%", shipper_id))
            
            row = cur.fetchone()
            conn.close()
            
            if row:
                warehouse_name = row[1] or ""
                warehouse_code = self.WAREHOUSE_CODE_MAP.get(warehouse_name, 5)
                
                return {
                    "store_code": row[0] or "",
                    "warehouse_name": warehouse_name,
                    "warehouse_code": warehouse_code,
                    "address": row[2] or "",
                    "contact_person": row[3] or "",
                    "phone": row[4] or ""
                }
            
            return None
            
        except Exception as e:
            print(f"门店匹配错误: {e}")
            return None
    
    def _match_sku(self, items: list, shipper_id: str) -> list:
        """SKU匹配"""
        try:
            conn = psycopg2.connect(**self.db_config)
            cur = conn.cursor()
            
            results = []
            for item in items:
                sku_code = ""
                unit_type = ""
                
                # 精确匹配
                cur.execute("""
                    SELECT system_sku_code,
                           (unit_conversion_rule->>'ratio')::numeric as ratio
                    FROM shipper_sku_mapping 
                    WHERE customer_sku_name = %s 
                    AND shipper_id = %s
                    ORDER BY ratio DESC
                    LIMIT 1
                """, (item["product_name"], shipper_id))
                
                row = cur.fetchone()
                
                # 模糊匹配
                if not row:
                    clean_name = item["product_name"].split("（")[0].split("(")[0].strip()
                    cur.execute("""
                        SELECT system_sku_code,
                               (unit_conversion_rule->>'ratio')::numeric as ratio
                        FROM shipper_sku_mapping 
                        WHERE customer_sku_name LIKE %s
                        AND shipper_id = %s
                        ORDER BY ratio DESC
                        LIMIT 1
                    """, (f"%{clean_name}%", shipper_id))
                    row = cur.fetchone()
                
                if row:
                    sku_code = row[0] or ""
                    unit_type = "大单位"  # ratio最大的为大单位
                
                results.append({
                    "seq": item["seq"],
                    "product_name": item["product_name"],
                    "quantity": item["quantity"],
                    "remark": item["remark"],  # 从备注字段获取
                    "sku_code": sku_code,
                    "unit_type": unit_type
                })
            
            conn.close()
            return results
            
        except Exception as e:
            print(f"SKU匹配错误: {e}")
            return items
    
    def _generate_template(self, order_data: Dict, store_info: Optional[Dict], 
                          sku_results: list, output_file: str):
        """生成华鼎模板Excel"""
        wb = Workbook()
        ws = wb.active
        ws.title = "omsWare"
        
        # 表头样式
        header_font = Font(bold=True, color="FFFFFF", size=10)
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        
        for col_idx, field_name in enumerate(self.HUADING_FIELDS, start=1):
            cell = ws.cell(row=1, column=col_idx, value=field_name)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_alignment
            cell.border = Border(
                left=Side(style="thin"), right=Side(style="thin"),
                top=Side(style="thin"), bottom=Side(style="thin")
            )
        
        # 列宽
        column_widths = {1: 6, 2: 16, 3: 12, 4: 8, 5: 10, 6: 18, 7: 16, 8: 10, 9: 10,
            10: 10, 11: 8, 12: 10, 13: 12, 14: 8, 15: 8, 16: 10, 17: 8, 18: 10,
            19: 10, 20: 15, 21: 12, 22: 25, 23: 12, 24: 15, 25: 18, 26: 8, 27: 8,
            28: 10, 29: 15, 30: 40, 31: 12}
        for col_idx, width in column_widths.items():
            ws.column_dimensions[get_column_letter(col_idx)].width = width
        
        ws.row_dimensions[1].height = 35
        
        # 数据行样式
        cell_alignment = Alignment(horizontal="center", vertical="center")
        cell_border = Border(
            left=Side(style="thin"), right=Side(style="thin"),
            top=Side(style="thin"), bottom=Side(style="thin")
        )
        
        # 写入数据
        for row_idx, item in enumerate(sku_results, start=2):
            warehouse_code = store_info["warehouse_code"] if store_info else 5
            
            row_data = {
                "序号": 1,  # 同单一组商品相同
                "门店编号": store_info["store_code"] if store_info else "",
                "门店三方编码": "",
                "仓库编码": warehouse_code,
                "加急程度\n（0：普通，1：加急）": self.DEFAULT_VALUES["加急程度"],
                "商品SKU编号": item["sku_code"],
                "商品三方SPEC编号": "",
                "单位类型": item["unit_type"],
                "出库数量": item["quantity"],
                "指定库存状态": self.DEFAULT_VALUES["指定库存状态"],
                "出库类型": self.DEFAULT_VALUES["出库类型"],
                "配送方式": self.DEFAULT_VALUES["配送方式"],
                "指定车型（专配）": "",
                "是否垫付": self.DEFAULT_VALUES["是否垫付"],
                "付款方式": "",  # 空（无默认值）
                "快递公司": "",
                "单价": "",
                "总金额": "",
                "是否制定批次": self.DEFAULT_VALUES["是否制定批次"],
                "批次号": "",
                "生产日期": "",
                "备注": item["remark"],  # 从订单备注字段提取
                "生产厂家编号": "",
                "门店收货地址编码": "",
                "三方单号": order_data["order_no"],  # 从订单提取
                "业务模式": "",  # 空
                "业务类型": "",  # 空
                "收货人": store_info["contact_person"] if store_info else "",
                "联系电话": store_info["phone"] if store_info else "",
                "收货地址": store_info["address"] if store_info else "",
                "C端快递公司": ""
            }
            
            for col_idx, field_name in enumerate(self.HUADING_FIELDS, start=1):
                value = row_data.get(field_name, "")
                cell = ws.cell(row=row_idx, column=col_idx, value=value)
                cell.alignment = cell_alignment
                cell.border = cell_border
        
        wb.save(output_file)


# 快捷调用函数
def convert_order_to_huading(order_file: str, shipper_id: str, output_file: str = None) -> Dict[str, Any]:
    """
    将客户订单转换为华鼎出库单模板
    
    Args:
        order_file: 客户订单Excel文件路径
        shipper_id: 货主ID
        output_file: 输出文件路径（可选）
    
    Returns:
        Dict包含 success, output_file, order_no, store_code, item_count, message
    """
    skill = OrderToHuadingTemplate()
    return skill.execute(order_file, shipper_id, output_file)


if __name__ == "__main__":
    # 测试
    result = convert_order_to_huading(
        order_file="/Users/jinqianfei/.openclaw/media/inbound/沧州任丘三中店_任建华10件_1---cfe7dd95-a460-43bc-9f64-660ab2fa5cfc.xlsx",
        shipper_id="HZ2023061500002"
    )
    print(result)