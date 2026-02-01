import { useState, useEffect } from 'react';
import { listSuppliers, searchSuppliers, deleteSupplier } from '../utils/api';

interface Supplier {
  id: number;
  company_name: string;
  contact_phone: string;
  contact_name: string | null;
  owner: string;
  tags: string[];
  quote_count: number;
  last_quote_date: string | null;
  created_at?: string;
  created_by_name?: string | null;
}

interface SupplierPanelProps {
  onClose: () => void;
}

const SupplierPanel = ({ onClose }: SupplierPanelProps) => {
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [isSearching, setIsSearching] = useState(false);

  useEffect(() => {
    loadSuppliers();
  }, []);

  const loadSuppliers = async () => {
    try {
      setLoading(true);
      const response = await listSuppliers();
      setSuppliers(response.suppliers || []);
    } catch (error) {
      console.error('Failed to load suppliers:', error);
      alert('加载供应商列表失败');
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = async () => {
    if (!searchQuery.trim()) {
      loadSuppliers();
      return;
    }

    try {
      setIsSearching(true);
      const response = await searchSuppliers(searchQuery.trim());
      setSuppliers(response.suppliers || []);
    } catch (error) {
      console.error('Failed to search suppliers:', error);
      alert('搜索失败');
    } finally {
      setIsSearching(false);
    }
  };

  const handleDelete = async (supplierId: number, companyName: string) => {
    if (!confirm(`确定要删除供应商 "${companyName}" 吗？`)) {
      return;
    }

    try {
      await deleteSupplier(supplierId);
      await loadSuppliers();
    } catch (error) {
      console.error('Failed to delete supplier:', error);
      alert('删除失败');
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-[900px] max-h-[700px] flex flex-col">
        {/* Header */}
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
          <h2 className="text-xl font-semibold text-gray-900">供应商管理</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-2xl"
          >
            ×
          </button>
        </div>

        {/* Search */}
        <div className="px-6 py-3 border-b border-gray-200 flex gap-2">
          <input
            type="text"
            placeholder="搜索供应商（公司名称、联系人、电话）..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
            className="flex-1 px-3 py-2 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <button
            onClick={handleSearch}
            disabled={isSearching}
            className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 disabled:bg-gray-400"
          >
            {isSearching ? '搜索中...' : '搜索'}
          </button>
          <button
            onClick={loadSuppliers}
            className="px-4 py-2 bg-gray-500 text-white rounded hover:bg-gray-600"
          >
            重置
          </button>
        </div>

        {/* List */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {loading ? (
            <div className="text-center text-gray-500 py-8">加载中...</div>
          ) : suppliers.length === 0 ? (
            <div className="text-center text-gray-500 py-8">
              {searchQuery ? '没有找到匹配的供应商' : '暂无供应商数据'}
            </div>
          ) : (
            <div className="space-y-3">
              {suppliers.map((supplier) => (
                <div
                  key={supplier.id}
                  className="border border-gray-200 rounded-lg p-4 hover:bg-gray-50 transition-colors"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <h3 className="font-medium text-gray-900 text-lg">
                        {supplier.company_name}
                      </h3>
                      <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-sm text-gray-600">
                        <div>
                          <span className="font-medium">联系人：</span>
                          {supplier.contact_name || '未填写'}
                        </div>
                        <div>
                          <span className="font-medium">电话：</span>
                          {supplier.contact_phone}
                        </div>
                        <div>
                          <span className="font-medium">报价次数：</span>
                          {supplier.quote_count} 次
                        </div>
                        <div>
                          <span className="font-medium">最后报价：</span>
                          {supplier.last_quote_date
                            ? new Date(supplier.last_quote_date).toLocaleDateString('zh-CN')
                            : '无'}
                        </div>
                        <div>
                          <span className="font-medium">录入方式：</span>
                          {supplier.owner}
                        </div>
                        {supplier.created_by_name && (
                          <div>
                            <span className="font-medium">来源：</span>
                            <span className="text-blue-600">{supplier.created_by_name}</span>
                          </div>
                        )}
                        {supplier.tags && supplier.tags.length > 0 && (
                          <div className="col-span-2">
                            <span className="font-medium">标签：</span>
                            {supplier.tags.map((tag, idx) => (
                              <span
                                key={idx}
                                className="inline-block ml-1 px-2 py-0.5 bg-blue-100 text-blue-700 rounded text-xs"
                              >
                                {tag}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                    <div className="ml-4">
                      <button
                        onClick={() => handleDelete(supplier.id, supplier.company_name)}
                        className="px-3 py-1 text-sm bg-red-500 text-white rounded hover:bg-red-600"
                      >
                        删除
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-gray-200 text-sm text-gray-500">
          共 {suppliers.length} 个供应商
        </div>
      </div>
    </div>
  );
};

export default SupplierPanel;
