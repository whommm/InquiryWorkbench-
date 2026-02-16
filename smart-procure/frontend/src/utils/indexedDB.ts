/**
 * IndexedDB utility for storing inquiry tabs locally
 * 按用户隔离数据
 */

export interface InquiryTab {
  id: string;
  name: string;
  sheetData: unknown[][];
  chatHistory: Array<{
    role: 'user' | 'assistant' | 'system';
    content: string;
  }>;
  createdAt: number;
  updatedAt: number;
  isDirty: boolean;
}

const DB_NAME_PREFIX = 'SmartProcureDB_';
const DB_VERSION = 1;
const STORE_NAME = 'tabs';
const DEFERRED_SAVE_DELAY_MS = 300;

type PendingSaveEntry = {
  tab: InquiryTab;
  timerId: number | null;
  resolvers: Array<() => void>;
  rejectors: Array<(error: Error) => void>;
};

const pendingSaves = new Map<string, PendingSaveEntry>();

const getPendingSaveKey = (userId: string, tabId: string): string => `${userId}:${tabId}`;

/**
 * Get database name for a specific user
 */
const getDBName = (userId: string): string => {
  return `${DB_NAME_PREFIX}${userId}`;
};

/**
 * Open IndexedDB connection for a specific user
 */
export const openDB = (userId: string): Promise<IDBDatabase> => {
  return new Promise((resolve, reject) => {
    const dbName = getDBName(userId);
    const request = indexedDB.open(dbName, DB_VERSION);

    request.onerror = () => {
      reject(new Error('Failed to open IndexedDB'));
    };

    request.onsuccess = () => {
      resolve(request.result);
    };

    request.onupgradeneeded = (event) => {
      const db = (event.target as IDBOpenDBRequest).result;

      // Create object store if it doesn't exist
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        const objectStore = db.createObjectStore(STORE_NAME, { keyPath: 'id' });
        objectStore.createIndex('updatedAt', 'updatedAt', { unique: false });
        objectStore.createIndex('createdAt', 'createdAt', { unique: false });
      }
    };
  });
};

/**
 * Save a tab to IndexedDB
 */
export const saveTab = async (userId: string, tab: InquiryTab): Promise<void> => {
  const db = await openDB(userId);

  return new Promise((resolve, reject) => {
    const transaction = db.transaction([STORE_NAME], 'readwrite');
    const store = transaction.objectStore(STORE_NAME);
    const request = store.put(tab);

    request.onsuccess = () => {
      resolve();
    };

    request.onerror = () => {
      reject(new Error('Failed to save tab'));
    };

    transaction.oncomplete = () => {
      db.close();
    };
  });
};

const flushPendingSave = async (pendingKey: string): Promise<void> => {
  const entry = pendingSaves.get(pendingKey);
  if (!entry) {
    return;
  }

  if (entry.timerId !== null) {
    window.clearTimeout(entry.timerId);
    entry.timerId = null;
  }

  pendingSaves.delete(pendingKey);

  try {
    const [userId] = pendingKey.split(':');
    await saveTab(userId, entry.tab);
    entry.resolvers.forEach((resolve) => resolve());
  } catch (error) {
    const err = error instanceof Error ? error : new Error('Failed to save tab');
    entry.rejectors.forEach((reject) => reject(err));
  }
};

/**
 * Save tab with debounce to avoid writing large objects on every single edit.
 */
export const saveTabDeferred = (
  userId: string,
  tab: InquiryTab,
  delayMs: number = DEFERRED_SAVE_DELAY_MS
): Promise<void> => {
  const pendingKey = getPendingSaveKey(userId, tab.id);
  const existing = pendingSaves.get(pendingKey);

  if (existing) {
    existing.tab = tab;
    if (existing.timerId !== null) {
      window.clearTimeout(existing.timerId);
      existing.timerId = null;
    }
    return new Promise((resolve, reject) => {
      existing.resolvers.push(resolve);
      existing.rejectors.push(reject);
      existing.timerId = window.setTimeout(() => {
        void flushPendingSave(pendingKey);
      }, delayMs);
    });
  }

  const entry: PendingSaveEntry = {
    tab,
    timerId: null,
    resolvers: [],
    rejectors: [],
  };
  pendingSaves.set(pendingKey, entry);

  return new Promise((resolve, reject) => {
    entry.resolvers.push(resolve);
    entry.rejectors.push(reject);
    entry.timerId = window.setTimeout(() => {
      void flushPendingSave(pendingKey);
    }, delayMs);
  });
};

/**
 * Flush all pending tab saves. Useful before destructive actions (delete/clear/logout).
 */
export const flushAllPendingTabSaves = async (userId?: string): Promise<void> => {
  const keys = Array.from(pendingSaves.keys()).filter((key) => {
    if (!userId) return true;
    return key.startsWith(`${userId}:`);
  });

  for (const key of keys) {
    await flushPendingSave(key);
  }
};

/**
 * Get a single tab by ID
 */
export const getTab = async (userId: string, id: string): Promise<InquiryTab | null> => {
  const db = await openDB(userId);

  return new Promise((resolve, reject) => {
    const transaction = db.transaction([STORE_NAME], 'readonly');
    const store = transaction.objectStore(STORE_NAME);
    const request = store.get(id);

    request.onsuccess = () => {
      resolve(request.result || null);
    };

    request.onerror = () => {
      reject(new Error('Failed to get tab'));
    };

    transaction.oncomplete = () => {
      db.close();
    };
  });
};

/**
 * Get all tabs, sorted by updatedAt descending
 */
export const getAllTabs = async (userId: string): Promise<InquiryTab[]> => {
  const db = await openDB(userId);

  return new Promise((resolve, reject) => {
    const transaction = db.transaction([STORE_NAME], 'readonly');
    const store = transaction.objectStore(STORE_NAME);
    const request = store.getAll();

    request.onsuccess = () => {
      const tabs = request.result as InquiryTab[];
      // Sort by updatedAt descending
      tabs.sort((a, b) => b.updatedAt - a.updatedAt);
      resolve(tabs);
    };

    request.onerror = () => {
      reject(new Error('Failed to get all tabs'));
    };

    transaction.oncomplete = () => {
      db.close();
    };
  });
};

/**
 * Delete a tab by ID
 */
export const deleteTab = async (userId: string, id: string): Promise<void> => {
  await flushAllPendingTabSaves(userId);
  const db = await openDB(userId);

  return new Promise((resolve, reject) => {
    const transaction = db.transaction([STORE_NAME], 'readwrite');
    const store = transaction.objectStore(STORE_NAME);
    const request = store.delete(id);

    request.onsuccess = () => {
      resolve();
    };

    request.onerror = () => {
      reject(new Error('Failed to delete tab'));
    };

    transaction.oncomplete = () => {
      db.close();
    };
  });
};

/**
 * Clear all tabs
 */
export const clearAllTabs = async (userId: string): Promise<void> => {
  await flushAllPendingTabSaves(userId);
  const db = await openDB(userId);

  return new Promise((resolve, reject) => {
    const transaction = db.transaction([STORE_NAME], 'readwrite');
    const store = transaction.objectStore(STORE_NAME);
    const request = store.clear();

    request.onsuccess = () => {
      resolve();
    };

    request.onerror = () => {
      reject(new Error('Failed to clear tabs'));
    };

    transaction.oncomplete = () => {
      db.close();
    };
  });
};
