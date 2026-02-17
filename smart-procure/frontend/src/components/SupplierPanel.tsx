import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { listSuppliers, searchSuppliers, deleteSupplier } from '../utils/api';
import ConfirmDialog from './ConfirmDialog';

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
  isOpen: boolean;
  onClose: () => void;
  selectedRow?: number | null;
}

const SupplierPanel = ({ isOpen, onClose }: SupplierPanelProps) => {
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [isSearching, setIsSearching] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<{ id: number; name: string } | null>(null);

  useEffect(() => {
    if (isOpen) {
      void loadSuppliers();
    }
  }, [isOpen]);

  const loadSuppliers = async () => {
    try {
      setLoading(true);
      const response = await listSuppliers();
      setSuppliers(response.suppliers || []);
    } catch (error) {
      console.error('Failed to load suppliers:', error);
      toast.error('加载供应商列表失败');
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = async () => {
    if (!searchQuery.trim()) {
      await loadSuppliers();
      return;
    }

    try {
      setIsSearching(true);
      const response = await searchSuppliers(searchQuery.trim());
      setSuppliers(response.suppliers || []);
    } catch (error) {
      console.error('Failed to search suppliers:', error);
      toast.error('搜索失败');
    } finally {
      setIsSearching(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deleteSupplier(deleteTarget.id);
      toast.success(`已删除: ${deleteTarget.name}`);
      await loadSuppliers();
    } catch (error) {
      console.error('Failed to delete supplier:', error);
      toast.error('删除失败');
    } finally {
      setDeleteTarget(null);
    }
  };

  if (!isOpen) return null;

  return (
    <>
      <div className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50 p-4">
        <div className="modal-shell w-[min(92vw,800px)] max-h-[85vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200">
          <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between bg-gray-50/50">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-emerald-100 text-emerald-600 rounded-lg">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857" />
                </svg>
              </div>
              <div>
                <h2 className="text-lg font-semibold text-gray-900">供应商管理</h2>
                <p className="text-xs text-gray-500">管理供应商数据与历史报价</p>
              </div>
            </div>
            <button
              onClick={onClose}
              aria-label="关闭供应商弹窗"
              className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-full transition-colors"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          <div className="px-6 py-4 border-b border-gray-100 flex flex-wrap gap-3 bg-white">
            <div className="relative flex-1 min-w-[220px]">
              <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
              <input
                type="text"
                placeholder="搜索供应商（公司名、联系人、电话）..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && void handleSearch()}
                className="w-full pl-9 pr-4 py-2 bg-gray-50 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500 transition-all text-sm"
              />
            </div>
            <button
              onClick={() => void handleSearch()}
              disabled={isSearching}
              className="px-4 py-2 text-sm btn-primary rounded-lg disabled:bg-gray-400"
            >
              {isSearching ? '搜索中...' : '搜索'}
            </button>
            <button
              onClick={() => void loadSuppliers()}
              className="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 border border-gray-200 rounded-lg transition-colors"
            >
              重置
            </button>
          </div>

          <div className="flex-1 overflow-y-auto px-6 py-4">
            {loading ? (
              <div className="text-center text-gray-500 py-8">加载中...</div>
            ) : suppliers.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-gray-500">
                <div className="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mb-4">
                  <svg className="w-8 h-8 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
                  </svg>
                </div>
                <p className="font-medium text-gray-700 mb-1">{searchQuery ? '没有找到匹配的供应商' : '暂无供应商数据'}</p>
                <p className="text-sm text-gray-400">{searchQuery ? '请尝试其他关键词' : '通过 AI 助手录入报价后将自动添加供应商'}</p>
              </div>
            ) : (
              <div className="space-y-3">
                {suppliers.map((supplier) => (
                  <div key={supplier.id} className="border border-gray-200 rounded-lg p-4 hover:bg-gray-50 transition-colors">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <h3 className="font-medium text-gray-900">{supplier.company_name}</h3>
                        <div className="mt-1 text-sm text-gray-500 space-y-1">
                          <div className="flex gap-4 flex-wrap">
                            <span>联系人: {supplier.contact_name || '未填写'}</span>
                            <span>电话: {supplier.contact_phone}</span>
                          </div>
                          <div className="flex gap-4 flex-wrap">
                            <span>报价次数: {supplier.quote_count} 次</span>
                            <span>
                              最后报价: {supplier.last_quote_date ? new Date(supplier.last_quote_date).toLocaleDateString('zh-CN') : '无'}
                            </span>
                          </div>
                          {supplier.tags && supplier.tags.length > 0 && (
                            <div className="flex gap-1 flex-wrap mt-1">
                              {supplier.tags.map((tag, idx) => (
                                <span key={idx} className="px-2 py-0.5 bg-emerald-100 text-emerald-700 rounded text-xs">
                                  {tag}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                      <div className="flex gap-2 ml-2 shrink-0">
                        <button
                          onClick={() => setDeleteTarget({ id: supplier.id, name: supplier.company_name })}
                          className="px-3 py-1 text-sm btn-danger rounded"
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

          <div className="px-6 py-3 border-t border-gray-200 text-sm text-gray-500">共 {suppliers.length} 个供应商</div>
        </div>
      </div>

      <ConfirmDialog
        open={deleteTarget !== null}
        title="确认删除供应商?"
        description={deleteTarget ? `将删除「${deleteTarget.name}」，该操作不可恢复。` : ''}
        confirmText="删除"
        cancelText="取消"
        danger
        onCancel={() => setDeleteTarget(null)}
        onConfirm={() => void handleDelete()}
      />
    </>
  );
};

export default SupplierPanel;

