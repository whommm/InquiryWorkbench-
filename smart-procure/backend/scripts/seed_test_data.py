"""
插入测试数据脚本 - 解决冷启动问题
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.database import SessionLocal, Supplier, SupplierProduct, init_db
from datetime import datetime, timedelta

def seed_data():
    """插入测试供应商和产品数据"""
    init_db()
    db = SessionLocal()

    try:
        # 供应商数据
        suppliers_data = [
            {
                "company_name": "苏州黎明液压有限公司",
                "contact_phone": "0512-66668888",
                "contact_name": "张经理",
                "tags": ["黎明", "滤芯", "液压"],
                "quote_count": 15
            },
            {
                "company_name": "上海滤芯科技有限公司",
                "contact_phone": "021-55556666",
                "contact_name": "李工",
                "tags": ["黎明", "滤芯"],
                "quote_count": 8
            },
            {
                "company_name": "无锡液压设备有限公司",
                "contact_phone": "0510-88889999",
                "contact_name": "王总",
                "tags": ["黎明", "液压配件"],
                "quote_count": 12
            },
            {
                "company_name": "杭州工业滤芯有限公司",
                "contact_phone": "0571-77778888",
                "contact_name": "陈经理",
                "tags": ["黎明", "工业滤芯"],
                "quote_count": 6
            },
            {
                "company_name": "南京精密过滤有限公司",
                "contact_phone": "025-66667777",
                "contact_name": "刘工",
                "tags": ["黎明", "过滤设备"],
                "quote_count": 10
            }
        ]

        # 插入供应商
        supplier_ids = []
        for data in suppliers_data:
            existing = db.query(Supplier).filter(
                Supplier.company_name == data["company_name"]
            ).first()

            if existing:
                print(f"[skip] supplier exists: {data['company_name']}")
                supplier_ids.append(existing.id)
            else:
                supplier = Supplier(
                    company_name=data["company_name"],
                    contact_phone=data["contact_phone"],
                    contact_name=data["contact_name"],
                    owner="test_data",
                    tags=data["tags"],
                    quote_count=data["quote_count"],
                    last_quote_date=datetime.now() - timedelta(days=len(supplier_ids) * 5)
                )
                db.add(supplier)
                db.flush()
                supplier_ids.append(supplier.id)
                print(f"[ok] created supplier: {data['company_name']}")

        # 产品数据 - 黎明滤芯系列
        products_data = [
            {"name": "离合器主泵进口滤芯", "model": "TFX-630x180", "brand": "黎明"},
            {"name": "离合器循环泵进口滤芯", "model": "TFX-25x80", "brand": "黎明"},
            {"name": "滤芯", "model": "TFX-160x180", "brand": "黎明"},
            {"name": "试模循环过滤电机吸油口滤芯", "model": "TFX-250X180", "brand": "黎明"},
            {"name": "液压油滤芯", "model": "TFX-400x100", "brand": "黎明"},
            {"name": "回油滤芯", "model": "TFX-800x80", "brand": "黎明"},
        ]

        # 为每个供应商分配产品
        prices = [180, 165, 195, 175, 188]

        for i, sid in enumerate(supplier_ids):
            for j, product in enumerate(products_data):
                if (i + j) % 2 == 0:
                    existing = db.query(SupplierProduct).filter(
                        SupplierProduct.supplier_id == sid,
                        SupplierProduct.product_name == product["name"],
                        SupplierProduct.product_model == product["model"]
                    ).first()

                    if existing:
                        continue

                    price = prices[i] + j * 10
                    sp = SupplierProduct(
                        supplier_id=sid,
                        product_name=product["name"],
                        product_model=product["model"],
                        brand=product["brand"],
                        last_price=price,
                        quote_count=3 + j
                    )
                    db.add(sp)
                    print(f"  [ok] product: {product['model']} - {price}")

        db.commit()
        print("\n[done] test data inserted!")

        # 统计
        supplier_count = db.query(Supplier).count()
        product_count = db.query(SupplierProduct).count()
        print(f"\nDatabase stats:")
        print(f"  - suppliers: {supplier_count}")
        print(f"  - products: {product_count}")

    except Exception as e:
        db.rollback()
        print(f"[error] {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    seed_data()
