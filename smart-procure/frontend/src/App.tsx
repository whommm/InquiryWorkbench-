import { useEffect, useState, useCallback, useRef } from 'react';
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
import { getNotifications, AUTH_EXPIRED_EVENT } from './utils/api';
import AuthPage from './pages/AuthPage';

import { Toaster } from 'sonner';

function App() {
  const { initializeTabs, isLoading, activeTabId, clearTabs } = useTabsStore();
  const { sheetData, chatHistory, isThinking, isDirty, toolConfigs, handleSendMessage, handleFileUpload, handleSheetDataChange, clearChatHistory, handleToolToggle, handleManualSave } = useProcureState();
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
        setToast({ message: '保存失败', type: 'error' });
      }
      // 保存成功不显示Toast，等后台任务完成后通过轮询显示
    } finally {
      setIsSaving(false);
    }
  };

  // 使用 ref 存储认证状态，避免 useCallback 依赖变化
  const isAuthenticatedRef = useRef(isAuthenticated);
  useEffect(() => {
    isAuthenticatedRef.current = isAuthenticated;
  }, [isAuthenticated]);

  // 轮询通知
  const checkNotifications = useCallback(async () => {
    if (!isAuthenticatedRef.current) return;
    try {
      const result = await getNotifications();
      if (result.notifications && result.notifications.length > 0) {
        const notification = result.notifications[0];
        setToast({ message: notification.message, type: notification.type });
      }
    } catch (e) {
      // 忽略错误
    }
  }, []);

  useEffect(() => {
    if (!isAuthenticated) return;
    const interval = setInterval(checkNotifications, 3000);
    return () => clearInterval(interval);
  }, [isAuthenticated, checkNotifications]);

  // Initialize tabs on mount
  useEffect(() => {
    loadFromStorage();
  }, []);

  // 监听认证过期事件
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
      onToggleRightPanel={() => setShowRecommend(!showRecommend)}
      rightPanel={
        <RecommendPanel
          isOpen={showRecommend}
          onClose={() => setShowRecommend(false)}
          selectedRow={selectedRow}
          sheetData={sheetData}
        />
      }
      sidebarContent={
        <div className="flex flex-col h-full bg-gray-50 border-r border-gray-200">
          <TabBar 
            onHistoryClick={() => setShowHistory(true)} 
            onSupplierClick={() => setShowSuppliers(true)}
            onRecommendClick={() => setShowRecommend(true)}
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
          toolConfigs={toolConfigs}
          onToolToggle={handleToolToggle}
          onClearHistory={clearChatHistory}
          onCollapse={() => setShowChat(false)}
        />
      }
    >
      <HistoryPanel 
        isOpen={showHistory} 
        onClose={() => setShowHistory(false)}
        onRestoreHistory={(history) => {
          // TODO: implement history restore
          console.log('Restore history:', history);
          setShowHistory(false);
        }}
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
