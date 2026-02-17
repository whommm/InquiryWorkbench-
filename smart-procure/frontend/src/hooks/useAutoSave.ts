import { useCallback, useEffect, useRef } from 'react';
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

  const clearDebounceTimer = useCallback(() => {
    if (debounceTimerRef.current !== null) {
      window.clearTimeout(debounceTimerRef.current);
      debounceTimerRef.current = null;
    }
  }, []);

  const clearRetryTimer = useCallback(() => {
    if (retryTimerRef.current !== null) {
      window.clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    }
  }, []);

  const performSave = useCallback(
    async (retryCount: number, forceOverwrite = false): Promise<void> => {
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
          toast.warning('检测到版本冲突，已保留本地改动，请手动处理后再保存');
          failureNotifiedRef.current = false;
        } else if (retryCount >= MAX_RETRIES) {
          if (!failureNotifiedRef.current) {
            toast.error('自动保存失败，请手动保存');
            failureNotifiedRef.current = true;
          }
        } else {
          const delay = RETRY_DELAYS_MS[retryCount];
          if (retryCount === 0) {
            toast.warning('自动保存失败，正在重试...');
          }

          clearRetryTimer();
          retryTimerRef.current = window.setTimeout(() => {
            void performSave(retryCount + 1, forceOverwrite);
          }, delay);
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
    },
    [tabId, updateTab, clearDebounceTimer, clearRetryTimer]
  );

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
  }, [tabId, activeTab, performSave, clearDebounceTimer, clearRetryTimer]);

  useEffect(() => {
    return () => {
      clearDebounceTimer();
      clearRetryTimer();
    };
  }, [clearDebounceTimer, clearRetryTimer]);
};
