"""
Seed script to populate supplier database with initial data
"""
from app.models.database import get_db, init_db
from app.services.supplier_service import SupplierService

# Initialize database
init_db()

# Supplier data to seed
suppliers_data = [
    {
        "company_name": "苏州怡合达自动化科技有限公司",
        "contact_name": "刘洋",
        "contact_phone": "18962433231",
        "tags": ["怡和达"],
        "owner": "系统预置"
    },
    {
        "company_name": "上海万鑫机电有限公司",
        "contact_name": "陈帆",
        "contact_phone": "15221216668",
        "tags": ["万鑫"],
        "owner": "系统预置"
    },
    {
        "company_name": "硕方电子（天津）有限公司",
        "contact_name": "宋颖",
        "contact_phone": "18102106638",
        "tags": ["硕方"],
        "owner": "系统预置"
    },
    {
        "company_name": "起帆电缆",
        "contact_name": "徐小菊",
        "contact_phone": "18982265872",
        "tags": ["起帆"],
        "owner": "系统预置"
    }
]

# Insert suppliers
db = next(get_db())
supplier_service = SupplierService(db)

print("开始插入供应商数据...")
for supplier_data in suppliers_data:
    try:
        supplier_service.upsert_supplier(**supplier_data)
        print(f"✓ 已插入: {supplier_data['company_name']}")
    except Exception as e:
        print(f"✗ 插入失败 {supplier_data['company_name']}: {e}")

db.commit()
print("\n供应商数据插入完成！")
