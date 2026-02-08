# RAG 向量检索增强供应商推荐方案

## 1. 概述

### 1.1 背景

当前 SmartProcure 的供应商推荐算法基于字符串匹配（SequenceMatcher），存在以下局限：

- 无法理解语义相似性（"气缸" vs "气动执行器"）
- 品牌别名需要手动维护硬编码
- 全表扫描性能随数据量增长下降
- 无法跨语言匹配（中英文）

### 1.2 目标

引入 RAG（Retrieval-Augmented Generation）向量检索技术，实现：

- **语义级匹配**：理解产品语义，匹配相似但文字不同的产品
- **自动品牌关联**：无需手动维护品牌别名映射
- **高效检索**：毫秒级返回结果，支持大规模数据
- **混合排序**：结合向量相似度与业务指标（报价次数、时间等）

### 1.3 技术选型

| 组件 | 选型 | 理由 |
|------|------|------|
| 向量数据库 | **pgvector** (第一阶段) | 无需新增组件，与现有 PostgreSQL 集成 |
| Embedding 模型 | **google/gemini-embedding-001** | 768 维，支持中英文，通过 OpenRouter 调用 |
| API 渠道 | **OpenRouter** | 统一 API 接口，支持多种模型 |
| 备选向量库 | Qdrant | 第二阶段扩展，性能更优 |

---

## 2. 架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         FastAPI 后端                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │ API Routes   │───▶│ Recommend    │───▶│ Embedding    │       │
│  │              │    │ Service      │    │ Service      │       │
│  └──────────────┘    └──────────────┘    └──────────────┘       │
│                             │                    │               │
│                             ▼                    ▼               │
│  ┌──────────────────────────────────────────────────────┐       │
│  │                    PostgreSQL                         │       │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐      │       │
│  │  │ suppliers  │  │ supplier_  │  │ product_   │      │       │
│  │  │            │  │ products   │  │ embeddings │      │       │
│  │  └────────────┘  └────────────┘  └────────────┘      │       │
│  │                                   (pgvector)         │       │
│  └──────────────────────────────────────────────────────┘       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 数据流程

```
[用户查询] ──▶ [构建查询文本] ──▶ [生成 Query Embedding]
                                          │
                                          ▼
                              [pgvector 向量检索 Top 50]
                                          │
                                          ▼
                              [业务指标重排序 Rerank]
                                          │
                                          ▼
                              [按供应商聚合 Top 5]
                                          │
                                          ▼
                                    [返回推荐结果]
```

---

## 3. 数据库设计

### 3.1 启用 pgvector 扩展

```sql
-- 在 PostgreSQL 中启用 pgvector 扩展
CREATE EXTENSION IF NOT EXISTS vector;
```

### 3.2 新增 product_embeddings 表

```sql
CREATE TABLE product_embeddings (
    id SERIAL PRIMARY KEY,

    -- 关联 supplier_products 表
    supplier_product_id INTEGER NOT NULL REFERENCES supplier_products(id) ON DELETE CASCADE,

    -- 用于生成 embedding 的原始文本
    embedding_text TEXT NOT NULL,

    -- 向量字段 (768 维，对应 gemini-embedding-001)
    embedding vector(768) NOT NULL,

    -- 元数据（用于过滤）
    brand VARCHAR(100),
    product_category VARCHAR(100),

    -- 时间戳
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- 唯一约束：每个 supplier_product 只有一条 embedding
    UNIQUE(supplier_product_id)
);

-- 创建向量索引 (IVFFlat 适合中等规模数据)
CREATE INDEX idx_product_embeddings_vector
ON product_embeddings
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- 创建普通索引
CREATE INDEX idx_product_embeddings_brand ON product_embeddings(brand);
CREATE INDEX idx_product_embeddings_category ON product_embeddings(product_category);
```

### 3.3 Alembic 迁移脚本

