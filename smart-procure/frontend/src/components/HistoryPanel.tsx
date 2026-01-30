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
  onClose: () => void;
}

const HistoryPanel = ({ onClose }: HistoryPanelProps) => {
  const [sheets, setSheets] = useState<SheetListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const { createTab } = useTabsStore();

  useEffect(() => {
    loadSheets();
  }, []);

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

      // Create new tab with loaded data directly (avoid race condition)
      await createTab(sheet.name, {
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

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-[800px] max-h-[600px] flex flex-col">
        {/* Header */}
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
          <h2 className="text-xl font-semibold text-gray-900">历史询价单</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-2xl"
          >
            ×
          </button>
        </div>

        {/* Search */}
        <div className="px-6 py-3 border-b border-gray-200">
          <input
            type="text"
            placeholder="搜索询价单..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
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
                        <div>完成率: {(sheet.completion_rate * 100).toFixed(1)}%</div>
                        <div>更新时间: {new Date(sheet.updated_at).toLocaleString('zh-CN')}</div>
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
