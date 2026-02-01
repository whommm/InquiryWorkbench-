import React, { useState, useEffect } from 'react';
import { recommendSuppliers } from '../utils/api';

interface RecommendPanelProps {
  selectedRow: number | null;
  sheetData: any[][];
  onQuickQuote?: (supplierInfo: any) => void;
}

interface Product {
  name: string | null;
  model: string | null;
  brand: string | null;
  price: number | null;
  quote_count: number;
}

interface Recommendation {
  rank: number;
  supplier_id: number | null;
  company_name: string;
  contact_name: string | null;
  contact_phone: string | null;
  quote_count: number;
  avg_price: number;
  min_price: number;
  max_price: number;
  last_quote_text: string;
  star_rating: number;
  brands: string[];
  delivery_times: string[];
  products?: Product[];
  created_by_name?: string | null;
}

export const RecommendPanel: React.FC<RecommendPanelProps> = ({
  selectedRow,
  sheetData,
  onQuickQuote
}) => {
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [productInfo, setProductInfo] = useState<{
    name: string;
    spec: string;
    brand: string;
  } | null>(null);

  useEffect(() => {
    console.log('[RecommendPanel] useEffect triggered', { selectedRow, sheetDataLength: sheetData?.length });
    if (selectedRow !== null && sheetData && sheetData.length > selectedRow) {
      console.log('[RecommendPanel] Calling fetchRecommendations for row:', selectedRow);
      fetchRecommendations(selectedRow);
    } else {
      console.log('[RecommendPanel] Clearing recommendations', { selectedRow, sheetDataLength: sheetData?.length });
      setRecommendations([]);
      setProductInfo(null);
    }
  }, [selectedRow, sheetData]);

  const fetchRecommendations = async (rowIndex: number) => {
    console.log('[RecommendPanel] fetchRecommendations called with rowIndex:', rowIndex);
    try {
      setLoading(true);
      setError(null);

      const row = sheetData[rowIndex];
      console.log('[RecommendPanel] Row data:', row);

      if (!row || row.length < 3) {
        setError('无法获取产品信息');
        return;
      }

      const headers = sheetData[0] || [];

      // 精准匹配"品牌"列
      const brandColIndex = headers.findIndex((h: any) => String(h) === '品牌');
      const brand = brandColIndex >= 0 ? String(row[brandColIndex] || '').trim() : '';

      // 清洗前5列数据作为搜索关键词（排除纯数字、单位等无意义数据）
      const basicColCount = Math.min(6, row.length); // 前6列是基础列
      const searchTerms: string[] = [];

      for (let i = 0; i < basicColCount; i++) {
        if (i === brandColIndex) continue; // 跳过品牌列
        const val = String(row[i] || '').trim();
        if (!val) continue;
        // 过滤纯数字、常见单位
        if (/^\d+$/.test(val)) continue;
        if (['台', '个', '件', '套', '只', '米', '公斤', 'kg', 'pcs', 'm'].includes(val.toLowerCase())) continue;
        searchTerms.push(val);
      }

      const productName = searchTerms.join(' ');
      console.log('[RecommendPanel] Extracted:', { brand, searchTerms, productName });

      if (!productName && !brand) {
        setError('产品信息为空');
        setRecommendations([]);
        return;
      }

      setProductInfo({ name: productName, spec: '', brand });

      // Call API
      const response = await recommendSuppliers({
        product_name: productName,
        spec: '',
        brand: brand,
        limit: 5
      });

      console.log('[RecommendPanel] API response:', response);
      setRecommendations(response.recommendations || []);

      if (response.recommendations.length === 0) {
        setError('暂无推荐供应商');
      }
    } catch (err: any) {
      console.error('[RecommendPanel] Failed to fetch recommendations:', err);
      setError(err.message || '获取推荐失败');
      setRecommendations([]);
    } finally {
      setLoading(false);
    }
  };

  const renderStars = (rating: number) => {
    return '⭐'.repeat(rating);
  };

  if (!selectedRow) {
    return (
      <div className="h-full flex items-center justify-center p-4 text-gray-500 text-center">
        <div>
          <div className="text-4xl mb-2">👆</div>
          <div>点击表格中的某一行</div>
          <div>查看供应商推荐</div>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center p-4">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mx-auto mb-2"></div>
          <div className="text-gray-600">加载推荐中...</div>
        </div>
      </div>
    );
  }

  if (error && recommendations.length === 0) {
    return (
      <div className="h-full flex items-center justify-center p-4 text-gray-500 text-center">
        <div>
          <div className="text-4xl mb-2">😔</div>
          <div>{error}</div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-gray-50">
      {/* Header */}
      <div className="p-4 bg-white border-b">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-lg">🏆</span>
          <h3 className="font-semibold text-gray-800">供应商推荐</h3>
        </div>
        {productInfo && (
          <div className="text-sm text-gray-600">
            <div className="truncate">
              <span className="font-medium">{productInfo.name}</span>
              {productInfo.spec && <span className="ml-2 text-gray-500">{productInfo.spec}</span>}
            </div>
            {productInfo.brand && (
              <div className="text-xs text-gray-500 mt-1">品牌: {productInfo.brand}</div>
            )}
          </div>
        )}
      </div>

      {/* Recommendations List */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {recommendations.map((rec) => (
          <div
            key={rec.rank}
            className="bg-white rounded-lg border border-gray-200 p-4 hover:shadow-md transition-shadow"
          >
            {/* Rank and Stars */}
            <div className="flex items-start justify-between mb-2">
              <div className="flex items-center gap-2">
                <span className="text-lg font-bold text-blue-600">#{rec.rank}</span>
                <span className="text-sm">{renderStars(rec.star_rating)}</span>
              </div>
            </div>

            {/* Company Name */}
            <div className="font-semibold text-gray-800 mb-2 truncate">
              {rec.company_name}
            </div>

            {/* Contact Info */}
            {(rec.contact_name || rec.contact_phone) && (
              <div className="text-sm text-gray-600 mb-2 space-y-1">
                {rec.contact_name && (
                  <div className="flex items-center gap-1">
                    <span>👤</span>
                    <span>{rec.contact_name}</span>
                  </div>
                )}
                {rec.contact_phone && (
                  <div className="flex items-center gap-1">
                    <span>📞</span>
                    <span>{rec.contact_phone}</span>
                  </div>
                )}
              </div>
            )}

            {/* Stats */}
            <div className="grid grid-cols-2 gap-2 text-xs text-gray-600 mb-3">
              <div>
                <span className="text-gray-500">历史报价:</span>
                <span className="ml-1 font-medium">{rec.quote_count}次</span>
              </div>
              <div>
                <span className="text-gray-500">平均价格:</span>
                <span className="ml-1 font-medium text-green-600">¥{rec.avg_price}</span>
              </div>
              <div>
                <span className="text-gray-500">最近报价:</span>
                <span className="ml-1">{rec.last_quote_text}</span>
              </div>
              <div>
                <span className="text-gray-500">价格区间:</span>
                <span className="ml-1">¥{rec.min_price}-{rec.max_price}</span>
              </div>
            </div>

            {/* Brands */}
            {rec.brands && rec.brands.length > 0 && (
              <div className="text-xs text-gray-500 mb-2">
                <span>品牌: </span>
                <span>{rec.brands.join(', ')}</span>
              </div>
            )}

            {/* Matched Products */}
            {rec.products && rec.products.length > 0 && (
              <div className="mb-2 p-2 bg-gray-50 rounded text-xs">
                <div className="text-gray-500 mb-1">匹配产品:</div>
                <div className="space-y-1">
                  {rec.products.slice(0, 3).map((product, idx) => (
                    <div key={idx} className="text-gray-700 truncate">
                      {product.name || product.model}
                      {product.price && (
                        <span className="text-green-600 ml-2">¥{product.price}</span>
                      )}
                    </div>
                  ))}
                  {rec.products.length > 3 && (
                    <div className="text-gray-400">...还有 {rec.products.length - 3} 个产品</div>
                  )}
                </div>
              </div>
            )}

            {/* Source User */}
            {rec.created_by_name && (
              <div className="text-xs text-gray-500 border-t pt-2">
                <span>来源: </span>
                <span className="text-blue-600">{rec.created_by_name}</span>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};