```python
# alembic/versions/xxx_add_product_embeddings.py

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

def upgrade():
    # 启用 pgvector 扩展
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')

    # 创建 product_embeddings 表
    op.create_table(
        'product_embeddings',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('supplier_product_id', sa.Integer(),
                  sa.ForeignKey('supplier_products.id', ondelete='CASCADE'),
                  nullable=False, unique=True),
        sa.Column('embedding_text', sa.Text(), nullable=False),
        sa.Column('embedding', Vector(768), nullable=False),
        sa.Column('brand', sa.String(100)),
        sa.Column('product_category', sa.String(100)),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # 创建向量索引
    op.execute('''
        CREATE INDEX idx_product_embeddings_vector
        ON product_embeddings
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
    ''')

    op.create_index('idx_product_embeddings_brand', 'product_embeddings', ['brand'])

def downgrade():
    op.drop_table('product_embeddings')
```

---

## 4. Embedding 服务设计

### 4.1 服务接口

```python
# app/services/embedding_service.py

import logging
import requests
from typing import List, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)

class EmbeddingService:
    """向量嵌入服务（OpenRouter 渠道）"""

    def __init__(self):
        self.api_key = settings.OPENROUTER_API_KEY
        self.base_url = "https://openrouter.ai/api/v1/embeddings"
        self.model = "google/gemini-embedding-001"
        self.dimensions = 768

    def get_embedding(self, text: str) -> Optional[List[float]]:
        """获取单个文本的 embedding"""
        if not text or not text.strip():
            return None

        try:
            response = requests.post(
                self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "input": text.strip()
                },
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            return data["data"][0]["embedding"]
        except Exception as e:
            logger.error(f"生成 embedding 失败: {e}")
            return None

    def get_embeddings_batch(
        self,
        texts: List[str],
        batch_size: int = 50
    ) -> List[Optional[List[float]]]:
        """批量获取 embeddings"""
        results = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            valid_texts = [t.strip() if t else "" for t in batch]

            try:
                response = requests.post(
                    self.base_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "input": valid_texts
                    },
                    timeout=60
                )
                response.raise_for_status()
                data = response.json()
                for item in data["data"]:
                    results.append(item["embedding"])
            except Exception as e:
                logger.error(f"批量生成 embedding 失败: {e}")
                results.extend([None] * len(batch))

        return results
```

### 4.2 Embedding 文本构建策略

```python
# app/services/embedding_service.py (续)

class EmbeddingTextBuilder:
    """构建用于 embedding 的文本"""

    @staticmethod
    def build_product_text(
        brand: str = "",
        product_name: str = "",
        product_model: str = ""
    ) -> str:
        """
        构建产品 embedding 文本

        策略：品牌 + 产品名称 + 型号
        示例："SMC 气缸 CDQ2B20-10D"
        """
        parts = []
        if brand and brand.strip():
            parts.append(brand.strip())
        if product_name and product_name.strip():
            parts.append(product_name.strip())
        if product_model and product_model.strip():
            parts.append(product_model.strip())
        return " ".join(parts)

    @staticmethod
    def build_query_text(
        product_name: str = "",
        spec: str = "",
        brand: str = ""
    ) -> str:
        """
        构建查询 embedding 文本

        策略：与产品文本保持一致的结构
        """
        parts = []
        if brand and brand.strip():
            parts.append(brand.strip())
        if product_name and product_name.strip():
            parts.append(product_name.strip())
        if spec and spec.strip():
            parts.append(spec.strip())
        return " ".join(parts)
```

---

## 5. 向量检索服务

### 5.1 数据模型

```python
# app/models/database.py (新增)

from pgvector.sqlalchemy import Vector

class ProductEmbedding(Base):
    """产品向量嵌入表"""
    __tablename__ = "product_embeddings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    supplier_product_id = Column(
        Integer,
        ForeignKey("supplier_products.id", ondelete="CASCADE"),
        nullable=False,
        unique=True
    )
    embedding_text = Column(Text, nullable=False)
    embedding = Column(Vector(768), nullable=False)  # gemini-embedding-001: 768 维
    brand = Column(String(100))
    product_category = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    # 关联
    supplier_product = relationship("SupplierProduct", backref="embedding_record")
```

