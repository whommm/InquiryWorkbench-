import { create } from 'zustand';
import { v4 as uuidv4 } from 'uuid';
import type { InquiryTab } from '../utils/indexedDB';
import { saveTab, getAllTabs, deleteTab, saveTabDeferred, flushAllPendingTabSaves } from '../utils/indexedDB';

interface TabsState {
  tabs: InquiryTab[];
  activeTabId: string | null;
  isLoading: boolean;
  userId: string | null;
  initializeTabs: (userId: string) => Promise<void>;
  createTab: (name?: string, initialData?: Partial<InquiryTab>) => Promise<string>;
  switchTab: (tabId: string) => void;
  closeTab: (tabId: string) => Promise<boolean>;
  updateTab: (tabId: string, updates: Partial<InquiryTab>) => Promise<void>;
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

  initializeTabs: async (userId: string) => {
    set({ isLoading: true, userId });
    try {
      const tabs = await getAllTabs(userId);

      if (tabs.length === 0) {
        const defaultTab: InquiryTab = {
          id: uuidv4(),
          name: `询价单 ${formatDate(new Date())}`,
          sheetData: [],
          chatHistory: [],
          createdAt: Date.now(),
          updatedAt: Date.now(),
          isDirty: false,
          serverUpdatedAt: null,
        };

        await saveTab(userId, defaultTab);
        set({ tabs: [defaultTab], activeTabId: defaultTab.id });
      } else {
        const normalizedTabs = tabs.map((tab) => ({
          ...tab,
          serverUpdatedAt: tab.serverUpdatedAt ?? null,
        }));
        set({ tabs: normalizedTabs, activeTabId: normalizedTabs[0].id });
      }
    } catch (error) {
      console.error('Failed to initialize tabs:', error);
      const fallbackTab: InquiryTab = {
        id: uuidv4(),
        name: `询价单 ${formatDate(new Date())}`,
        sheetData: [],
        chatHistory: [],
        createdAt: Date.now(),
        updatedAt: Date.now(),
        isDirty: false,
        serverUpdatedAt: null,
      };
      set({ tabs: [fallbackTab], activeTabId: fallbackTab.id });
    } finally {
      set({ isLoading: false });
    }
  },

  createTab: async (name?: string, initialData?: Partial<InquiryTab>) => {
    const { userId, tabs } = get();
    if (!userId) throw new Error('User not initialized');

    const tabId = initialData?.id || uuidv4();

    if (initialData?.id) {
      const existingTab = tabs.find((t) => t.id === initialData.id);
      if (existingTab) {
        set({ activeTabId: existingTab.id });
        return existingTab.id;
      }
    }

    const newTab: InquiryTab = {
      ...initialData,
      id: tabId,
      name: name || initialData?.name || `询价单 ${formatDate(new Date())}`,
      sheetData: initialData?.sheetData || [],
      chatHistory: initialData?.chatHistory || [],
      createdAt: initialData?.createdAt || Date.now(),
      updatedAt: Date.now(),
      isDirty: initialData?.isDirty ?? false,
      serverUpdatedAt: initialData?.serverUpdatedAt ?? null,
    };

    try {
      await saveTab(userId, newTab);
      set((state) => ({
        tabs: [...state.tabs, newTab],
        activeTabId: newTab.id,
      }));
      return newTab.id;
    } catch (error) {
      console.error('Failed to create tab:', error);
      throw error;
    }
  },

  switchTab: (tabId: string) => {
    const { tabs } = get();
    const tab = tabs.find((t) => t.id === tabId);
    if (tab) {
      set({ activeTabId: tabId });
    }
  },

  closeTab: async (tabId: string) => {
    const { tabs, activeTabId, userId } = get();
    if (!userId) return false;

    const tab = tabs.find((t) => t.id === tabId);
    if (!tab) return false;

    try {
      await deleteTab(userId, tabId);

      const newTabs = tabs.filter((t) => t.id !== tabId);
      let newActiveTabId = activeTabId;

      if (activeTabId === tabId) {
        if (newTabs.length > 0) {
          const closedIndex = tabs.findIndex((t) => t.id === tabId);
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

  updateTab: async (tabId: string, updates: Partial<InquiryTab>) => {
    const { userId, tabs } = get();
    if (!userId) throw new Error('User not initialized');

    const updatedTabs = tabs.map((tab) => {
      if (tab.id === tabId) {
        return { ...tab, ...updates, updatedAt: Date.now() };
      }
      return tab;
    });

    set({ tabs: updatedTabs });

    const updatedTab = updatedTabs.find((t) => t.id === tabId);
    if (updatedTab) {
      void saveTabDeferred(userId, updatedTab);
    }
  },

  getActiveTab: () => {
    const { tabs, activeTabId } = get();
    return tabs.find((t) => t.id === activeTabId) || null;
  },

  clearTabs: () => {
    const currentUserId = get().userId;
    if (currentUserId) {
      void flushAllPendingTabSaves(currentUserId);
    }
    set({ tabs: [], activeTabId: null, userId: null });
  },
}));

