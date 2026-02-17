import { useState, useEffect } from 'react';
import { toast } from 'sonner';
import { initSheet, sendChat, uploadFile, saveSheet, extractSuppliersFromSheet } from '../utils/api';
import { useTabsStore } from '../stores/useTabsStore';
import type { ToolConfig } from '../components/ToolConfigPanel';

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
}

export type SheetData = unknown[][];
const EMPTY_SHEET_DATA: SheetData = [];
const EMPTY_CHAT_HISTORY: ChatMessage[] = [];

interface UploadRecommendedSupplier {
  company_name?: string;
  contact_name?: string | null;
  contact_phone?: string | null;
  match_reason?: string;
  quote_count?: number;
  last_quote_date?: string | null;
}

const DEFAULT_TOOL_CONFIGS: ToolConfig[] = [
  { id: 'locate_row', name: '行定位', description: '按物料关键词定位行', enabled: true },
  { id: 'get_row_slot_snapshot', name: '槽位快照', description: '读取当前行报价槽位状态', enabled: true },
  { id: 'supplier_lookup', name: '供应商查询', description: '从库内检索供应商信息', enabled: true },
  { id: 'web_search_supplier', name: '网络搜索', description: '联网搜索供应商线索', enabled: true },
  { id: 'web_browse', name: '网页浏览', description: '访问网页提取关键信息', enabled: true },
];

