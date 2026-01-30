import { useEffect, useState } from 'react';
import Layout from './components/Layout';
import ChatPanel from './components/ChatPanel';
import UniverSheet from './components/UniverSheet';
import TabBar from './components/TabBar';
import HistoryPanel from './components/HistoryPanel';
import SupplierPanel from './components/SupplierPanel';
import { useProcureState } from './hooks/useProcureState';
import { useTabsStore } from './stores/useTabsStore';
import { useAutoSave } from './hooks/useAutoSave';

function App() {
  const { initializeTabs, isLoading, activeTabId } = useTabsStore();
  const { sheetData, chatHistory, isThinking, handleSendMessage, handleFileUpload, handleSheetDataChange, clearChatHistory } = useProcureState();
  const [showHistory, setShowHistory] = useState(false);
  const [showSuppliers, setShowSuppliers] = useState(false);

  // Initialize tabs on mount
  useEffect(() => {
    initializeTabs();
  }, []);

  // Enable auto-save for active tab
  useAutoSave(activeTabId);

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
      </div>
      <div className="flex-1 overflow-hidden">
        <Layout
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
            <UniverSheet data={sheetData} onDataChange={handleSheetDataChange} />
          }
        />
      </div>
      {showHistory && <HistoryPanel onClose={() => setShowHistory(false)} />}
      {showSuppliers && <SupplierPanel onClose={() => setShowSuppliers(false)} />}
    </div>
  );
}

export default App;
