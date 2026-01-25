BASIC_COLS = ["序号", "物品名称", "规格", "数量", "单位", "品牌"]

SLOT_TEMPLATE = [
    "品牌", "备注", "单价", "含税", "含运", "货期", 
    "供应商"
]

# Generate headers
# ["序号"..."品牌", "备注1", "单价1"..."手机1", "备注2"..."手机2"...]
HEADERS = list(BASIC_COLS)
for i in range(1, 4):
    for col in SLOT_TEMPLATE:
        HEADERS.append(f"{col}{i}")
