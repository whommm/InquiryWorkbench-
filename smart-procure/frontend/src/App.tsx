import { useEffect, useState } from 'react';
import Layout from './components/Layout';
import ChatPanel from './components/ChatPanel';
import UniverSheet from './components/UniverSheet';
import TabBar from './components/TabBar';
import HistoryPanel from './components/HistoryPanel';
import SupplierPanel from './components/SupplierPanel';
import { RecommendPanel } from './components/RecommendPanel';
import { Toast } from './components/Toast';
import { useProcureState } from './hooks/useProcureState';
import { useTabsStore } from './stores/useTabsStore';
import { useAuthStore } from './stores/useAuthStore';
import { useAutoSave } from './hooks/useAutoSave';
import { AUTH_EXPIRED_EVENT } from './utils/api';
import AuthPage from './pages/AuthPage';

import { Toaster } from 'sonner';

function App() {
  const { initializeTabs, isLoading, activeTabId, clearTabs } = useTabsStore();
  const {
    sheetData,
    chatHistory,
    isThinking,
    isDirty,
    toolConfigs,
    handleSendMessage,
    handleFileUpload,
    handleSheetDataChange,
    clearChatHistory,
    handleToolToggle,
    handleManualSave,
  } = useProcureState();
  const { isAuthenticated, isLoading: authLoading, loadFromStorage, logout, user } = useAuthStore();
  const [showHistory, setShowHistory] = useState(false);
  const [showSuppliers, setShowSuppliers] = useState(false);
  const [showRecommend, setShowRecommend] = useState(false);
  const [selectedRow, setSelectedRow] = useState<number | null>(null);
  const [showChat, setShowChat] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'info' | 'error' } | null>(null);

  const onSave = async () => {
    setIsSaving(true);
    try {
      const result = await handleManualSave();
      if (!result.success) {
        setToast({ message: '淇濆瓨澶辫触', type: 'error' });
      }
    } finally {
      setIsSaving(false);
    }
  };

  useEffect(() => {
    loadFromStorage();
  }, [loadFromStorage]);

  useEffect(() => {
    const handleAuthExpired = () => {
      setToast({ message: '登录已过期，请重新登录', type: 'error' });
      setTimeout(() => {
        logout();
        clearTabs();
      }, 1500);
    };
    window.addEventListener(AUTH_EXPIRED_EVENT, handleAuthExpired);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, handleAuthExpired);
  }, [logout, clearTabs]);

  useEffect(() => {
    if (isAuthenticated && user) {
      void initializeTabs(user.id);
    }
  }, [isAuthenticated, user, initializeTabs]);

  useAutoSave(activeTabId);

  const handleRowClick = (rowIndex: number) => {
    setSelectedRow(rowIndex);
  };

  if (!isAuthenticated) {
    if (authLoading) {
      return (
        <div className="h-screen w-screen flex items-center justify-center bg-gray-50">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-emerald-600"></div>
        </div>
      );
    }
    return (
      <>
        <Toaster position="top-center" richColors />
        <AuthPage />
      </>
    );
  }

  if (isLoading) {
    return (
      <div className="h-screen w-screen flex items-center justify-center bg-gray-50">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-emerald-600"></div>
      </div>
    );
  }

  return (
    <Layout
      showChat={showChat}
      onToggleChat={() => setShowChat(!showChat)}
      showRightPanel={showRecommend}
      sidebarContent={
        <div className="w-16 flex-shrink-0 flex flex-col h-full bg-gray-50 border-r border-gray-200">
          <TabBar
            onHistoryClick={() => setShowHistory(true)}
            onSupplierClick={() => setShowSuppliers(true)}
            onRecommendClick={() => setShowRecommend(!showRecommend)}
          />
        </div>
      }
      mainContent={
        <div className="h-full relative flex flex-col bg-white">
          <UniverSheet
            data={sheetData}
            onChange={handleSheetDataChange}
            onRowClick={handleRowClick}
            isDirty={isDirty}
            onSave={onSave}
            isSaving={isSaving}
          />
          {toast && (
            <Toast
              message={toast.message}
              type={toast.type}
              onClose={() => setToast(null)}
            />
          )}
          <Toaster position="top-center" richColors />
        </div>
      }
      chatPanel={
        <ChatPanel
          messages={chatHistory}
          onSendMessage={handleSendMessage}
          isThinking={isThinking}
          onFileUpload={handleFileUpload}
          onClearHistory={clearChatHistory}
          toolConfigs={toolConfigs}
          onToolToggle={handleToolToggle}
        />
      }
      rightPanel={
        <RecommendPanel
          isOpen={showRecommend}
          onClose={() => setShowRecommend(false)}
          activeTabId={activeTabId}
          selectedRow={selectedRow}
          sheetData={sheetData}
        />
      }
    >
      <HistoryPanel
        isOpen={showHistory}
        onClose={() => setShowHistory(false)}
        onClearHistory={clearChatHistory}
      />
      <SupplierPanel
        isOpen={showSuppliers}
        onClose={() => setShowSuppliers(false)}
        selectedRow={selectedRow}
      />
    </Layout>
  );
}

export default App;

