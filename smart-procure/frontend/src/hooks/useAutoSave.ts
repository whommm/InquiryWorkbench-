/**
 * Auto-save hook - DISABLED
 *
 * 自动保存已禁用，改为手动保存模式。
 * 数据仍会保存到 IndexedDB 本地缓存，但不会自动同步到后端。
 * 用户需要点击"保存"按钮手动保存到服务器。
 */
export const useAutoSave = (_tabId: string | null, _interval: number = 3000) => {
  // 自动保存已禁用 - 保留此 hook 以保持 API 兼容性
  // 数据变更会自动保存到 IndexedDB（通过 useTabsStore.updateTabData）
  // 但不会自动同步到后端服务器
};