### 5.2 向量检索服务

```python
# app/services/vector_search_service.py

import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.models.database import ProductEmbedding, SupplierProduct, Supplier
from app.services.embedding_service import EmbeddingService, EmbeddingTextBuilder

logger = logging.getLogger(__name__)

class VectorSearchService:
    """向量检索服务"""

    def __init__(self, db: Session):
        self.db = db
        self.embedding_service = EmbeddingService()

    def search_similar_products(
        self,
        query_text: str,
        top_k: int = 50,
        similarity_threshold: float = 0.3
    ) -> List[Dict[str, Any]]:
        """
        向量相似度搜索

        Args:
            query_text: 查询文本
            top_k: 返回数量
            similarity_threshold: 相似度阈值 (0-1)

        Returns:
            匹配的产品列表，包含相似度分数
        """
        # 生成查询向量
        query_embedding = self.embedding_service.get_embedding(query_text)
        if not query_embedding:
            logger.warning("无法生成查询向量")
            return []

        # pgvector 余弦相似度查询
        # 注意：pgvector 的 <=> 操作符返回的是距离，需要转换为相似度
        sql = text("""
            SELECT
                pe.id,
                pe.supplier_product_id,
                pe.embedding_text,
                pe.brand,
                1 - (pe.embedding <=> :query_embedding) as similarity
            FROM product_embeddings pe
            WHERE 1 - (pe.embedding <=> :query_embedding) >= :threshold
            ORDER BY pe.embedding <=> :query_embedding
            LIMIT :top_k
        """)

        results = self.db.execute(
            sql,
            {
                "query_embedding": str(query_embedding),
                "threshold": similarity_threshold,
                "top_k": top_k
            }
        ).fetchall()

        return [
            {
                "embedding_id": row[0],
                "supplier_product_id": row[1],
                "embedding_text": row[2],
                "brand": row[3],
                "similarity": float(row[4])
            }
            for row in results
        ]
```

### 5.3 混合搜索（向量 + 过滤）

```python
# app/services/vector_search_service.py (续)

    def search_with_filter(
        self,
        query_text: str,
        brand_filter: Optional[str] = None,
        top_k: int = 50,
        similarity_threshold: float = 0.3
    ) -> List[Dict[str, Any]]:
        """
        带过滤条件的向量搜索

        支持按品牌过滤，提高搜索精度
        """
        query_embedding = self.embedding_service.get_embedding(query_text)
        if not query_embedding:
            return []

        # 构建动态 SQL
        where_clauses = ["1 - (pe.embedding <=> :query_embedding) >= :threshold"]
        params = {
            "query_embedding": str(query_embedding),
            "threshold": similarity_threshold,
            "top_k": top_k
        }

        if brand_filter:
            where_clauses.append("LOWER(pe.brand) = LOWER(:brand)")
            params["brand"] = brand_filter

        sql = text(f"""
            SELECT
                pe.id,
                pe.supplier_product_id,
                pe.embedding_text,
                pe.brand,
                1 - (pe.embedding <=> :query_embedding) as similarity
            FROM product_embeddings pe
            WHERE {" AND ".join(where_clauses)}
            ORDER BY pe.embedding <=> :query_embedding
            LIMIT :top_k
        """)

        results = self.db.execute(sql, params).fetchall()

        return [
            {
                "embedding_id": row[0],
                "supplier_product_id": row[1],
                "embedding_text": row[2],
                "brand": row[3],
                "similarity": float(row[4])
            }
            for row in results
        ]
```

---

## 6. 改造后的推荐服务

### 6.1 重排序与聚合逻辑

