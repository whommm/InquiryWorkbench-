import { useState } from 'react';
import { useTabsStore } from '../stores/useTabsStore';
import { toast } from 'sonner';
import ConfirmDialog from './ConfirmDialog';

interface TabBarProps {
  onHistoryClick: () => void;
  onSupplierClick: () => void;
  onRecommendClick: () => void;
}

const TabBar: React.FC<TabBarProps> = ({ onHistoryClick, onSupplierClick, onRecommendClick }) => {
  const { tabs, activeTabId, createTab, switchTab, closeTab } = useTabsStore();
  const [pendingCloseTab, setPendingCloseTab] = useState<{ id: string; name: string } | null>(null);

  const handleNewTab = async () => {
    try {
      await createTab();
    } catch (error) {
      console.error('Failed to create new tab:', error);
      toast.error('创建标签页失败');
    }
  };

  const handleCloseTab = async (tabId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const tab = tabs.find((t) => t.id === tabId);
    if (!tab) return;
    if (tab.isDirty) {
      setPendingCloseTab({ id: tab.id, name: tab.name });
      return;
    }
    await closeTab(tabId);
  };

  return (
    <>
      <div className="flex flex-col h-full">
        <div className="flex flex-col items-center py-4 gap-2">
          <button
            onClick={onHistoryClick}
            aria-label="打开历史记录"
            className="w-10 h-10 flex items-center justify-center rounded-lg text-gray-600 hover:bg-emerald-50 hover:text-emerald-600 transition-colors"
            title="历史记录"
          >
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
            </svg>
          </button>
          <button
            onClick={onSupplierClick}
            aria-label="打开供应商"
            className="w-10 h-10 flex items-center justify-center rounded-lg text-gray-600 hover:bg-emerald-50 hover:text-emerald-600 transition-colors"
            title="供应商"
          >
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
              <path strokeLinecap="round" strokeLinejoin="round" d="M18 18.72a9.094 9.094 0 0 0 3.741-.479 3 3 0 0 0-4.682-2.72m.94 3.198.001.031c0 .225-.012.447-.037.666A11.944 11.944 0 0 1 12 21c-2.17 0-4.207-.576-5.963-1.584A6.062 6.062 0 0 1 6 18.719" />
            </svg>
          </button>
          <button
            onClick={onRecommendClick}
            aria-label="打开智能推荐"
            className="w-10 h-10 flex items-center justify-center rounded-lg text-gray-600 hover:bg-emerald-50 hover:text-emerald-600 transition-colors"
            title="智能推荐"
          >
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846" />
            </svg>
          </button>
        </div>

        <div className="mx-3 border-t border-gray-200" />

        <div className="flex-1 flex flex-col items-center py-2 gap-1 overflow-y-auto">
          {tabs.map((tab, index) => (
            <button
              key={tab.id}
              onClick={() => switchTab(tab.id)}
              className={`w-10 h-10 flex items-center justify-center rounded-lg text-xs font-medium transition-colors relative group ${
                activeTabId === tab.id ? 'bg-emerald-100 text-emerald-700 border border-emerald-300' : 'text-gray-600 hover:bg-gray-100'
              }`}
              title={tab.name}
              aria-label={`切换到标签 ${index + 1}`}
            >
              {index + 1}
              {tab.isDirty && <span className="absolute -top-0.5 -right-0.5 w-2 h-2 bg-orange-500 rounded-full" />}
              <span
                onClick={(e) => void handleCloseTab(tab.id, e)}
                className="absolute -top-1 -right-1 w-4 h-4 bg-red-500 text-white rounded-full text-xs items-center justify-center hidden group-hover:flex cursor-pointer"
                aria-label="关闭标签"
              >
                ×
              </span>
            </button>
          ))}

          <button
            onClick={() => void handleNewTab()}
            aria-label="新建标签页"
            className="w-10 h-10 flex items-center justify-center rounded-lg text-gray-400 hover:bg-gray-100 hover:text-gray-600 transition-colors"
            title="新建标签页"
          >
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
            </svg>
          </button>
        </div>
      </div>

      <ConfirmDialog
        open={pendingCloseTab !== null}
        title="确认关闭标签?"
        description={pendingCloseTab ? `标签「${pendingCloseTab.name}」有未保存修改，关闭后将丢失。` : ''}
        confirmText="关闭标签"
        cancelText="取消"
        danger
        onCancel={() => setPendingCloseTab(null)}
        onConfirm={() => {
          if (pendingCloseTab) {
            void closeTab(pendingCloseTab.id);
          }
          setPendingCloseTab(null);
        }}
      />
    </>
  );
};

export default TabBar;
