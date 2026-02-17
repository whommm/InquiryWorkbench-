import React, { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { useAuthStore } from '../stores/useAuthStore';
import { useTabsStore } from '../stores/useTabsStore';
import {
  archiveNotification,
  exportSheet,
  getNotifications,
  getNotificationStreamUrl,
  markAllNotificationsRead,
  markNotificationRead,
  type NotificationDTO,
  type NotificationStatus,
  type NotificationType,
} from '../utils/api';

interface HeaderProps {
  onToggleSidebar?: () => void;
}

const NOTIFICATION_LIMIT = 80;
const STREAM_RECONNECT_DELAY_MS = 3000;

const toTitle = (type: NotificationType) => {
  if (type === 'success') return '操作成功';
  if (type === 'error') return '系统告警';
  return '系统通知';
};

const formatNotificationTime = (value?: string | null): string => {
  if (!value) return '--';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '--';
  return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
};

const sortByNewest = (items: NotificationDTO[]): NotificationDTO[] =>
  [...items].sort((a, b) => {
    const aTime = a.created_at ? new Date(a.created_at).getTime() : 0;
    const bTime = b.created_at ? new Date(b.created_at).getTime() : 0;
    if (aTime !== bTime) return bTime - aTime;
    return b.id - a.id;
  });

const upsertNotification = (items: NotificationDTO[], incoming: NotificationDTO): NotificationDTO[] => {
  const idx = items.findIndex((item) => item.id === incoming.id);
  if (idx < 0) {
    return sortByNewest([incoming, ...items]).slice(0, NOTIFICATION_LIMIT);
  }
  const next = [...items];
  next[idx] = { ...next[idx], ...incoming };
  return sortByNewest(next).slice(0, NOTIFICATION_LIMIT);
};

const showIncomingNotificationToast = (notification: NotificationDTO) => {
  const message = notification.message || '收到一条新通知';
  if (notification.type === 'success') {
    toast.success(message);
    return;
  }
  if (notification.type === 'error') {
    toast.error(message);
    return;
  }
  toast(message);
};

const Header: React.FC<HeaderProps> = ({ onToggleSidebar }) => {
  const { user, logout, isAuthenticated } = useAuthStore();
  const { tabs, activeTabId, updateTab, isLoading } = useTabsStore();

  const [showNotifications, setShowNotifications] = useState(false);
  const [showUserMenu, setShowUserMenu] = useState(false);
  const [notifications, setNotifications] = useState<NotificationDTO[]>([]);
  const [notificationLoading, setNotificationLoading] = useState(false);

  const notificationRef = useRef<HTMLDivElement>(null);
  const userMenuRef = useRef<HTMLDivElement>(null);
  const streamRef = useRef<EventSource | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);

  const activeTab = tabs.find((t) => t.id === activeTabId);
  const unreadCount = notifications.filter((n) => n.status === 'unread').length;

  const clearReconnectTimer = useCallback(() => {
    if (reconnectTimerRef.current !== null) {
      window.clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, []);

  const closeStream = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.close();
      streamRef.current = null;
    }
  }, []);

  const connectNotificationStream = useCallback(() => {
    clearReconnectTimer();
    closeStream();

    const url = getNotificationStreamUrl();
    if (!url.includes('token=') || url.endsWith('token=')) {
      return;
    }

    const stream = new EventSource(url);
    streamRef.current = stream;

    stream.addEventListener('notification', (event: MessageEvent<string>) => {
      try {
        const payload = JSON.parse(event.data) as NotificationDTO;
        if (!payload || typeof payload.id !== 'number') return;
        setNotifications((prev) => upsertNotification(prev, payload));
        if (payload.status === 'unread') {
          showIncomingNotificationToast(payload);
        }
      } catch (error) {
        console.error('Failed to parse notification SSE payload:', error);
      }
    });

    stream.onerror = () => {
      closeStream();
      clearReconnectTimer();
      reconnectTimerRef.current = window.setTimeout(() => {
        connectNotificationStream();
      }, STREAM_RECONNECT_DELAY_MS);
    };
  }, [clearReconnectTimer, closeStream]);

  const handleTitleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (activeTab) {
      void updateTab(activeTab.id, { name: e.target.value, isDirty: true });
    }
  };

  const handleDownload = async () => {
    if (!activeTab) {
      toast.error('当前没有可导出的表格');
      return;
    }

    if (activeTab.isDirty) {
      toast.warning('当前有未保存改动，导出的是服务端最新版本');
    }

    const toastId = toast.loading('正在生成 Excel 报表...');
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
      toast.error('导出失败', { id: toastId });
    }
  };

  const markOneAsRead = async (notificationId: number) => {
    try {
      const result = await markNotificationRead(notificationId);
      if (result?.notification) {
        setNotifications((prev) => upsertNotification(prev, result.notification));
      }
    } catch (error) {
      console.error('Failed to mark notification as read:', error);
      toast.error('标记已读失败');
    }
  };

  const handleMarkAllRead = async () => {
    try {
      await markAllNotificationsRead();
      const now = new Date().toISOString();
      setNotifications((prev) =>
        prev.map((item) =>
          item.status === 'unread' ? { ...item, status: 'read', read_at: item.read_at || now } : item
        )
      );
    } catch (error) {
      console.error('Failed to mark all notifications as read:', error);
      toast.error('全部已读失败');
    }
  };

  const handleArchive = async (notificationId: number) => {
    try {
      const result = await archiveNotification(notificationId);
      if (result?.notification) {
        setNotifications((prev) => upsertNotification(prev, result.notification));
      }
    } catch (error) {
      console.error('Failed to archive notification:', error);
      toast.error('归档失败');
    }
  };

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (notificationRef.current && !notificationRef.current.contains(event.target as Node)) {
        setShowNotifications(false);
      }
      if (userMenuRef.current && !userMenuRef.current.contains(event.target as Node)) {
        setShowUserMenu(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

  useEffect(() => {
    if (!isAuthenticated) {
      setNotifications([]);
      clearReconnectTimer();
      closeStream();
      return;
    }

    let cancelled = false;
    const fetchNotifications = async () => {
      setNotificationLoading(true);
      try {
        const result = await getNotifications('all', NOTIFICATION_LIMIT);
        if (cancelled) return;
        const list = Array.isArray(result?.notifications) ? result.notifications : [];
        setNotifications(sortByNewest(list));
      } catch (error) {
        console.error('Failed to fetch notifications:', error);
      } finally {
        if (!cancelled) {
          setNotificationLoading(false);
        }
      }
    };

    void fetchNotifications();
    connectNotificationStream();

    return () => {
      cancelled = true;
      clearReconnectTimer();
      closeStream();
    };
  }, [isAuthenticated, clearReconnectTimer, closeStream, connectNotificationStream]);

  const statusLabel = (status: NotificationStatus) => {
    if (status === 'unread') return '未读';
    if (status === 'archived') return '已归档';
    return '已读';
  };

  return (
    <header className="h-14 bg-white border-b border-gray-200 flex items-center justify-between px-4 shadow-sm z-20 relative">
      <div className="flex items-center gap-4">
        <button
          onClick={onToggleSidebar}
          aria-label="切换 AI 助手"
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
              placeholder="未命名询价单"
            />
            <div className="w-2 h-2 rounded-full bg-emerald-500 ml-2" title="已自动保存" />
          </div>
        ) : (
          <span className="text-gray-400 text-sm">暂无活动表格</span>
        )}
      </div>

      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1 border-r border-gray-200 pr-3 mr-1">
          <button
            onClick={() => {
              void handleDownload();
            }}
            aria-label="导出 Excel"
            className="p-2 text-gray-500 hover:text-emerald-600 hover:bg-gray-100 rounded-full transition-colors"
            title="导出 Excel"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
          </button>

          <div className="relative" ref={notificationRef}>
            <button
              onClick={() => setShowNotifications((prev) => !prev)}
              aria-label="查看通知"
              className={`p-2 rounded-full transition-colors ${showNotifications ? 'bg-gray-100 text-emerald-600' : 'text-gray-500 hover:text-emerald-600 hover:bg-gray-100'}`}
              title="通知"
            >
              <div className="relative">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
                </svg>
                {unreadCount > 0 && (
                  <span className="absolute -top-0.5 -right-0.5 min-w-4 h-4 px-1 rounded-full bg-red-500 text-white text-xs leading-4 text-center">
                    {unreadCount > 99 ? '99+' : unreadCount}
                  </span>
                )}
              </div>
            </button>

            {showNotifications && (
              <div className="absolute right-0 top-full mt-2 w-96 bg-white rounded-xl shadow-lg border border-gray-100 py-2 z-50 animate-in fade-in slide-in-from-top-2 duration-200">
                <div className="px-4 py-2 border-b border-gray-50 flex justify-between items-center">
                  <h3 className="font-semibold text-gray-800">通知中心</h3>
                  <button
                    onClick={() => {
                      void handleMarkAllRead();
                    }}
                    className="text-sm text-emerald-600 cursor-pointer hover:underline"
                    disabled={unreadCount === 0}
                  >
                    全部已读
                  </button>
                </div>
                <div className="max-h-[320px] overflow-y-auto">
                  {notificationLoading ? (
                    <div className="px-4 py-6 text-sm text-gray-400 text-center">加载中...</div>
                  ) : notifications.length === 0 ? (
                    <div className="px-4 py-6 text-sm text-gray-400 text-center">暂无通知</div>
                  ) : (
                    notifications.map((notification) => {
                      const isUnread = notification.status === 'unread';
                      const isArchived = notification.status === 'archived';
                      return (
                        <div
                          key={notification.id}
                          className={`w-full text-left px-4 py-3 hover:bg-gray-50 transition-colors border-b border-gray-50 last:border-0 ${isUnread ? 'bg-blue-50/30' : ''}`}
                          onClick={() => {
                            if (isUnread) {
                              void markOneAsRead(notification.id);
                            }
                          }}
                        >
                          <div className="flex justify-between items-start gap-2 mb-1">
                            <span className={`text-sm font-medium ${isUnread ? 'text-gray-900' : 'text-gray-600'}`}>
                              {toTitle(notification.type)}
                            </span>
                            <div className="flex items-center gap-2">
                              <span className="text-xs text-gray-400">{formatNotificationTime(notification.created_at)}</span>
                              <span
                                className={`text-xs px-1.5 py-0.5 rounded ${
                                  isUnread
                                    ? 'bg-blue-100 text-blue-700'
                                    : isArchived
                                      ? 'bg-gray-100 text-gray-500'
                                      : 'bg-emerald-100 text-emerald-700'
                                }`}
                              >
                                {statusLabel(notification.status)}
                              </span>
                            </div>
                          </div>
                          <p className="text-sm text-gray-500 line-clamp-2">{notification.message}</p>
                          <div className="mt-2 flex justify-end">
                            {!isArchived && (
                              <button
                                type="button"
                                className="text-xs text-gray-400 hover:text-gray-600"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  void handleArchive(notification.id);
                                }}
                              >
                                归档
                              </button>
                            )}
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="flex items-center gap-3 pl-1" ref={userMenuRef}>
          <div className="text-right hidden sm:block">
            <div className="text-sm font-medium text-gray-700">{user?.display_name || user?.username}</div>
            <div className="text-xs text-gray-400">采购专员</div>
          </div>
          <div className="relative">
            <button
              aria-label="打开用户菜单"
              onClick={() => setShowUserMenu((prev) => !prev)}
              className="w-9 h-9 rounded-full bg-gradient-to-br from-emerald-500 to-teal-600 text-white flex items-center justify-center font-medium shadow-md border-2 border-white cursor-pointer"
            >
              {(user?.username?.charAt(0) ?? '?').toUpperCase()}
            </button>

            {showUserMenu && (
              <div className="absolute right-0 top-full mt-2 w-48 bg-white rounded-lg shadow-lg border border-gray-100 py-1 z-50">
                <div className="px-4 py-2 border-b border-gray-50">
                  <p className="text-sm font-medium text-gray-900 truncate">{user?.display_name || user?.username}</p>
                  <p className="text-xs text-gray-500 truncate">{user?.username}</p>
                </div>
                <button
                  type="button"
                  className="block w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
                >
                  个人中心
                </button>
                <button
                  type="button"
                  className="block w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
                >
                  设置
                </button>
                <div className="border-t border-gray-50 my-1" />
                <button
                  onClick={logout}
                  className="block w-full text-left px-4 py-2 text-sm text-red-600 hover:bg-red-50"
                >
                  退出登录
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </header>
  );
};

export default Header;

