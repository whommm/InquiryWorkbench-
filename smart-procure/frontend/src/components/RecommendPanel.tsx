import React, { useState, useEffect, useRef } from 'react';
import { recommendSuppliers } from '../utils/api';

interface RecommendPanelProps {
  isOpen: boolean;
  onClose: () => void;
  activeTabId?: string | null;
  selectedRow?: number | null;
  sheetData?: any[][];
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
  isOpen,
  onClose,
  selectedRow = null,
  sheetData = []
}) => {
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [productInfo, setProductInfo] = useState<{
    name: string;
    spec: string;
    brand: string;
  } | null>(null);

  // 使用 ref 存储 sheetData，避免数组引用变化导致的重复渲染
  const sheetDataRef = useRef(sheetData);
  useEffect(() => {
    sheetDataRef.current = sheetData;
  }, [sheetData]);

  // 用于处理竞态条件的请求 ID
  const requestIdRef = useRef(0);

  useEffect(() => {
    if (selectedRow !== null && sheetDataRef.current && sheetDataRef.current.length > selectedRow) {
      fetchRecommendations(selectedRow);
    } else {
      setRecommendations([]);
      setProductInfo(null);
    }
  }, [selectedRow]);  // 只依赖 selectedRow

  const fetchRecommendations = async (rowIndex: number) => {
    // 生成新的请求 ID，用于处理竞态条件
    const currentRequestId = ++requestIdRef.current;

    try {
      setLoading(true);
      setError(null);

      const row = sheetDataRef.current[rowIndex];

      if (!row || row.length < 3) {
        setError('无法获取产品信息');
        return;
      }

      const headers = sheetDataRef.current[0] || [];

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

      // 检查是否是最新的请求，如果不是则忽略结果
      if (currentRequestId !== requestIdRef.current) {
        return;
      }

      setRecommendations(response.recommendations || []);

      if (response.recommendations.length === 0) {
        setError('暂无推荐供应商');
      }
    } catch (err: any) {
      // 检查是否是最新的请求
      if (currentRequestId !== requestIdRef.current) {
        return;
      }
      setError(err.message || '获取推荐失败');
      setRecommendations([]);
    } finally {
      // 只有最新请求才更新 loading 状态
      if (currentRequestId === requestIdRef.current) {
        setLoading(false);
      }
    }
  };

  const renderStars = (rating: number) => {
    return '⭐'.repeat(rating);
  };

  if (!isOpen) return null;

  return (
    <div className="flex flex-col h-full bg-white">
      {/* Header */}
      <div className="p-4 border-b border-gray-100 flex justify-between items-center bg-gray-50/50 shrink-0">
        <div className="flex items-center gap-2">
          <div className="p-1.5 bg-purple-100 text-purple-600 rounded-lg">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
            </svg>
          </div>
          <div>
            <h2 className="text-sm font-semibold text-gray-900">智能推荐</h2>
            <p className="text-xs text-gray-500">基于历史数据匹配</p>
          </div>
        </div>
        <button
          onClick={onClose}
          className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-full transition-colors"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
        
      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 bg-gray-50/30">
        {selectedRow === null ? (
          <div className="flex flex-col items-center justify-center h-full text-gray-500 py-8">
            <div className="w-12 h-12 bg-gray-100 rounded-full flex items-center justify-center mb-3 text-gray-400">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 15l-2 5L9 9l11 4-5 2zm0 0l5 5M7.188 2.239l.777 2.897M5.136 7.965l-2.898-.777M13.95 4.05l-2.122 2.122m-5.657 5.656l-2.12 2.122" />
              </svg>
            </div>
            <p className="text-sm font-medium text-gray-700">请选择一行数据</p>
            <p className="text-xs text-gray-400 mt-1 text-center">点击表格中的任意行<br/>系统将为您推荐供应商</p>
          </div>
        ) : productInfo ? (
          <div className="mb-4 bg-white p-3 rounded-lg border border-gray-200 shadow-sm">
            <h3 className="font-medium text-gray-900 mb-2 flex items-center gap-2 text-sm">
              <span className="w-1 h-3 bg-purple-500 rounded-full"></span>
              当前选中产品
            </h3>
            <div className="space-y-2 text-xs">
              <div className="flex justify-between">
                <span className="text-gray-500">产品名称</span>
                <span className="font-medium text-gray-900 text-right max-w-[60%] truncate">{productInfo.name || '-'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">品牌要求</span>
                <span className="font-medium text-gray-900">{productInfo.brand || '-'}</span>
              </div>
            </div>
          </div>
        ) : null}

        {loading ? (
          <div className="flex items-center justify-center h-32">
            <div className="flex flex-col items-center gap-2">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-600"></div>
              <span className="text-xs text-gray-500">正在分析...</span>
            </div>
          </div>
        ) : error ? (
          <div className="bg-red-50 border border-red-200 text-red-600 p-3 rounded-lg flex items-center gap-2 text-sm">
            <svg className="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            {error}
          </div>
        ) : recommendations.length > 0 ? (
          <div className="space-y-3">
            <h3 className="font-medium text-gray-900 flex items-center gap-2 text-sm">
              <span className="w-1 h-3 bg-emerald-500 rounded-full"></span>
              推荐供应商 ({recommendations.length})
            </h3>
            <div className="space-y-3">
              {recommendations.map((rec) => (
                <div key={rec.supplier_id} className="bg-white p-3 rounded-lg border border-gray-200 shadow-sm hover:shadow-md transition-shadow">
                  <div className="flex justify-between items-start mb-2">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <h4 className="font-semibold text-sm text-gray-900 truncate">{rec.company_name}</h4>
                        <span className={`px-1.5 py-0.5 rounded text-xs font-medium shrink-0 ${
                          rec.rank === 1 ? 'bg-yellow-100 text-yellow-800' :
                          rec.rank <= 3 ? 'bg-blue-100 text-blue-800' :
                          'bg-gray-100 text-gray-600'
                        }`}>
                          #{rec.rank}
                        </span>
                      </div>
                      <div className="flex items-center gap-3 text-xs text-gray-500">
                        <span>{rec.contact_name || '-'}</span>
                        <span>{rec.contact_phone || '-'}</span>
                      </div>
                    </div>
                    <div className="text-right shrink-0 ml-2">
                      <div className="text-lg font-bold text-emerald-600">
                        ¥{(rec.avg_price ?? 0).toLocaleString()}
                      </div>
                      <div className="text-xs text-gray-400">
                        {rec.quote_count ?? 0}次报价
                      </div>
                    </div>
                  </div>

                  {rec.brands && rec.brands.length > 0 && (
                    <div className="flex gap-1 flex-wrap mt-2">
                      {rec.brands.slice(0, 3).map((brand, i) => (
                        <span key={i} className="px-1.5 py-0.5 bg-gray-100 text-gray-600 rounded text-xs">
                          {brand}
                        </span>
                      ))}
                      {rec.brands.length > 3 && (
                        <span className="text-xs text-gray-400">+{rec.brands.length - 3}</span>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center h-32 text-gray-500 bg-white rounded-lg border border-gray-200 border-dashed">
            <div className="w-10 h-10 bg-gray-50 rounded-full flex items-center justify-center mb-2 text-gray-400">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <p className="text-xs">暂无推荐</p>
          </div>
        )}
      </div>
    </div>
  );
};
