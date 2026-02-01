import { create } from 'zustand';
import { v4 as uuidv4 } from 'uuid';
import type { InquiryTab } from '../utils/indexedDB';
import { saveTab, getAllTabs, deleteTab } from '../utils/indexedDB';

interface TabsState {
  tabs: InquiryTab[];
  activeTabId: string | null;
  isLoading: boolean;
  userId: string | null;

  // Actions
  initializeTabs: (userId: string) => Promise<void>;
  createTab: (name?: string, initialData?: Partial<InquiryTab>) => Promise<string>;
  switchTab: (tabId: string) => void;
  closeTab: (tabId: string) => Promise<boolean>;
  updateTabData: (tabId: string, updates: Partial<InquiryTab>) => Promise<void>;
  getActiveTab: () => InquiryTab | null;
  clearTabs: () => void;
}

const formatDate = (date: Date): string => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  return `${year}-${month}-${day} ${hours}:${minutes}`;
};

export const useTabsStore = create<TabsState>((set, get) => ({
  tabs: [],
  activeTabId: null,
  isLoading: false,
  userId: null,

  /**
   * Initialize tabs from IndexedDB for a specific user
   */
  initializeTabs: async (userId: string) => {
    set({ isLoading: true, userId });
    try {
      const tabs = await getAllTabs(userId);

      if (tabs.length === 0) {
        // Create default tab if none exist
        const defaultTab: InquiryTab = {
          id: uuidv4(),
          name: `询价单-${formatDate(new Date())}`,
          sheetData: [],
          chatHistory: [],
          createdAt: Date.now(),
          updatedAt: Date.now(),
          isDirty: false,
        };

        await saveTab(userId, defaultTab);
        set({ tabs: [defaultTab], activeTabId: defaultTab.id });
      } else {
        // Load existing tabs, set first as active
        set({ tabs, activeTabId: tabs[0].id });
      }
    } catch (error) {
      console.error('Failed to initialize tabs:', error);
      // Create a fallback tab in memory
      const fallbackTab: InquiryTab = {
        id: uuidv4(),
        name: `询价单-${formatDate(new Date())}`,
        sheetData: [],
        chatHistory: [],
        createdAt: Date.now(),
        updatedAt: Date.now(),
        isDirty: false,
      };
      set({ tabs: [fallbackTab], activeTabId: fallbackTab.id });
    } finally {
      set({ isLoading: false });
    }
  },

  /**
   * Create a new tab
   * @param name - Optional tab name
   * @param initialData - Optional initial data for the tab (sheetData, chatHistory, etc.)
   */
  createTab: async (name?: string, initialData?: Partial<InquiryTab>) => {
    const { userId } = get();
    if (!userId) throw new Error('User not initialized');

    const newTab: InquiryTab = {
      id: uuidv4(),
      name: name || `询价单-${formatDate(new Date())}`,
      sheetData: [],
      chatHistory: [],
      createdAt: Date.now(),
      updatedAt: Date.now(),
      isDirty: false,
      ...initialData,
    };

    try {
      await saveTab(userId, newTab);
      set(state => ({
        tabs: [...state.tabs, newTab],
        activeTabId: newTab.id,
      }));
      return newTab.id;
    } catch (error) {
      console.error('Failed to create tab:', error);
      throw error;
    }
  },

  /**
   * Switch to a different tab
   */
  switchTab: (tabId: string) => {
    const { tabs } = get();
    const tab = tabs.find(t => t.id === tabId);
    if (tab) {
      set({ activeTabId: tabId });
    }
  },

  /**
   * Close a tab (with dirty check)
   * Returns true if closed, false if cancelled
   */
  closeTab: async (tabId: string) => {
    const { tabs, activeTabId, userId } = get();
    if (!userId) return false;

    const tab = tabs.find(t => t.id === tabId);

    if (!tab) return false;

    // Check if tab has unsaved changes
    if (tab.isDirty) {
      const confirmed = window.confirm(
        `标签页 "${tab.name}" 有未保存的修改，确定要关闭吗？`
      );
      if (!confirmed) return false;
    }

    try {
      // Delete from IndexedDB
      await deleteTab(userId, tabId);

      // Remove from state
      const newTabs = tabs.filter(t => t.id !== tabId);

      // If closing active tab, switch to another
      let newActiveTabId = activeTabId;
      if (activeTabId === tabId) {
        if (newTabs.length > 0) {
          const closedIndex = tabs.findIndex(t => t.id === tabId);
          const nextIndex = closedIndex < newTabs.length ? closedIndex : newTabs.length - 1;
          newActiveTabId = newTabs[nextIndex].id;
        } else {
          newActiveTabId = null;
        }
      }

      set({ tabs: newTabs, activeTabId: newActiveTabId });
      return true;
    } catch (error) {
      console.error('Failed to close tab:', error);
      return false;
    }
  },

  /**
   * Update tab data
   */
  updateTabData: async (tabId: string, updates: Partial<InquiryTab>) => {
    const { tabs, userId } = get();
    if (!userId) return;

    const tab = tabs.find(t => t.id === tabId);
    if (!tab) return;

    const updatedTab: InquiryTab = {
      ...tab,
      ...updates,
      updatedAt: Date.now(),
      isDirty: updates.isDirty !== undefined ? updates.isDirty : true,
    };

    try {
      await saveTab(userId, updatedTab);
      set(state => ({
        tabs: state.tabs.map(t => t.id === tabId ? updatedTab : t),
      }));
    } catch (error) {
      console.error('Failed to update tab:', error);
      throw error;
    }
  },

  /**
   * Get the currently active tab
   */
  getActiveTab: () => {
    const { tabs, activeTabId } = get();
    return tabs.find(t => t.id === activeTabId) || null;
  },

  /**
   * Clear all tabs (used when user logs out or switches)
   */
  clearTabs: () => {
    set({ tabs: [], activeTabId: null, userId: null });
  },
}));
