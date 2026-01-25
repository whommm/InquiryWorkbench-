import { useState, useEffect } from 'react';
import { initSheet, sendChat, uploadFile } from '../utils/api';

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
}

export type SheetData = unknown[][];

export const useProcureState = () => {
  const [sheetData, setSheetData] = useState<SheetData>([]);
  const [chatHistory, setChatHistory] = useState<ChatMessage[]>([]);
  const [isThinking, setIsThinking] = useState(false);

  useEffect(() => {
    // Load initial data
    const loadInit = async () => {
      try {
        const res = await initSheet();
        if (res && res.data) {
          setSheetData(res.data);
        }
      } catch (e) {
        console.error("Failed to load init data", e);
        setChatHistory(prev => [...prev, { role: 'assistant', content: '连接后端失败，请检查 Docker 服务。' }]);
      }
    };
    loadInit();
  }, []);

  const handleSendMessage = async (message: string) => {
    const nextHistory = [...chatHistory, { role: 'user' as const, content: message }];
    setChatHistory(nextHistory);
    setIsThinking(true);

    try {
      const response = await sendChat(message, sheetData, nextHistory);
      
      let reply = "";
      if (response.action === "ASK") {
        reply = response.content || "请提供更多信息";
      } else if (response.action === "WRITE") {
        reply = response.content || "更新成功";
        if (response.updated_sheet) {
          setSheetData(response.updated_sheet);
        }
      }
      
      setChatHistory(prev => [...prev, { role: 'assistant', content: reply }]);
      
    } catch (e) {
      setChatHistory(prev => [...prev, { role: 'assistant', content: `错误: ${(e as Error).message}` }]);
    } finally {
      setIsThinking(false);
    }
  };

  const handleFileUpload = async (file: File) => {
    setIsThinking(true);
    try {
        setChatHistory(prev => [...prev, { role: 'user', content: `正在上传文件: ${file.name}...` }]);
        const res = await uploadFile(file);
        if (res && res.data) {
            setSheetData(res.data);
            setChatHistory(prev => [...prev, { role: 'assistant', content: `文件 ${file.name} 上传并解析成功！` }]);
        }
    } catch (e) {
        console.error("Upload failed", e);
        setChatHistory(prev => [...prev, { role: 'assistant', content: `文件上传失败: ${(e as Error).message}` }]);
    } finally {
        setIsThinking(false);
    }
  };

  const handleSheetDataChange = (next: SheetData) => {
    setSheetData(next);
  };

  const clearChatHistory = () => {
    setChatHistory([]);
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