export const useProcureState = () => {
  const { getActiveTab, updateTab, activeTabId } = useTabsStore();
  const [isThinking, setIsThinking] = useState(false);
  const [toolConfigs, setToolConfigs] = useState<ToolConfig[]>(DEFAULT_TOOL_CONFIGS);

  const activeTab = getActiveTab();
  const sheetData = activeTab?.sheetData ?? EMPTY_SHEET_DATA;
  const chatHistory = activeTab?.chatHistory ?? EMPTY_CHAT_HISTORY;

  useEffect(() => {
    const loadInit = async () => {
      if (!activeTab || activeTab.sheetData.length > 0 || !activeTabId) return;
      try {
        const res = await initSheet();
        if (res?.data) {
          await updateTab(activeTabId, {
            sheetData: res.data,
            isDirty: false,
          });
        }
      } catch (e) {
        console.error('Failed to load init data', e);
        await updateTab(activeTabId, {
          chatHistory: [
            ...chatHistory,
            { role: 'assistant', content: '初始化数据失败，请检查后端服务状态。' },
          ],
        });
      }
    };

    void loadInit();
  }, [activeTab, activeTabId, chatHistory, updateTab]);

  const handleSendMessage = async (message: string) => {
    if (!activeTabId) return;

    const nextHistory = [...chatHistory, { role: 'user' as const, content: message }];
    await updateTab(activeTabId, { chatHistory: nextHistory });
    setIsThinking(true);

    try {
      const enabledTools = toolConfigs.filter((t) => t.enabled).map((t) => t.id);
      const response = await sendChat(message, sheetData, nextHistory, enabledTools);

      if (!response || !response.action) {
        throw new Error('服务端响应格式不正确');
      }

      let reply = '';
      const updates: { chatHistory: ChatMessage[]; sheetData?: unknown[][] } = {
        chatHistory: [...nextHistory, { role: 'assistant', content: '' }],
      };

      if (response.action === 'ASK') {
        reply = response.content || '请提供更多信息';
      } else if (response.action === 'WRITE') {
        reply = response.content || '更新成功';
        if (response.updated_sheet) {
          updates.sheetData = response.updated_sheet;
        }
      } else {
        reply = response.content || '操作已完成';
      }

      updates.chatHistory = [...nextHistory, { role: 'assistant', content: reply }];
      await updateTab(activeTabId, updates);
    } catch (e) {
      console.error('Chat failed:', e);
      await updateTab(activeTabId, {
        chatHistory: [...nextHistory, { role: 'assistant', content: `错误: ${(e as Error).message}` }],
      });
    } finally {
      setIsThinking(false);
    }
  };

  const handleFileUpload = async (file: File) => {
    if (!activeTabId) return;

    setIsThinking(true);
    try {
      await updateTab(activeTabId, {
        chatHistory: [...chatHistory, { role: 'user', content: `正在上传文件: ${file.name}...` }],
      });

      const res = await uploadFile(file);
      if (!res?.data) return;

      const fileName = file.name.replace(/\.(xlsx?|xls)$/i, '');
      let successMessage = `文件 ${file.name} 上传并解析成功。`;

      if (Array.isArray(res.recommended_suppliers) && res.recommended_suppliers.length > 0) {
        successMessage += '\n\n推荐供应商：\n';
        const suppliers = res.recommended_suppliers as UploadRecommendedSupplier[];
        suppliers.forEach((supplier, index: number) => {
          successMessage += `${index + 1}. ${supplier.company_name || '未命名供应商'}，联系人: ${supplier.contact_name || '未知'}，电话: ${supplier.contact_phone || '未知'}\n`;
        });
      }

      await updateTab(activeTabId, {
        name: fileName,
        sheetData: res.data,
        chatHistory: [
          ...chatHistory,
          { role: 'user', content: `正在上传文件: ${file.name}...` },
          { role: 'assistant', content: successMessage },
        ],
      });
    } catch (e) {
      console.error('Upload failed', e);
      await updateTab(activeTabId, {
        chatHistory: [
          ...chatHistory,
          { role: 'user', content: `正在上传文件: ${file.name}...` },
          { role: 'assistant', content: `文件上传失败: ${(e as Error).message}` },
        ],
      });
    } finally {
      setIsThinking(false);
    }
  };

  const handleSheetDataChange = async (next: SheetData) => {
    if (!activeTabId) return;
    await updateTab(activeTabId, {
      sheetData: next,
      isDirty: true,
    });
  };

  const clearChatHistory = async () => {
    if (!activeTabId) return;
    await updateTab(activeTabId, { chatHistory: [] });
  };

  const handleToolToggle = (toolId: string) => {
    setToolConfigs((prev) =>
      prev.map((tool) => (tool.id === toolId ? { ...tool, enabled: !tool.enabled } : tool))
    );
  };

  const handleManualSave = async (): Promise<{ success: boolean; newSupplierCount?: number; conflict?: boolean }> => {
    if (!activeTabId || !activeTab) return { success: false };

    const basePayload = {
      id: activeTab.id,
      name: activeTab.name,
      sheet_data: activeTab.sheetData,
      chat_history: activeTab.chatHistory,
      expected_updated_at: activeTab.serverUpdatedAt || undefined,
    };

    let saveResult: { updated_at?: string | null } | null = null;

    try {
      saveResult = await saveSheet(basePayload);
    } catch (error) {
      const status = (error as { response?: { status?: number } })?.response?.status;
      if (status !== 409) {
        console.error('Manual save failed:', error);
        return { success: false };
      }

      const detail = (error as { response?: { data?: { detail?: Record<string, unknown> } } })?.response?.data?.detail;
      const serverUpdatedAt = typeof detail?.server_updated_at === 'string' ? detail.server_updated_at : '';
      const timeLabel = serverUpdatedAt
        ? new Date(serverUpdatedAt).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })
        : '未知时间';

      toast.warning(`检测到版本冲突（服务端时间：${timeLabel}），已保留本地改动，请手动处理后再保存`);
      return { success: false, conflict: true };
    }

    let newSupplierCount = 0;
    try {
      const result = await extractSuppliersFromSheet(activeTab.sheetData);
      newSupplierCount = result.new_count || 0;
    } catch (extractError) {
      console.warn('Supplier extract failed:', extractError);
    }

    await updateTab(activeTabId, {
      isDirty: false,
      serverUpdatedAt: saveResult?.updated_at || activeTab.serverUpdatedAt || null,
    });

    return { success: true, newSupplierCount };
  };

  return {
    sheetData,
    chatHistory,
    isThinking,
    isDirty: activeTab?.isDirty ?? false,
    toolConfigs,
    handleSendMessage,
    handleFileUpload,
    handleSheetDataChange,
    clearChatHistory,
    handleToolToggle,
    handleManualSave,
  };
};
