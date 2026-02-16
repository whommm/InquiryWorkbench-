import { useTabsStore } from '../stores/useTabsStore';

interface TabBarProps {
  onHistoryClick: () => void;
  onSupplierClick: () => void;
  onRecommendClick: () => void;
}

const TabBar: React.FC<TabBarProps> = ({ onHistoryClick, onSupplierClick, onRecommendClick }) => {
  const { tabs, activeTabId, createTab, switchTab, closeTab } = useTabsStore();

  const handleNewTab = async () => {
    try {
      await createTab();
    } catch (error) {
      console.error('Failed to create new tab:', error);
      alert('创建标签页失败');
    }
  };

  const handleCloseTab = async (tabId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    await closeTab(tabId);
  };

  return (
    <div className="flex flex-col h-full">
      {/* 侧边栏导航按钮 */}
      <div className="flex flex-col items-center py-4 gap-2">
        <button
          onClick={onHistoryClick}
          className="w-10 h-10 flex items-center justify-center rounded-lg text-gray-600 hover:bg-emerald-50 hover:text-emerald-600 transition-colors"
          title="历史记录"
        >
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
          </svg>
        </button>
        <button
          onClick={onSupplierClick}
          className="w-10 h-10 flex items-center justify-center rounded-lg text-gray-600 hover:bg-emerald-50 hover:text-emerald-600 transition-colors"
          title="供应商"
        >
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
            <path strokeLinecap="round" strokeLinejoin="round" d="M18 18.72a9.094 9.094 0 0 0 3.741-.479 3 3 0 0 0-4.682-2.72m.94 3.198.001.031c0 .225-.012.447-.037.666A11.944 11.944 0 0 1 12 21c-2.17 0-4.207-.576-5.963-1.584A6.062 6.062 0 0 1 6 18.719m12 0a5.971 5.971 0 0 0-.941-3.197m0 0A5.995 5.995 0 0 0 12 12.75a5.995 5.995 0 0 0-5.058 2.772m0 0a3 3 0 0 0-4.681 2.72 8.986 8.986 0 0 0 3.74.477m.94-3.197a5.971 5.971 0 0 0-.94 3.197M15 6.75a3 3 0 1 1-6 0 3 3 0 0 1 6 0Zm6 3a2.25 2.25 0 1 1-4.5 0 2.25 2.25 0 0 1 4.5 0Zm-13.5 0a2.25 2.25 0 1 1-4.5 0 2.25 2.25 0 0 1 4.5 0Z" />
          </svg>
        </button>
        <button
          onClick={onRecommendClick}
          className="w-10 h-10 flex items-center justify-center rounded-lg text-gray-600 hover:bg-emerald-50 hover:text-emerald-600 transition-colors"
          title="智能推荐"
        >
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
            <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 0 0-2.456 2.456Z" />
          </svg>
        </button>
      </div>

      {/* 分隔线 */}
      <div className="mx-3 border-t border-gray-200"></div>

      {/* Excel 标签页列表 */}
      <div className="flex-1 flex flex-col items-center py-2 gap-1 overflow-y-auto">
        {tabs.map((tab, index) => (
          <button
            key={tab.id}
            onClick={() => switchTab(tab.id)}
            className={`
              w-10 h-10 flex items-center justify-center rounded-lg text-xs font-medium transition-colors relative group
              ${activeTabId === tab.id
                ? 'bg-emerald-100 text-emerald-700 border border-emerald-300'
                : 'text-gray-600 hover:bg-gray-100'
              }
            `}
            title={tab.name}
          >
            {index + 1}
            {tab.isDirty && (
              <span className="absolute -top-0.5 -right-0.5 w-2 h-2 bg-orange-500 rounded-full"></span>
            )}
            {/* 关闭按钮 - hover时显示 */}
            <span
              onClick={(e) => handleCloseTab(tab.id, e)}
              className="absolute -top-1 -right-1 w-4 h-4 bg-red-500 text-white rounded-full text-[10px] items-center justify-center hidden group-hover:flex cursor-pointer"
            >
              ×
            </span>
          </button>
        ))}

        {/* 新建标签按钮 */}
        <button
          onClick={handleNewTab}
          className="w-10 h-10 flex items-center justify-center rounded-lg text-gray-400 hover:bg-gray-100 hover:text-gray-600 transition-colors"
          title="新建标签页"
        >
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
        </button>
      </div>
    </div>
  );
};

export default TabBar;
