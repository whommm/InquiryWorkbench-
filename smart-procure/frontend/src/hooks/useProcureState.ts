import { useState, useEffect } from 'react';
import { initSheet, sendChat, uploadFile, saveSheet, extractSuppliersFromSheet } from '../utils/api';
import { useTabsStore } from '../stores/useTabsStore';
import type { ToolConfig } from '../components/ToolConfigPanel';

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
}

export type SheetData = unknown[][];

// 默认工具配置
const DEFAULT_TOOL_CONFIGS: ToolConfig[] = [
  { id: 'locate_row', name: '行定位', description: '按物料/品牌/型号定位表格行', enabled: true },
  { id: 'get_row_slot_snapshot', name: '槽位查询', description: '获取行的报价槽位状态', enabled: true },
  { id: 'supplier_lookup', name: '供应商查询', description: '从数据库查询供应商信息', enabled: true },
  { id: 'web_search_supplier', name: '网络搜索', description: '在互联网上搜索供应商信息', enabled: true },
  { id: 'web_browse', name: '网页浏览', description: '使用浏览器访问网页提取信息', enabled: true },
];

export const useProcureState = () => {
  const { getActiveTab, updateTabData, activeTabId } = useTabsStore();
  const [isThinking, setIsThinking] = useState(false);
  const [toolConfigs, setToolConfigs] = useState<ToolConfig[]>(DEFAULT_TOOL_CONFIGS);

  const activeTab = getActiveTab();
  const sheetData = activeTab?.sheetData || [];
  const chatHistory = activeTab?.chatHistory || [];

  useEffect(() => {
    // Load initial data only if active tab is empty
    const loadInit = async () => {
      if (!activeTab || activeTab.sheetData.length > 0) return;

      try {
        const res = await initSheet();
        if (res && res.data && activeTabId) {
          await updateTabData(activeTabId, {
            sheetData: res.data,
            isDirty: false
          });
        }
      } catch (e) {
        console.error("Failed to load init data", e);
        if (activeTabId) {
          await updateTabData(activeTabId, {
            chatHistory: [...chatHistory, {
              role: 'assistant',
              content: '连接后端失败，请检查 Docker 服务。'
            }]
          });
        }
      }
    };
    loadInit();
  }, [activeTabId]);

  const handleSendMessage = async (message: string) => {
    if (!activeTabId) return;

    const nextHistory = [...chatHistory, { role: 'user' as const, content: message }];

    // Update chat history immediately
    await updateTabData(activeTabId, {
      chatHistory: nextHistory
    });

    setIsThinking(true);

    try {
      console.log('[Chat] 发送消息:', message);
      const enabledTools = toolConfigs.filter(t => t.enabled).map(t => t.id);
      const response = await sendChat(message, sheetData, nextHistory, enabledTools);
      console.log('[Chat] 收到响应:', response);

      if (!response || !response.action) {
        throw new Error('服务器返回的响应格式不正确');
      }

      let reply = "";
      const updates: { chatHistory: ChatMessage[]; sheetData?: unknown[][] } = {
        chatHistory: [...nextHistory, { role: 'assistant', content: '' }]
      };

      if (response.action === "ASK") {
        reply = response.content || "请提供更多信息";
      } else if (response.action === "WRITE") {
        reply = response.content || "更新成功";
        if (response.updated_sheet) {
          console.log('[Chat] 更新表格数据，行数:', response.updated_sheet.length);
          updates.sheetData = response.updated_sheet;
        } else {
          console.warn('[Chat] WRITE动作但没有updated_sheet数据');
        }
      } else {
        console.warn('[Chat] 未知的action类型:', response.action);
      }

      updates.chatHistory = [...nextHistory, { role: 'assistant', content: reply }];

      // 更新标签页数据（保存到 IndexedDB，标记为 isDirty）
      // 用户需要手动点击保存按钮才会同步到后端
      console.log('[Chat] 更新标签页数据...');
      await updateTabData(activeTabId, updates);
      console.log('[Chat] 标签页数据更新完成');

    } catch (e) {
      console.error('[Chat] 处理失败:', e);
      await updateTabData(activeTabId, {
        chatHistory: [...nextHistory, { role: 'assistant', content: `错误: ${(e as Error).message}` }]
      });
    } finally {
      setIsThinking(false);
    }
  };

  const handleFileUpload = async (file: File) => {
    if (!activeTabId) return;

    setIsThinking(true);
    try {
        await updateTabData(activeTabId, {
          chatHistory: [...chatHistory, { role: 'user', content: `正在上传文件: ${file.name}...` }]
        });

        const res = await uploadFile(file);
        if (res && res.data) {
            // Extract filename without extension
            const fileName = file.name.replace(/\.(xlsx?|xls)$/i, '');

            // Build success message with supplier recommendations
            let successMessage = `文件 ${file.name} 上传并解析成功！`;

            if (res.recommended_suppliers && res.recommended_suppliers.length > 0) {
              successMessage += '\n\n📋 **根据文件内容，为您推荐以下供应商：**\n\n';

              res.recommended_suppliers.forEach((supplier: any, index: number) => {
                successMessage += `${index + 1}. **${supplier.company_name}**\n`;
                successMessage += `   联系人：${supplier.contact_name || '未知'}\n`;
                successMessage += `   电话：${supplier.contact_phone}\n`;
                successMessage += `   匹配原因：${supplier.match_reason}\n`;
                successMessage += `   历史报价次数：${supplier.quote_count} 次\n`;
                if (supplier.last_quote_date) {
                  successMessage += `   最后报价时间：${new Date(supplier.last_quote_date).toLocaleDateString('zh-CN')}\n`;
                }
                successMessage += '\n';
              });

              successMessage += '💡 您可以直接在聊天框中输入报价信息，例如："第2行，单价5000，找张三"';
            }

            await updateTabData(activeTabId, {
              name: fileName,  // Update tab name with uploaded filename
              sheetData: res.data,
              chatHistory: [...chatHistory,
                { role: 'user', content: `正在上传文件: ${file.name}...` },
                { role: 'assistant', content: successMessage }
              ]
            });
        }
    } catch (e) {
        console.error("Upload failed", e);
        await updateTabData(activeTabId, {
          chatHistory: [...chatHistory,
            { role: 'user', content: `正在上传文件: ${file.name}...` },
            { role: 'assistant', content: `文件上传失败: ${(e as Error).message}` }
          ]
        });
    } finally {
        setIsThinking(false);
    }
  };

  const handleSheetDataChange = async (next: SheetData) => {
    if (!activeTabId) return;
    await updateTabData(activeTabId, {
      sheetData: next
    });
  };

  const clearChatHistory = async () => {
    if (!activeTabId) return;
    await updateTabData(activeTabId, {
      chatHistory: []
    });
  };

  const handleToolToggle = (toolId: string) => {
    setToolConfigs(prev => prev.map(tool =>
      tool.id === toolId ? { ...tool, enabled: !tool.enabled } : tool
    ));
  };

  const handleManualSave = async (): Promise<{ success: boolean; newSupplierCount?: number }> => {
    if (!activeTabId || !activeTab) return { success: false };

    try {
      // 1. 保存表格数据到后端
      await saveSheet({
        id: activeTab.id,
        name: activeTab.name,
        sheet_data: activeTab.sheetData,
        chat_history: activeTab.chatHistory,
      });

      // 2. 提取并沉淀供应商数据（异步，不阻塞）
      let newSupplierCount = 0;
      try {
        const result = await extractSuppliersFromSheet(activeTab.sheetData);
        newSupplierCount = result.new_count || 0;
        if (newSupplierCount > 0) {
          console.log(`✓ 发现 ${newSupplierCount} 个新供应商，后台提取中...`);
        }
      } catch (extractError) {
        console.warn('供应商提取失败:', extractError);
      }

      await updateTabData(activeTabId, { isDirty: false });
      console.log(`✓ 手动保存成功: ${activeTab.name}`);
      return { success: true, newSupplierCount };
    } catch (error) {
      console.error('❌ 手动保存失败:', error);
      return { success: false };
    }
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