```python
# app/services/supplier_service.py (新增方法)

def _rerank_and_aggregate(
    self,
    vector_results: List[Dict],
    limit: int
) -> List[Dict[str, Any]]:
    """重排序并按供应商聚合"""

    # 获取产品详情
    product_ids = [r["supplier_product_id"] for r in vector_results]
    products = self.db.query(SupplierProduct).filter(
        SupplierProduct.id.in_(product_ids)
    ).all()
    product_map = {p.id: p for p in products}

    # 计算综合分数
    scored_items = []
    for vr in vector_results:
        product = product_map.get(vr["supplier_product_id"])
        if not product:
            continue

        # 综合分数权重分配
        similarity = vr["similarity"]
        quote_factor = min(product.quote_count / 10, 1.0)
        recency = self._calc_recency(product.updated_at)

        score = similarity * 0.6 + quote_factor * 0.3 + recency * 0.1

        scored_items.append({
            "product": product,
            "similarity": similarity,
            "score": score
        })

    # 按供应商聚合
    return self._group_by_supplier(scored_items, limit)
```

### 6.2 供应商聚合方法

```python
def _group_by_supplier(
    self,
    scored_items: List[Dict],
    limit: int
) -> List[Dict[str, Any]]:
    """按供应商分组聚合"""

    supplier_groups: Dict[int, Dict] = {}

    for item in scored_items:
        product = item["product"]
        sid = product.supplier_id

        if sid not in supplier_groups:
            supplier_groups[sid] = {
                "supplier_id": sid,
                "products": [],
                "scores": [],
                "similarities": [],
                "total_quotes": 0,
                "brands": set()
            }

        group = supplier_groups[sid]
        group["products"].append(product)
        group["scores"].append(item["score"])
        group["similarities"].append(item["similarity"])
        group["total_quotes"] += product.quote_count
        if product.brand:
            group["brands"].add(product.brand)

    # 获取供应商信息
    supplier_ids = list(supplier_groups.keys())
    suppliers = self.db.query(Supplier).filter(
        Supplier.id.in_(supplier_ids)
    ).all()
    supplier_map = {s.id: s for s in suppliers}

    # 构建结果
    results = []
    for sid, group in supplier_groups.items():
        supplier = supplier_map.get(sid)
        if not supplier:
            continue

        avg_score = sum(group["scores"]) / len(group["scores"])
        max_similarity = max(group["similarities"])

        results.append({
            "supplier_id": sid,
            "company_name": supplier.company_name,
            "contact_name": supplier.contact_name,
            "contact_phone": supplier.contact_phone,
            "brands": list(group["brands"]),
            "quote_count": group["total_quotes"],
            "avg_similarity": sum(group["similarities"]) / len(group["similarities"]),
            "max_similarity": max_similarity,
            "recommendation_score": avg_score,
            "matched_products": [
                {
                    "name": p.product_name,
                    "model": p.product_model,
                    "brand": p.brand
                }
                for p in group["products"][:3]
            ]
        })

    # 按推荐分数排序
    results.sort(key=lambda x: x["recommendation_score"], reverse=True)
    return results[:limit]
```

---

## 7. 增量索引机制

### 7.1 索引管理服务

```python
# app/services/embedding_index_service.py

import logging
from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.database import SupplierProduct, ProductEmbedding
from app.services.embedding_service import EmbeddingService, EmbeddingTextBuilder

logger = logging.getLogger(__name__)

class EmbeddingIndexService:
    """向量索引管理服务"""

    def __init__(self, db: Session):
        self.db = db
        self.embedding_service = EmbeddingService()

    def index_product(self, product: SupplierProduct) -> Optional[ProductEmbedding]:
        """为单个产品创建向量索引"""

        # 构建 embedding 文本
        text = EmbeddingTextBuilder.build_product_text(
            brand=product.brand or "",
            product_name=product.product_name or "",
            product_model=product.product_model or ""
        )

        if not text.strip():
            logger.warning(f"产品 {product.id} 文本为空，跳过索引")
            return None

        # 生成 embedding
        embedding = self.embedding_service.get_embedding(text)
        if not embedding:
            logger.error(f"产品 {product.id} embedding 生成失败")
            return None

        # 检查是否已存在
        existing = self.db.query(ProductEmbedding).filter(
            ProductEmbedding.supplier_product_id == product.id
        ).first()

        if existing:
            # 更新
            existing.embedding_text = text
            existing.embedding = embedding
            existing.brand = product.brand
            self.db.commit()
            return existing
        else:
            # 新建
            record = ProductEmbedding(
                supplier_product_id=product.id,
                embedding_text=text,
                embedding=embedding,
                brand=product.brand
            )
            self.db.add(record)
            self.db.commit()
            return record
```

