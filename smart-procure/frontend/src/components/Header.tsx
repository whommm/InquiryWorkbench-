import React, { useState, useEffect, useRef } from 'react';
import { useAuthStore } from '../stores/useAuthStore';
import { useTabsStore } from '../stores/useTabsStore';
import { exportSheet, getNotifications } from '../utils/api';
import { toast } from 'sonner';

interface HeaderProps {
  onToggleSidebar?: () => void;
}

type NotificationType = 'info' | 'success' | 'error';

interface NotificationItem {
  id: number;
  title: string;
  message: string;
  time: string;
  read: boolean;
  type: NotificationType;
}

const Header: React.FC<HeaderProps> = ({ onToggleSidebar }) => {
  const { user, logout, isAuthenticated } = useAuthStore();
  const { tabs, activeTabId, updateTab, isLoading } = useTabsStore();
  const [showNotifications, setShowNotifications] = useState(false);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const notificationRef = useRef<HTMLDivElement>(null);

  const activeTab = tabs.find((t) => t.id === activeTabId);

  const unreadCount = notifications.filter((n) => !n.read).length;

  const formatTime = (date: Date) => {
    return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  };

  const toTitle = (type: NotificationType) => {
    if (type === 'success') return '操作成功';
    if (type === 'error') return '系统告警';
    return '系统通知';
  };

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

  useEffect(() => {
    if (!isAuthenticated) return;

    const fetchNotifications = async () => {
      try {
        const result = await getNotifications();
        const incoming = Array.isArray(result?.notifications)
          ? (result.notifications as Array<{ message?: string; type?: string }>)
          : [];

        if (!incoming.length) return;

        const now = Date.now();
        const mapped: NotificationItem[] = incoming.map((item, index) => {
          const type: NotificationType =
            item.type === 'success' || item.type === 'error' ? item.type : 'info';
          const message = item.message || '收到一条新通知';

          if (type === 'success') {
            toast.success(message);
          } else if (type === 'error') {
            toast.error(message);
          } else {
            toast(message);
          }

          return {
            id: now + index,
            title: toTitle(type),
            message,
            time: formatTime(new Date()),
            read: false,
            type,
          };
        });

        setNotifications((prev) => [...mapped, ...prev].slice(0, 50));
      } catch (error) {
        console.error('Failed to fetch notifications:', error);
      }
    };

    void fetchNotifications();
    const interval = window.setInterval(() => {
      void fetchNotifications();
    }, 5000);

    return () => window.clearInterval(interval);
  }, [isAuthenticated]);

  const handleTitleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (activeTab) {
      void updateTab(activeTab.id, { name: e.target.value, isDirty: true });
    }
  };

  const handleMarkAllRead = () => {
    setNotifications((prev) => prev.map((item) => ({ ...item, read: true })));
  };

  const handleDownload = async () => {
    if (!activeTab) {
      toast.error('褰撳墠娌℃湁娲诲姩鐨勮〃鏍煎彲瀵煎嚭');
      return;
    }

    if (activeTab.isDirty) {
      toast.warning('当前有未保存改动，导出的是服务器最新版本');
    }

    const toastId = toast.loading('姝ｅ湪鐢熸垚 Excel 鎶ヨ〃...');
    try {
      const blob = await exportSheet(activeTab.id);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${activeTab.name}.xlsx`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
      toast.success('报表已成功导出', { id: toastId });
    } catch (error) {
      console.error('Failed to export sheet:', error);
      toast.error('瀵煎嚭澶辫触', { id: toastId });
    }
  };

  return (
    <header className="h-14 bg-white border-b border-gray-200 flex items-center justify-between px-4 shadow-sm z-20 relative">
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
          <span className="font-bold text-gray-800 text-lg tracking-tight hidden sm:block">SmartProcure</span>
        </div>
      </div>

      <div className="flex-1 max-w-2xl mx-4 flex items-center justify-center">
        {isLoading ? (
          <div className="h-8 w-48 bg-gray-100 rounded animate-pulse" />
        ) : activeTab ? (
          <div className="group flex items-center gap-2 px-3 py-1.5 rounded-md hover:bg-gray-50 transition-colors cursor-text max-w-full">
            <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
              />
            </svg>
            <input
              type="text"
              value={activeTab.name}
              onChange={handleTitleChange}
              className="bg-transparent border-none focus:ring-0 text-gray-700 font-medium text-sm w-full text-center p-0 placeholder-gray-400"
              placeholder="鏈懡鍚嶈浠峰崟"
            />
            <div className="w-2 h-2 rounded-full bg-emerald-500 ml-2" title="Auto-saved" />
          </div>
        ) : (
          <span className="text-gray-400 text-sm italic">No active sheet</span>
        )}
      </div>

      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1 border-r border-gray-200 pr-3 mr-1">
          <button
            onClick={() => {
              void handleDownload();
            }}
            className="p-2 text-gray-500 hover:text-emerald-600 hover:bg-gray-100 rounded-full transition-colors"
            title="瀵煎嚭 Excel"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
              />
            </svg>
          </button>

          <div className="relative" ref={notificationRef}>
            <button
              onClick={() => setShowNotifications(!showNotifications)}
              className={`p-2 rounded-full transition-colors ${showNotifications ? 'bg-gray-100 text-emerald-600' : 'text-gray-500 hover:text-emerald-600 hover:bg-gray-100'}`}
              title="閫氱煡"
            >
              <div className="relative">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"
                  />
                </svg>
                {unreadCount > 0 && (
                  <span className="absolute -top-0.5 -right-0.5 block h-2.5 w-2.5 rounded-full bg-red-500 ring-2 ring-white" />
                )}
              </div>
            </button>

            {showNotifications && (
              <div className="absolute right-0 top-full mt-2 w-80 bg-white rounded-xl shadow-lg border border-gray-100 py-2 z-50 animate-in fade-in slide-in-from-top-2 duration-200">
                <div className="px-4 py-2 border-b border-gray-50 flex justify-between items-center">
                  <h3 className="font-semibold text-gray-800">閫氱煡涓績</h3>
                  <button
                    onClick={handleMarkAllRead}
                    className="text-xs text-emerald-600 cursor-pointer hover:underline"
                  >
                    鍏ㄩ儴宸茶
                  </button>
                </div>
                <div className="max-h-[300px] overflow-y-auto">
                  {notifications.length === 0 ? (
                    <div className="px-4 py-6 text-sm text-gray-400 text-center">鏆傛棤閫氱煡</div>
                  ) : (
                    notifications.map((n) => (
                      <div
                        key={n.id}
                        className={`px-4 py-3 hover:bg-gray-50 transition-colors border-b border-gray-50 last:border-0 ${!n.read ? 'bg-blue-50/30' : ''}`}
                      >
                        <div className="flex justify-between items-start mb-1">
                          <span className={`text-sm font-medium ${!n.read ? 'text-gray-900' : 'text-gray-600'}`}>{n.title}</span>
                          <span className="text-xs text-gray-400">{n.time}</span>
                        </div>
                        <p className="text-sm text-gray-500 line-clamp-2">{n.message}</p>
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="flex items-center gap-3 pl-1">
          <div className="text-right hidden sm:block">
            <div className="text-sm font-medium text-gray-700">{user?.display_name || user?.username}</div>
            <div className="text-xs text-gray-400">閲囪喘涓撳憳</div>
          </div>
          <div className="relative group">
            <button className="w-9 h-9 rounded-full bg-gradient-to-br from-emerald-500 to-teal-600 text-white flex items-center justify-center font-medium shadow-md border-2 border-white cursor-pointer">
              {(user?.username?.charAt(0) ?? '?').toUpperCase()}
            </button>

            <div className="absolute right-0 top-full mt-2 w-48 bg-white rounded-lg shadow-lg border border-gray-100 py-1 hidden group-hover:block hover:block transform origin-top-right transition-all">
              <div className="px-4 py-2 border-b border-gray-50">
                <p className="text-sm font-medium text-gray-900 truncate">{user?.display_name || user?.username}</p>
                <p className="text-xs text-gray-500 truncate">{user?.username}</p>
              </div>
              <a href="#" className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-50">涓汉涓績</a>
              <a href="#" className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-50">璁剧疆</a>
              <div className="border-t border-gray-50 my-1"></div>
              <button onClick={logout} className="block w-full text-left px-4 py-2 text-sm text-red-600 hover:bg-red-50">
                閫€鍑虹櫥褰?
              </button>
            </div>
          </div>
        </div>
      </div>
    </header>
  );
};

export default Header;

