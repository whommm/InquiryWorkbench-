import { useState, useEffect } from 'react';
import { listSheets, getSheet, deleteSheet, exportSheet } from '../utils/api';
import { useTabsStore } from '../stores/useTabsStore';

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
  onRestoreHistory?: (history: any) => void;
  onClearHistory?: () => Promise<void>;
}

const HistoryPanel = ({ 
  isOpen,
  onClose,
  onRestoreHistory,
  onClearHistory
}: HistoryPanelProps) => {
  const [sheets, setSheets] = useState<SheetListItem[]>([]);

  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const { createTab } = useTabsStore();

  useEffect(() => {
    if (isOpen) {
      loadSheets();
    }
  }, [isOpen]);

  const loadSheets = async () => {
    try {
      setLoading(true);
      const response = await listSheets();
      setSheets(response.sheets || []);
    } catch (error) {
      console.error('Failed to load sheets:', error);
      alert('加载历史记录失败');
    } finally {
      setLoading(false);
    }
  };

  const handleLoadSheet = async (sheetId: string) => {
    try {
      const sheet = await getSheet(sheetId);

      // Create new tab with loaded data, preserving the original ID
      await createTab(sheet.name, {
        id: sheet.id,  // 保留原始ID，这样保存时会更新而不是创建新记录
        sheetData: sheet.sheet_data,
        chatHistory: sheet.chat_history,
        isDirty: false,
      });

      onClose();
    } catch (error) {
      console.error('Failed to load sheet:', error);
      alert('加载询价单失败');
    }
  };

  const handleDeleteSheet = async (sheetId: string, sheetName: string) => {
    if (!confirm(`确定要删除询价单 "${sheetName}" 吗？`)) {
      return;
    }

    try {
      await deleteSheet(sheetId);
      await loadSheets(); // Reload list
    } catch (error) {
      console.error('Failed to delete sheet:', error);
      alert('删除失败');
    }
  };

  const handleExportSheet = async (sheetId: string, sheetName: string) => {
    try {
      const blob = await exportSheet(sheetId);

      // Create download link
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${sheetName}.xlsx`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Failed to export sheet:', error);
      alert('导出失败');
    }
  };

  const filteredSheets = sheets.filter(sheet =>
    sheet.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-2xl w-[800px] max-h-[600px] flex flex-col border border-gray-100 overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between bg-gray-50/50">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-emerald-100 text-emerald-600 rounded-lg">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900">历史询价单</h2>
              <p className="text-xs text-gray-500">查看和管理您之前的询价记录</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-full transition-colors"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Search */}
        <div className="px-6 py-4 border-b border-gray-100 flex gap-3 bg-white">
          <div className="relative flex-1">
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
              onClick={async () => {
                if (confirm('确定要清空所有历史记录吗？此操作不可恢复。')) {
                   await onClearHistory();
                   loadSheets();
                }
              }}
              className="px-4 py-2 text-sm text-red-600 hover:bg-red-50 border border-red-200 rounded-lg transition-colors flex items-center gap-2"
             >
               <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                 <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
               </svg>
               清空记录
             </button>
          )}
        </div>

        {/* List */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {loading ? (
            <div className="text-center text-gray-500 py-8">加载中...</div>
          ) : filteredSheets.length === 0 ? (
            <div className="text-center text-gray-500 py-8">
              {searchQuery ? '没有找到匹配的询价单' : '暂无历史记录'}
            </div>
          ) : (
            <div className="space-y-3">
              {filteredSheets.map((sheet) => (
                <div
                  key={sheet.id}
                  className="border border-gray-200 rounded-lg p-4 hover:bg-gray-50 transition-colors"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <h3 className="font-medium text-gray-900">{sheet.name}</h3>
                      <div className="mt-1 text-sm text-gray-500 space-y-1">
                        <div>物料数量: {sheet.item_count} 项</div>
                        <div>更新时间: {new Date(sheet.updated_at).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })}</div>
                      </div>
                    </div>
                    <div className="flex gap-2 ml-4">
                      <button
                        onClick={() => handleLoadSheet(sheet.id)}
                        className="px-3 py-1 text-sm bg-blue-500 text-white rounded hover:bg-blue-600"
                      >
                        加载
                      </button>
                      <button
                        onClick={() => handleExportSheet(sheet.id, sheet.name)}
                        className="px-3 py-1 text-sm bg-green-500 text-white rounded hover:bg-green-600"
                      >
                        导出
                      </button>
                      <button
                        onClick={() => handleDeleteSheet(sheet.id, sheet.name)}
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
          共 {filteredSheets.length} 条记录
        </div>
      </div>
    </div>
  );
};

export default HistoryPanel;
