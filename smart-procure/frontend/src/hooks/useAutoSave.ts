import { useEffect, useRef } from 'react';
import { useTabsStore } from '../stores/useTabsStore';
import { saveSheet } from '../utils/api';

/**
 * Auto-save hook that saves tab data after a period of inactivity
 * @param tabId - The ID of the tab to auto-save
 * @param interval - Debounce interval in milliseconds (default: 3000ms)
 */
export const useAutoSave = (tabId: string | null, interval: number = 3000) => {
  const { tabs, updateTabData } = useTabsStore();
  const timeoutRef = useRef<number | null>(null);
  const lastSavedRef = useRef<Record<string, string>>({});
  const isSavingRef = useRef(false);

  useEffect(() => {
    if (!tabId) return;

    const tab = tabs.find(t => t.id === tabId);
    if (!tab || !tab.isDirty) return;

    // Create a snapshot of current data for comparison
    const currentSnapshot = JSON.stringify({
      sheetData: tab.sheetData,
      chatHistory: tab.chatHistory,
    });

    // Skip if data hasn't changed since last save for this specific tab
    if (currentSnapshot === lastSavedRef.current[tabId]) return;

    // Skip if already saving
    if (isSavingRef.current) return;

    // Clear existing timeout
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
    }

    // Set new timeout for auto-save
    timeoutRef.current = window.setTimeout(async () => {
      if (isSavingRef.current) return;

      isSavingRef.current = true;
      try {
        console.log(`Auto-saving tab: ${tab.name}...`);

        await saveSheet({
          id: tab.id,
          name: tab.name,
          sheet_data: tab.sheetData,
          chat_history: tab.chatHistory,
        });

        // Update tab to mark as saved
        await updateTabData(tabId, { isDirty: false });

        // Update last saved snapshot for this tab
        lastSavedRef.current[tabId] = currentSnapshot;

        console.log(`✓ Auto-saved tab: ${tab.name}`);
      } catch (error) {
        console.error('❌ Auto-save failed:', error);
        // Keep isDirty as true so it will retry
      } finally {
        isSavingRef.current = false;
        timeoutRef.current = null;
      }
    }, interval);

    // Cleanup only on unmount, not on every re-render
    return () => {
      // Don't clear timeout here - let it complete
      // Only clear on unmount
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
    };
  }, [tabId, tabs, interval, updateTabData]);
};
