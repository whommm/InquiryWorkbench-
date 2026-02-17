import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { listSheets, getSheet, deleteSheet, exportSheet } from '../utils/api';
import { useTabsStore } from '../stores/useTabsStore';
import ConfirmDialog from './ConfirmDialog';

interface SheetListItem {
  id: string;
  name: string;
  item_count: number;
  completion_rate: number;
  created_at: string;
  updated_at: string;
}

interface HistoryPanelProps {
  isOpen: boolean;
  onClose: () => void;
  onClearHistory?: () => Promise<void>;
}

const HistoryPanel = ({ isOpen, onClose, onClearHistory }: HistoryPanelProps) => {
  const [sheets, setSheets] = useState<SheetListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; name: string } | null>(null);
  const [clearConfirmOpen, setClearConfirmOpen] = useState(false);

  const { createTab } = useTabsStore();

  useEffect(() => {
    if (isOpen) {
      void loadSheets();
    }
  }, [isOpen]);

  const loadSheets = async () => {
    try {
      setLoading(true);
      const response = await listSheets();
      setSheets(response.sheets || []);
    } catch (error) {
      console.error('Failed to load sheets:', error);
      toast.error('加载历史记录失败');
    } finally {
      setLoading(false);
    }
  };

  const handleLoadSheet = async (sheetId: string) => {
    try {
      const sheet = await getSheet(sheetId);
      await createTab(sheet.name, {
        id: sheet.id,
        sheetData: sheet.sheet_data,
        chatHistory: sheet.chat_history,
        isDirty: false,
        serverUpdatedAt: sheet.updated_at || null,
      });
      onClose();
      toast.success('询价单已加载到新标签页');
    } catch (error) {
      console.error('Failed to load sheet:', error);
      toast.error('加载询价单失败');
    }
  };

  const confirmDeleteSheet = async () => {
    if (!deleteTarget) return;
    try {
      await deleteSheet(deleteTarget.id);
      toast.success(`已删除: ${deleteTarget.name}`);
      await loadSheets();
    } catch (error) {
      console.error('Failed to delete sheet:', error);
      toast.error('删除失败');
    } finally {
      setDeleteTarget(null);
    }
  };

  const handleExportSheet = async (sheetId: string, sheetName: string) => {
    try {
      const blob = await exportSheet(sheetId);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${sheetName}.xlsx`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
      toast.success('导出成功');
    } catch (error) {
      console.error('Failed to export sheet:', error);
      toast.error('导出失败');
    }
  };

  const filteredSheets = sheets.filter((sheet) =>
    sheet.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  if (!isOpen) return null;

  return (
    <>
      <div className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50 p-4">
        <div className="modal-shell w-[min(92vw,800px)] max-h-[85vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200">
          <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between bg-gray-50/50">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-emerald-100 text-emerald-600 rounded-lg">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <div>
                <h2 className="text-lg font-semibold text-gray-900">历史询价单</h2>
                <p className="text-xs text-gray-500">查看并管理之前保存的询价记录</p>
              </div>
            </div>
            <button
              onClick={onClose}
              aria-label="关闭历史询价单弹窗"
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
                placeholder="搜索询价单..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-9 pr-4 py-2 bg-gray-50 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500 transition-all text-sm"
              />
            </div>
            {onClearHistory && (
              <button
                onClick={() => setClearConfirmOpen(true)}
                className="px-4 py-2 text-sm text-red-600 hover:bg-red-50 border border-red-200 rounded-lg transition-colors flex items-center gap-2"
              >
                清空记录
              </button>
            )}
          </div>

          <div className="flex-1 overflow-y-auto px-6 py-4">
            {loading ? (
              <div className="text-center text-gray-500 py-8">加载中...</div>
            ) : filteredSheets.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-gray-500">
                <div className="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mb-4">
                  <svg className="w-8 h-8 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                </div>
                <p className="font-medium text-gray-700 mb-1">{searchQuery ? '没有找到匹配的询价单' : '暂无历史记录'}</p>
                <p className="text-sm text-gray-400">{searchQuery ? '请尝试其他关键词' : '创建新的询价单后将显示在这里'}</p>
              </div>
            ) : (
              <div className="space-y-3">
                {filteredSheets.map((sheet) => (
                  <div key={sheet.id} className="border border-gray-200 rounded-lg p-4 hover:bg-gray-50 transition-colors">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <h3 className="font-medium text-gray-900 truncate">{sheet.name}</h3>
                        <div className="mt-1 text-sm text-gray-500 space-y-1">
                          <div>物料数量: {sheet.item_count} 项</div>
                          <div>更新时间: {new Date(sheet.updated_at).toLocaleString('zh-CN')}</div>
                        </div>
                      </div>
                      <div className="flex gap-2 ml-2 shrink-0">
                        <button onClick={() => void handleLoadSheet(sheet.id)} className="px-3 py-1 text-sm btn-primary rounded">
                          加载
                        </button>
                        <button
                          onClick={() => void handleExportSheet(sheet.id, sheet.name)}
                          className="px-3 py-1 text-sm text-emerald-700 border border-emerald-200 bg-emerald-50 rounded hover:bg-emerald-100"
                        >
                          导出
                        </button>
                        <button
                          onClick={() => setDeleteTarget({ id: sheet.id, name: sheet.name })}
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

          <div className="px-6 py-3 border-t border-gray-200 text-sm text-gray-500">共 {filteredSheets.length} 条记录</div>
        </div>
      </div>

      <ConfirmDialog
        open={deleteTarget !== null}
        title="确认删除询价单?"
        description={deleteTarget ? `将永久删除「${deleteTarget.name}」，该操作不可恢复。` : ''}
        confirmText="删除"
        cancelText="取消"
        danger
        onCancel={() => setDeleteTarget(null)}
        onConfirm={() => void confirmDeleteSheet()}
      />

      <ConfirmDialog
        open={clearConfirmOpen}
        title="确认清空历史记录?"
        description="将清空当前会话历史，操作不可恢复。"
        confirmText="确认清空"
        cancelText="取消"
        danger
        onCancel={() => setClearConfirmOpen(false)}
        onConfirm={() => {
          setClearConfirmOpen(false);
          void onClearHistory?.();
          void loadSheets();
        }}
      />
    </>
  );
};

export default HistoryPanel;