### 7.2 批量索引与全量重建

```python
# app/services/embedding_index_service.py (续)

def rebuild_all_indexes(self, batch_size: int = 50) -> Dict[str, int]:
    """全量重建索引"""
    stats = {"total": 0, "success": 0, "failed": 0}

    # 分批处理
    offset = 0
    while True:
        products = self.db.query(SupplierProduct).offset(offset).limit(batch_size).all()
        if not products:
            break

        for product in products:
            stats["total"] += 1
            result = self.index_product(product)
            if result:
                stats["success"] += 1
            else:
                stats["failed"] += 1

        offset += batch_size
        logger.info(f"已处理 {offset} 条记录")

    return stats

def index_missing(self) -> Dict[str, int]:
    """仅索引缺失的记录"""
    stats = {"total": 0, "indexed": 0}

    # 查找没有 embedding 的产品
    missing = self.db.query(SupplierProduct).outerjoin(
        ProductEmbedding,
        SupplierProduct.id == ProductEmbedding.supplier_product_id
    ).filter(ProductEmbedding.id == None).all()

    stats["total"] = len(missing)

    for product in missing:
        if self.index_product(product):
            stats["indexed"] += 1

    return stats
```

### 7.3 自动触发索引

在 `upsert_supplier_product` 方法中自动触发索引更新：

```python
# app/services/supplier_service.py (修改)

def upsert_supplier_product(self, ...):
    """保存供应商-产品关联信息"""
    # ... 原有逻辑 ...

    # 新增：自动更新向量索引
    from app.services.embedding_index_service import EmbeddingIndexService
    index_service = EmbeddingIndexService(self.db)
    index_service.index_product(record)

    return record
```

---

## 8. API 端点设计

### 8.1 推荐接口（V2）

```python
# app/api/routes.py (新增)

@router.post("/suppliers/recommend/v2")
async def recommend_suppliers_v2(
    request: RecommendRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """基于向量检索的供应商推荐（V2）"""
    service = SupplierService(db)
    results = service.recommend_suppliers_v2(
        product_name=request.product_name,
        spec=request.spec or "",
        brand=request.brand or "",
        limit=request.limit or 5
    )
    return {"recommendations": results}
```

### 8.2 索引管理接口

```python
@router.post("/admin/embeddings/rebuild")
async def rebuild_embeddings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """重建所有向量索引（管理员）"""
    service = EmbeddingIndexService(db)
    stats = service.rebuild_all_indexes()
    return {"status": "completed", "stats": stats}

@router.post("/admin/embeddings/sync")
async def sync_embeddings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """同步缺失的向量索引"""
    service = EmbeddingIndexService(db)
    stats = service.index_missing()
    return {"status": "completed", "stats": stats}
```

---

## 9. 部署配置

### 9.1 依赖更新

```txt
# requirements.txt (新增)
pgvector>=0.2.0
```

### 9.2 Docker 配置

```yaml
# docker-compose.yml (修改 PostgreSQL 服务)
services:
  postgres:
    image: pgvector/pgvector:pg15
    # ... 其他配置保持不变
```

### 9.3 环境变量

```bash
# .env (新增 OpenRouter API Key)
OPENROUTER_API_KEY=sk-or-xxx  # OpenRouter API 密钥，用于 Embedding
```

需要在 `app/core/config.py` 中添加配置：

```python
# app/core/config.py (新增)
OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
```

---

## 10. 成本估算

### 10.1 Embedding API 成本

