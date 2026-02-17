import { useEffect, useRef } from 'react';
import { toast } from 'sonner';
import { saveSheet } from '../utils/api';
import { useTabsStore } from '../stores/useTabsStore';

const AUTO_SAVE_DELAY_MS = 3000;
const RETRY_DELAYS_MS = [2000, 5000, 10000];
const MAX_RETRIES = RETRY_DELAYS_MS.length;

const getErrorStatus = (error: unknown): number | undefined => {
  const status = (error as { response?: { status?: number } })?.response?.status;
  return typeof status === 'number' ? status : undefined;
};

const getConflictServerUpdatedAt = (error: unknown): string | null => {
  const detail = (error as { response?: { data?: { detail?: Record<string, unknown> } } })?.response?.data?.detail;
  const value = detail?.server_updated_at;
  return typeof value === 'string' ? value : null;
};

export const useAutoSave = (tabId: string | null) => {
  const activeTab = useTabsStore((state) =>
    state.tabs.find((tab) => tabId && tab.id === tabId) ?? null
  );
  const updateTab = useTabsStore((state) => state.updateTab);

  const debounceTimerRef = useRef<number | null>(null);
  const retryTimerRef = useRef<number | null>(null);
  const inFlightRef = useRef(false);
  const pendingRef = useRef(false);
  const latestTabRef = useRef(activeTab);
  const failureNotifiedRef = useRef(false);

  const clearDebounceTimer = () => {
    if (debounceTimerRef.current !== null) {
      window.clearTimeout(debounceTimerRef.current);
      debounceTimerRef.current = null;
    }
  };

  const clearRetryTimer = () => {
    if (retryTimerRef.current !== null) {
      window.clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    }
  };

  const scheduleRetry = (retryCount: number, run: () => Promise<void>) => {
    if (retryCount >= MAX_RETRIES) {
      if (!failureNotifiedRef.current) {
        toast.error('自动保存失败，请手动保存');
        failureNotifiedRef.current = true;
      }
      return;
    }

    const delay = RETRY_DELAYS_MS[retryCount];
    if (retryCount === 0) {
      toast.warning('自动保存失败，正在重试');
    }

    clearRetryTimer();
    retryTimerRef.current = window.setTimeout(() => {
      void run();
    }, delay);
  };

  const performSave = async (retryCount: number, forceOverwrite: boolean = false): Promise<void> => {
    const tab = latestTabRef.current;
    if (!tabId || !tab || tab.id !== tabId || !tab.isDirty) return;
    if (inFlightRef.current) {
      pendingRef.current = true;
      return;
    }

    inFlightRef.current = true;
    pendingRef.current = false;

    try {
      const saveResult = await saveSheet({
        id: tab.id,
        name: tab.name,
        sheet_data: tab.sheetData,
        chat_history: tab.chatHistory,
        expected_updated_at: forceOverwrite ? undefined : tab.serverUpdatedAt || undefined,
        force_overwrite: forceOverwrite,
      });

      await updateTab(tab.id, {
        isDirty: false,
        serverUpdatedAt: saveResult.updated_at || tab.serverUpdatedAt || null,
      });

      if (retryCount > 0) {
        toast.success('自动保存已恢复');
      }
      failureNotifiedRef.current = false;
      clearRetryTimer();
    } catch (error) {
      const status = getErrorStatus(error);

      if (status === 409 && !forceOverwrite) {
        const serverUpdatedAt = getConflictServerUpdatedAt(error);
        const serverTimeLabel = serverUpdatedAt
          ? new Date(serverUpdatedAt).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })
          : '未知时间';

        const shouldOverwrite = window.confirm(
          `检测到服务器版本冲突（服务器更新时间：${serverTimeLabel}）。\n是否使用当前本地内容覆盖服务器版本？`
        );

        if (shouldOverwrite) {
          inFlightRef.current = false;
          await performSave(0, true);
          return;
        }

        toast.warning('已保留本地改动，请手动处理冲突');
        failureNotifiedRef.current = false;
      } else {
        scheduleRetry(retryCount, async () => {
          await performSave(retryCount + 1, forceOverwrite);
        });
      }
    } finally {
      inFlightRef.current = false;

      if (pendingRef.current) {
        pendingRef.current = false;
        clearDebounceTimer();
        debounceTimerRef.current = window.setTimeout(() => {
          void performSave(0, false);
        }, AUTO_SAVE_DELAY_MS);
      }
    }
  };

  useEffect(() => {
    latestTabRef.current = activeTab;
  }, [activeTab]);

  useEffect(() => {
    if (!tabId || !activeTab || activeTab.id !== tabId) {
      clearDebounceTimer();
      clearRetryTimer();
      return;
    }
    if (!activeTab.isDirty) {
      clearDebounceTimer();
      clearRetryTimer();
      return;
    }

    clearDebounceTimer();
    debounceTimerRef.current = window.setTimeout(() => {
      void performSave(0, false);
    }, AUTO_SAVE_DELAY_MS);

    return () => {
      clearDebounceTimer();
    };
  }, [tabId, activeTab?.id, activeTab?.isDirty, activeTab?.updatedAt]);

  useEffect(() => {
    return () => {
      clearDebounceTimer();
      clearRetryTimer();
    };
  }, []);
};
