import { useTabsStore } from '../stores/useTabsStore';

const TabBar = () => {
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
    <div className="flex items-center gap-1 bg-gray-100 border-b border-gray-300 px-2 py-1 overflow-x-auto">
      {tabs.map(tab => (
        <div
          key={tab.id}
          onClick={() => switchTab(tab.id)}
          className={`
            flex items-center gap-2 px-3 py-1.5 rounded-t cursor-pointer
            transition-colors duration-150 min-w-[120px] max-w-[200px]
            ${activeTabId === tab.id
              ? 'bg-white border-t-2 border-blue-500 text-gray-900'
              : 'bg-gray-200 hover:bg-gray-300 text-gray-700'
            }
          `}
        >
          <span className="truncate flex-1 text-sm">
            {tab.name}
            {tab.isDirty && <span className="text-orange-500 ml-1">*</span>}
          </span>
          <button
            onClick={(e) => handleCloseTab(tab.id, e)}
            className="text-gray-500 hover:text-red-600 hover:bg-gray-200 rounded px-1"
            title="关闭标签页"
          >
            ×
          </button>
        </div>
      ))}

      <button
        onClick={handleNewTab}
        className="px-3 py-1.5 text-gray-600 hover:bg-gray-200 rounded transition-colors"
        title="新建标签页"
      >
        +
      </button>
    </div>
  );
};

export default TabBar;