| 模型 | 渠道 | 价格 | 1万条产品成本 |
|------|------|------|---------------|
| google/gemini-embedding-001 | OpenRouter | 免费 / 极低 | ~$0.01 |

**说明**：
- Gemini Embedding 通过 OpenRouter 调用成本极低
- 平均每条产品文本约 50 tokens
- 查询成本可忽略

### 10.2 存储成本

| 数据量 | 向量存储 | PostgreSQL 增量 |
|--------|----------|-----------------|
| 1万条 | ~60 MB | 可忽略 |
| 10万条 | ~600 MB | 可忽略 |
| 100万条 | ~6 GB | 建议迁移 Qdrant |

---

## 11. 实施计划

### 11.1 阶段划分

| 阶段 | 任务 | 产出 |
|------|------|------|
| **阶段一** | 基础设施 | pgvector 扩展、数据表、迁移脚本 |
| **阶段二** | 核心服务 | EmbeddingService、VectorSearchService |
| **阶段三** | 算法改造 | recommend_suppliers_v2 方法 |
| **阶段四** | 索引管理 | 增量索引、全量重建、API |
| **阶段五** | 测试验证 | 效果对比、性能测试 |

### 11.2 详细任务清单

**阶段一：基础设施**
- [ ] 更新 docker-compose.yml 使用 pgvector 镜像
- [ ] 添加 pgvector 依赖到 requirements.txt
- [ ] 创建 Alembic 迁移脚本
- [ ] 执行数据库迁移

**阶段二：核心服务**
- [ ] 实现 EmbeddingService 类
- [ ] 实现 EmbeddingTextBuilder 类
- [ ] 实现 VectorSearchService 类
- [ ] 添加单元测试

**阶段三：算法改造**
- [ ] 在 SupplierService 中添加 recommend_suppliers_v2
- [ ] 实现重排序逻辑
- [ ] 实现供应商聚合逻辑
- [ ] 保留原算法作为回退

**阶段四：索引管理**
- [ ] 实现 EmbeddingIndexService 类
- [ ] 实现自动触发索引逻辑
- [ ] 添加管理 API 端点
- [ ] 编写索引重建脚本

**阶段五：测试验证**
- [ ] 准备测试数据集
- [ ] 对比新旧算法召回率
- [ ] 性能压测
- [ ] 灰度发布

---

## 12. 效果预期

### 12.1 改进对比

| 场景 | 当前算法 | RAG 增强后 |
|------|----------|------------|
| "气缸" 查 "气动执行器" | 无法匹配 | 可匹配 |
| "西门子" 查 "Siemens" | 需手动配置 | 自动关联 |
| "PLC" 查 "可编程控制器" | 无法匹配 | 可匹配 |
| 10万条数据检索 | 秒级 | 毫秒级 |

### 12.2 关键指标

- **召回率提升**：预计 30-50%
- **查询延迟**：< 200ms（含 Embedding 生成）
- **索引延迟**：< 500ms / 条

---

## 13. 新增文件结构

```
backend/app/
├── models/
│   └── database.py          # 新增 ProductEmbedding 模型
├── services/
│   ├── embedding_service.py      # 新增：Embedding 生成服务
│   ├── vector_search_service.py  # 新增：向量检索服务
│   ├── embedding_index_service.py # 新增：索引管理服务
│   └── supplier_service.py       # 修改：添加 recommend_suppliers_v2
└── api/
    └── routes.py            # 修改：添加 V2 推荐接口
```

---

## 14. 总结

本方案采用 **pgvector + OpenAI Embedding** 的轻量级方案，在不引入新组件的前提下，为供应商推荐系统增加语义检索能力。

**核心优势**：
1. 改动最小，复用现有 PostgreSQL
2. 语义匹配能力显著提升
3. 自动品牌关联，无需手动维护
4. 保留原算法作为回退，风险可控

**后续扩展**：
- 数据量超过 10 万时，可迁移至 Qdrant
- 可考虑本地 Embedding 模型（BGE-M3）降低 API 依赖
