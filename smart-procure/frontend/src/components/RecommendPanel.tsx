import React, { useState, useEffect, useRef } from 'react';
import { recommendSuppliers } from '../utils/api';

interface RecommendPanelProps {
  isOpen: boolean;
  onClose: () => void;
  activeTabId?: string | null;
  selectedRow?: number | null;
  sheetData?: unknown[][];
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
  sheetData = [],
}) => {
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [productInfo, setProductInfo] = useState<{
    name: string;
    spec: string;
    brand: string;
  } | null>(null);

  const sheetDataRef = useRef(sheetData);
  useEffect(() => {
    sheetDataRef.current = sheetData;
  }, [sheetData]);

  const requestIdRef = useRef(0);

  useEffect(() => {
    if (selectedRow !== null && sheetDataRef.current && sheetDataRef.current.length > selectedRow) {
      void fetchRecommendations(selectedRow);
    } else {
      setRecommendations([]);
      setProductInfo(null);
    }
  }, [selectedRow]);

  const fetchRecommendations = async (rowIndex: number) => {
    const currentRequestId = ++requestIdRef.current;

    try {
      setLoading(true);
      setError(null);

      const row = sheetDataRef.current[rowIndex];
      if (!Array.isArray(row) || row.length < 3) {
        setError('鏃犳硶鑾峰彇浜у搧淇℃伅');
        return;
      }

      const headers = Array.isArray(sheetDataRef.current[0]) ? sheetDataRef.current[0] : [];

      const brandColIndex = headers.findIndex((h) => String(h ?? '') === '鍝佺墝');
      const brand = brandColIndex >= 0 ? String(row[brandColIndex] ?? '').trim() : '';

      const basicColCount = Math.min(6, row.length);
      const searchTerms: string[] = [];

      for (let i = 0; i < basicColCount; i += 1) {
        if (i === brandColIndex) continue;
        const val = String(row[i] ?? '').trim();
        if (!val) continue;
        if (/^\d+$/.test(val)) continue;
        if (['个', '台', '件', '套', '只', '米', '公斤', 'kg', 'pcs', 'm'].includes(val.toLowerCase())) {
          continue;
        }
        searchTerms.push(val);
      }

      const productName = searchTerms.join(' ');

      if (!productName && !brand) {
        setError('浜у搧淇℃伅涓虹┖');
        setRecommendations([]);
        return;
      }

      setProductInfo({ name: productName, spec: '', brand });

      const response = await recommendSuppliers({
        product_name: productName,
        spec: '',
        brand,
        limit: 5,
      });

      if (currentRequestId !== requestIdRef.current) {
        return;
      }

      const recs = Array.isArray(response?.recommendations)
        ? (response.recommendations as Recommendation[])
        : [];
      setRecommendations(recs);

      if (recs.length === 0) {
        setError('暂无推荐供应商');
      }
    } catch (err: unknown) {
      if (currentRequestId !== requestIdRef.current) {
        return;
      }
      setError(err instanceof Error ? err.message : '鑾峰彇鎺ㄨ崘澶辫触');
      setRecommendations([]);
    } finally {
      if (currentRequestId === requestIdRef.current) {
        setLoading(false);
      }
    }
  };

  if (!isOpen) return null;

  return (
    <div className="flex flex-col h-full bg-white">
      <div className="p-3 border-b border-gray-100 bg-gray-50 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="p-1.5 bg-purple-100 text-purple-600 rounded-lg">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09Z"
              />
            </svg>
          </div>
          <span className="font-semibold text-gray-700 text-sm">鏅鸿兘鎺ㄨ崘</span>
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

      <div className="flex-1 overflow-y-auto p-3">
        {selectedRow === null ? (
          <div className="flex flex-col items-center justify-center h-full text-gray-500 py-8">
            <div className="w-12 h-12 bg-gray-100 rounded-full flex items-center justify-center mb-3 text-gray-400">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M15 15l-2 5L9 9l11 4-5 2zm0 0l5 5M7.188 2.239l.777 2.897M5.136 7.965l-2.898-.777M13.95 4.05l-2.122 2.122m-5.657 5.656l-2.12 2.122"
                />
              </svg>
            </div>
            <p className="text-sm font-medium text-gray-700">Please select a row</p>
            <p className="text-xs text-gray-400 mt-1 text-center">
              Click any row in the sheet
              <br />
              and the system will recommend matching suppliers.
            </p>
          </div>
        ) : productInfo ? (
          <div className="mb-3 bg-purple-50 p-3 rounded-lg border border-purple-100">
            <h3 className="font-medium text-gray-900 text-xs mb-2 flex items-center gap-1">
              <span className="w-1 h-3 bg-purple-500 rounded-full"></span>
              褰撳墠閫変腑浜у搧
            </h3>
            <div className="space-y-1 text-xs">
              <div className="flex">
                <span className="text-gray-500 w-16 flex-shrink-0">鍚嶇О:</span>
                <span className="font-medium text-gray-900 truncate">{productInfo.name || '-'}</span>
              </div>
              <div className="flex">
                <span className="text-gray-500 w-16 flex-shrink-0">鍝佺墝:</span>
                <span className="font-medium text-gray-900">{productInfo.brand || '-'}</span>
              </div>
            </div>
          </div>
        ) : null}

        {loading ? (
          <div className="flex items-center justify-center h-32">
            <div className="flex flex-col items-center gap-2">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-600"></div>
              <span className="text-xs text-gray-500">姝ｅ湪鍒嗘瀽...</span>
            </div>
          </div>
        ) : error ? (
          <div className="bg-red-50 border border-red-200 text-red-600 p-3 rounded-lg flex items-center gap-2 text-xs">
            <svg className="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
            {error}
          </div>
        ) : recommendations.length > 0 ? (
          <div className="space-y-3">
            <h3 className="font-medium text-gray-900 text-xs flex items-center gap-1">
              <span className="w-1 h-3 bg-emerald-500 rounded-full"></span>
              鎺ㄨ崘渚涘簲鍟?({recommendations.length})
            </h3>
            <div className="space-y-2">
              {recommendations.map((rec) => (
                <div
                  key={rec.supplier_id}
                  className="bg-white p-3 rounded-lg border border-gray-200 shadow-sm hover:shadow-md transition-shadow"
                >
                  <div className="flex justify-between items-start mb-2">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5 mb-1">
                        <h4 className="font-semibold text-sm text-gray-900 truncate">{rec.company_name}</h4>
                        <span
                          className={`px-1.5 py-0.5 rounded text-[10px] font-medium flex-shrink-0 ${
                            rec.rank === 1
                              ? 'bg-yellow-100 text-yellow-800'
                              : rec.rank <= 3
                                ? 'bg-blue-100 text-blue-800'
                                : 'bg-gray-100 text-gray-600'
                          }`}
                        >
                          #{rec.rank}
                        </span>
                      </div>
                      <div className="flex items-center gap-2 text-[11px] text-gray-500">
                        <span>{rec.contact_name || '鏈～鍐?'}</span>
                        <span>路</span>
                        <span>{rec.contact_phone || '鏈～鍐?'}</span>
                      </div>
                    </div>
                    <div className="text-right flex-shrink-0 ml-2">
                      <div className="text-base font-bold text-emerald-600">楼{(rec.avg_price ?? 0).toLocaleString()}</div>
                      <div className="text-[10px] text-gray-400">{rec.quote_count ?? 0}娆℃姤浠?</div>
                    </div>
                  </div>

                  {rec.brands && rec.brands.length > 0 && (
                    <div className="flex gap-1 flex-wrap mb-2">
                      {rec.brands.slice(0, 3).map((brand, i) => (
                        <span key={i} className="px-1.5 py-0.5 bg-gray-100 text-gray-600 rounded text-[10px]">
                          {brand}
                        </span>
                      ))}
                      {rec.brands.length > 3 && (
                        <span className="text-[10px] text-gray-400">+{rec.brands.length - 3}</span>
                      )}
                    </div>
                  )}

                  <div className="pt-2 border-t border-gray-100 flex justify-between items-center">
                    <p className="text-[11px] text-gray-500 italic truncate max-w-[180px]">"{rec.last_quote_text || '-'}"</p>
                    <span className="text-[10px] text-yellow-500">猸?{(rec.star_rating ?? 0).toFixed(1)}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
};

