import React, { useState, useEffect, useRef } from 'react';
import { useAuthStore } from '../stores/useAuthStore';
import { useTabsStore } from '../stores/useTabsStore';
import { toast } from 'sonner';

interface HeaderProps {
  onToggleSidebar?: () => void;
}

const Header: React.FC<HeaderProps> = ({ onToggleSidebar }) => {
  const { user, logout } = useAuthStore();
  const { tabs, activeTabId, updateTab, isLoading } = useTabsStore();
  const [showNotifications, setShowNotifications] = useState(false);
  const notificationRef = useRef<HTMLDivElement>(null);
  
  const activeTab = tabs.find(t => t.id === activeTabId);

  // Mock notifications
  const notifications = [
    { id: 1, title: '系统更新', message: 'SmartProcure 已升级至 v1.2.0', time: '10分钟前', read: false, type: 'info' },
    { id: 2, title: '新供应商', message: '已成功导入 5 家供应商数据', time: '1小时前', read: false, type: 'success' },
    { id: 3, title: '自动保存', message: '询价单草稿已自动保存', time: '2小时前', read: true, type: 'info' },
  ];

  const unreadCount = notifications.filter(n => !n.read).length;

  // Close notifications when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (notificationRef.current && !notificationRef.current.contains(event.target as Node)) {
        setShowNotifications(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

  const handleTitleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (activeTab) {
      updateTab(activeTab.id, { name: e.target.value, isDirty: true });
    }
  };


  const handleDownload = () => {
    if (!activeTab) {
      toast.error('当前没有活动的表格可导出');
      return;
    }
    
    // Simulate export process
    toast.promise(
      new Promise((resolve) => setTimeout(resolve, 1500)),
      {
        loading: '正在生成 Excel 报表...',
        success: '报表已成功导出',
        error: '导出失败',
      }
    );
  };

  return (
    <header className="h-14 bg-white border-b border-gray-200 flex items-center justify-between px-4 shadow-sm z-20 relative">
      {/* Left: Logo & Sidebar Toggle */}
      <div className="flex items-center gap-4">
        <button 
          onClick={onToggleSidebar}
          className="p-1.5 text-gray-500 hover:bg-gray-100 rounded-md transition-colors lg:hidden"
        >
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>
        
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-emerald-600 rounded-lg flex items-center justify-center text-white font-bold text-xl shadow-sm">
            S
          </div>
          <span className="font-bold text-gray-800 text-lg tracking-tight hidden sm:block">
            SmartProcure
          </span>
        </div>
      </div>

      {/* Middle: Title & Status */}
      <div className="flex-1 max-w-2xl mx-4 flex items-center justify-center">
        {isLoading ? (
          <div className="h-8 w-48 bg-gray-100 rounded animate-pulse" />
        ) : activeTab ? (
          <div className="group flex items-center gap-2 px-3 py-1.5 rounded-md hover:bg-gray-50 transition-colors cursor-text max-w-full">
            <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <input
              type="text"
              value={activeTab.name}
              onChange={handleTitleChange}
              className="bg-transparent border-none focus:ring-0 text-gray-700 font-medium text-sm w-full text-center p-0 placeholder-gray-400"
              placeholder="未命名询价单"
            />
            <div className="w-2 h-2 rounded-full bg-emerald-500 ml-2" title="已自动保存" />
          </div>
        ) : (
          <span className="text-gray-400 text-sm italic">无活动表格</span>
        )}
      </div>

      {/* Right: Actions & Profile */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1 border-r border-gray-200 pr-3 mr-1">
          <button 
            onClick={handleDownload}
            className="p-2 text-gray-500 hover:text-emerald-600 hover:bg-gray-100 rounded-full transition-colors" 
            title="导出 Excel"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
          </button>
          
          <div className="relative" ref={notificationRef}>
            <button 
              onClick={() => setShowNotifications(!showNotifications)}
              className={`p-2 rounded-full transition-colors ${showNotifications ? 'bg-gray-100 text-emerald-600' : 'text-gray-500 hover:text-emerald-600 hover:bg-gray-100'}`} 
              title="通知"
            >
              <div className="relative">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
                </svg>
                {unreadCount > 0 && (
                  <span className="absolute -top-0.5 -right-0.5 block h-2.5 w-2.5 rounded-full bg-red-500 ring-2 ring-white" />
                )}
              </div>
            </button>

            {/* Notification Dropdown */}
            {showNotifications && (
              <div className="absolute right-0 top-full mt-2 w-80 bg-white rounded-xl shadow-lg border border-gray-100 py-2 z-50 animate-in fade-in slide-in-from-top-2 duration-200">
                <div className="px-4 py-2 border-b border-gray-50 flex justify-between items-center">
                  <h3 className="font-semibold text-gray-800">通知中心</h3>
                  <span className="text-xs text-emerald-600 cursor-pointer hover:underline">全部已读</span>
                </div>
                <div className="max-h-[300px] overflow-y-auto">
                  {notifications.map((n) => (
                    <div key={n.id} className={`px-4 py-3 hover:bg-gray-50 transition-colors border-b border-gray-50 last:border-0 ${!n.read ? 'bg-blue-50/30' : ''}`}>
                      <div className="flex justify-between items-start mb-1">
                        <span className={`text-sm font-medium ${!n.read ? 'text-gray-900' : 'text-gray-600'}`}>{n.title}</span>
                        <span className="text-xs text-gray-400">{n.time}</span>
                      </div>
                      <p className="text-sm text-gray-500 line-clamp-2">{n.message}</p>
                    </div>
                  ))}
                </div>
                <div className="px-4 py-2 border-t border-gray-50 text-center">
                  <span className="text-xs text-gray-400 hover:text-emerald-600 cursor-pointer transition-colors">查看全部历史通知</span>
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="flex items-center gap-3 pl-1">
          <div className="text-right hidden sm:block">
            <div className="text-sm font-medium text-gray-700">{user?.display_name || user?.username}</div>
            <div className="text-xs text-gray-400">采购专员</div>
          </div>
          <div className="relative group">
            <button className="w-9 h-9 rounded-full bg-gradient-to-br from-emerald-500 to-teal-600 text-white flex items-center justify-center font-medium shadow-md border-2 border-white cursor-pointer">
              {user?.username?.charAt(0).toUpperCase()}
            </button>
            
            {/* Dropdown Menu */}
            <div className="absolute right-0 top-full mt-2 w-48 bg-white rounded-lg shadow-lg border border-gray-100 py-1 hidden group-hover:block hover:block transform origin-top-right transition-all">
              <div className="px-4 py-2 border-b border-gray-50">
                <p className="text-sm font-medium text-gray-900 truncate">{user?.display_name || user?.username}</p>
                <p className="text-xs text-gray-500 truncate">{user?.username}</p>
              </div>
              <a href="#" className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-50">个人中心</a>
              <a href="#" className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-50">设置</a>
              <div className="border-t border-gray-50 my-1"></div>
              <button 
                onClick={logout}
                className="block w-full text-left px-4 py-2 text-sm text-red-600 hover:bg-red-50"
              >
                退出登录
              </button>
            </div>
          </div>
        </div>
      </div>
    </header>
  );
};

export default Header;
