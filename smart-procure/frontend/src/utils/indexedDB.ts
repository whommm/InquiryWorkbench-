/**
 * IndexedDB utility for storing inquiry tabs locally
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

const DB_NAME = 'SmartProcureDB';
const DB_VERSION = 1;
const STORE_NAME = 'tabs';

/**
 * Open IndexedDB connection
 */
export const openDB = (): Promise<IDBDatabase> => {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);

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
export const saveTab = async (tab: InquiryTab): Promise<void> => {
  const db = await openDB();

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

/**
 * Get a single tab by ID
 */
export const getTab = async (id: string): Promise<InquiryTab | null> => {
  const db = await openDB();

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
export const getAllTabs = async (): Promise<InquiryTab[]> => {
  const db = await openDB();

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
export const deleteTab = async (id: string): Promise<void> => {
  const db = await openDB();

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
export const clearAllTabs = async (): Promise<void> => {
  const db = await openDB();

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
