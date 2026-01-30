import { useState, useEffect } from 'react';
import { initSheet, sendChat, uploadFile } from '../utils/api';
import { useTabsStore } from '../stores/useTabsStore';

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
}

export type SheetData = unknown[][];

export const useProcureState = () => {
  const { getActiveTab, updateTabData, activeTabId } = useTabsStore();
  const [isThinking, setIsThinking] = useState(false);

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
      const response = await sendChat(message, sheetData, nextHistory);
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

  return {
    sheetData,
    chatHistory,
    isThinking,
    handleSendMessage,
    handleFileUpload,
    handleSheetDataChange,
    clearChatHistory,
  };
};
