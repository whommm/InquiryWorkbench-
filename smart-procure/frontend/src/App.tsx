import { useEffect, useState } from 'react';
import Layout from './components/Layout';
import ChatPanel from './components/ChatPanel';
import UniverSheet from './components/UniverSheet';
import TabBar from './components/TabBar';
import HistoryPanel from './components/HistoryPanel';
import SupplierPanel from './components/SupplierPanel';
import { RecommendPanel } from './components/RecommendPanel';
import { useProcureState } from './hooks/useProcureState';
import { useTabsStore } from './stores/useTabsStore';
import { useAuthStore } from './stores/useAuthStore';
import { useAutoSave } from './hooks/useAutoSave';
import AuthPage from './pages/AuthPage';

function App() {
  const { initializeTabs, isLoading, activeTabId, clearTabs } = useTabsStore();
  const { sheetData, chatHistory, isThinking, handleSendMessage, handleFileUpload, handleSheetDataChange, clearChatHistory } = useProcureState();
  const { isAuthenticated, isLoading: authLoading, loadFromStorage, logout, user } = useAuthStore();
  const [showHistory, setShowHistory] = useState(false);
  const [showSuppliers, setShowSuppliers] = useState(false);
  const [showRecommend, setShowRecommend] = useState(false);
  const [selectedRow, setSelectedRow] = useState<number | null>(null);
  const [showChat, setShowChat] = useState(true);

  // Initialize tabs on mount
  useEffect(() => {
    loadFromStorage();
  }, []);

  // Initialize tabs after authentication
  useEffect(() => {
    if (isAuthenticated && user) {
      initializeTabs(user.id);
    }
  }, [isAuthenticated, user]);

  // Enable auto-save for active tab
  useAutoSave(activeTabId);

  // Handle row click from UniverSheet
  const handleRowClick = (rowIndex: number) => {
    console.log('[App] handleRowClick called with rowIndex:', rowIndex);
    setSelectedRow(rowIndex);
  };

  if (authLoading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-gray-600">加载中...</div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <AuthPage />;
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-gray-600">加载中...</div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen">
      <div className="flex items-center gap-2 bg-gray-100 border-b border-gray-300 px-2 py-1">
        <TabBar />
        <button
          onClick={() => setShowHistory(true)}
          className="px-3 py-1.5 text-sm bg-blue-500 text-white rounded hover:bg-blue-600 transition-colors whitespace-nowrap"
          title="查看历史记录"
        >
          历史记录
        </button>
        <button
          onClick={() => setShowSuppliers(true)}
          className="px-3 py-1.5 text-sm bg-green-500 text-white rounded hover:bg-green-600 transition-colors whitespace-nowrap"
          title="供应商管理"
        >
          供应商
        </button>
        <button
          onClick={() => setShowRecommend(!showRecommend)}
          className={`px-3 py-1.5 text-sm rounded transition-colors whitespace-nowrap ${
            showRecommend
              ? 'bg-purple-600 text-white hover:bg-purple-700'
              : 'bg-purple-500 text-white hover:bg-purple-600'
          }`}
          title="供应商推荐"
        >
          {showRecommend ? '隐藏推荐' : '显示推荐'}
        </button>
        <div className="flex-1" />
        <span className="text-sm text-gray-600">
          {user?.display_name || user?.username}
        </span>
        <button
          onClick={() => { clearTabs(); logout(); }}
          className="px-3 py-1.5 text-sm bg-gray-500 text-white rounded hover:bg-gray-600 transition-colors whitespace-nowrap"
        >
          退出
        </button>
      </div>
      <div className="flex-1 overflow-hidden">
        <Layout
          collapsed={!showChat}
          onToggleCollapse={() => setShowChat(!showChat)}
          left={
            <ChatPanel
              history={chatHistory}
              onSend={handleSendMessage}
              onFileUpload={handleFileUpload}
              isThinking={isThinking}
              onClear={clearChatHistory}
            />
          }
          right={
            <div className="h-full flex">
              <div className="flex-1 min-w-0">
                <UniverSheet
                  data={sheetData}
                  onDataChange={handleSheetDataChange}
                  onRowClick={handleRowClick}
                />
              </div>
              {showRecommend && (
                <div className="w-80 border-l border-gray-200 bg-white">
                  <RecommendPanel
                    selectedRow={selectedRow}
                    sheetData={sheetData}
                  />
                </div>
              )}
            </div>
          }
        />
      </div>
      {showHistory && <HistoryPanel onClose={() => setShowHistory(false)} />}
      {showSuppliers && <SupplierPanel onClose={() => setShowSuppliers(false)} />}
    </div>
  );
}

export default App;
