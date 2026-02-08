import React, { useEffect, useRef, useState } from 'react';
import type { ChatMessage } from '../hooks/useProcureState';
import type { ToolConfig } from './ToolConfigPanel';
import ToolConfigPanel from './ToolConfigPanel';

interface ChatPanelProps {
  messages: ChatMessage[];
  onSendMessage: (msg: string) => Promise<void>;
  onFileUpload: (file: File) => Promise<void>;
  isThinking: boolean;
  toolConfigs: ToolConfig[];
  onToolToggle: (toolId: string) => void;
  onClearHistory?: () => void;
  onCollapse?: () => void;
}

const ChatPanel: React.FC<ChatPanelProps> = ({
  messages,
  onSendMessage,
  onFileUpload,
  isThinking,
  toolConfigs,
  onToolToggle,
  onClearHistory,
  onCollapse
}) => {
  const [input, setInput] = useState("");

  const [showToolConfig, setShowToolConfig] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isThinking) return;
    onSendMessage(input);
    setInput("");
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
        onFileUpload(e.target.files[0]);
    }
    // Reset
    if (fileInputRef.current) {
        fileInputRef.current.value = "";
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (isThinking) return;
    const file = e.dataTransfer.files?.[0];
    if (!file) return;
    onFileUpload(file);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key !== 'Enter') return;
    if (e.shiftKey) return;
    e.preventDefault();
    if (!input.trim() || isThinking) return;
    onSendMessage(input);
    setInput("");
  };


  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = '0px';
    const next = Math.min(el.scrollHeight, 200);
    el.style.height = `${Math.max(next, 100)}px`;
  }, [input]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
  }, [messages.length, isThinking]);

  return (
    <div className="flex flex-col h-full bg-white border-r border-gray-200 shadow-lg">
      {/* 头部 */}
      <div className="p-3 border-b border-gray-100 bg-gray-50 flex items-center justify-between relative">
        <div className="flex items-center gap-3">
          <span className="font-semibold text-gray-700 flex items-center">
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5 text-emerald-500 mr-2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 0 0-2.456 2.456ZM16.894 20.567 16.5 21.75l-.394-1.183a2.25 2.25 0 0 0-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 0 0 1.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 0 0 1.423 1.423l1.183.394-1.183.394a2.25 2.25 0 0 0-1.423 1.423Z" />
            </svg>
            AI 助手
          </span>
          <button
          type="button"
          onClick={() => setShowToolConfig(!showToolConfig)}
          className={`flex items-center gap-1 px-2 py-1 text-xs rounded-md transition-all ${
            showToolConfig ? 'text-emerald-600 bg-emerald-50' : 'text-gray-500 hover:text-emerald-600 hover:bg-emerald-50'
          }`}
          title="工具配置"
        >
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-4 h-4">
            <path strokeLinecap="round" strokeLinejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.325.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 0 1 1.37.49l1.296 2.247a1.125 1.125 0 0 1-.26 1.431l-1.003.827c-.293.241-.438.613-.43.992a7.723 7.723 0 0 1 0 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 0 1-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 0 1-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.94-1.11.94h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 0 1-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 0 1-1.369-.49l-1.297-2.247a1.125 1.125 0 0 1 .26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 0 1 0-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 0 1-.26-1.43l1.297-2.247a1.125 1.125 0 0 1 1.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.28Z" />
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
          </svg>
          <span>工具</span>
        </button>
        <button
          type="button"
          onClick={onClearHistory}
          className="flex items-center gap-1 px-2 py-1 text-xs text-gray-500 hover:text-orange-600 hover:bg-orange-50 rounded-md transition-all disabled:opacity-40 disabled:cursor-not-allowed"
          disabled={isThinking || messages.length === 0}
          title="清空聊天记录"
        >
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-4 h-4">
            <path strokeLinecap="round" strokeLinejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" />
          </svg>
          <span>清空</span>
        </button>
        </div>

        {/* 折叠按钮 */}
        <button
          type="button"
          onClick={onCollapse}
          className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-md transition-all"
          title="收起面板"
        >
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-4 h-4">
            <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5 8.25 12l7.5-7.5" />
          </svg>
        </button>
      </div>

      {/* Tool Config Panel */}
      {showToolConfig && (
        <ToolConfigPanel
          configs={toolConfigs}
          onToggle={onToolToggle}
          onClose={() => setShowToolConfig(false)}
        />
      )}

      {/* 消息列表 */}
      <div 
        ref={scrollRef}
        className="flex-1 overflow-y-auto p-4 space-y-4 scroll-smooth"
      >
        {messages.map((msg, idx) => (
          <div 
            key={idx} 
            className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}
          >
            <div className={`
              max-w-[90%] rounded-lg p-3 text-sm shadow-sm
              ${msg.role === 'user' 
                ? 'bg-emerald-600 text-white rounded-br-none' 
                : 'bg-gray-100 text-gray-800 rounded-bl-none'
              }
            `}>
              <div className="whitespace-pre-wrap leading-relaxed">{msg.content}</div>
            </div>
            {msg.role === 'assistant' && (
              <span className="text-[10px] text-gray-400 mt-1 ml-1">AI 助手</span>
            )}
            {msg.role === 'user' && (
              <span className="text-[10px] text-gray-400 mt-1 mr-1">我</span>
            )}
          </div>
        ))}
        {isThinking && (
          <div className="flex items-start">
            <div className="bg-gray-100 text-gray-800 rounded-lg rounded-bl-none p-3 shadow-sm">
              <div className="flex space-x-1.5 items-center h-5">
                <div className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce [animation-delay:-0.3s]"></div>
                <div className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce [animation-delay:-0.15s]"></div>
                <div className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce"></div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* 输入框 */}
      <div className="p-4 bg-white border-t border-gray-100">
        <form onSubmit={handleSubmit}>
          <div className="relative">
            <textarea
              ref={textareaRef}
              className="w-full border border-gray-300 rounded-lg pl-3 pr-20 py-2 text-sm focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500 resize-none shadow-inner"
              placeholder="输入报价信息或指令，例如：'第2行，单价5000，含税含运，货期3天'"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={isThinking}
              rows={8}
              onDrop={handleDrop}
              onDragOver={(e) => e.preventDefault()}
            />
            <button
              type="submit"
              className="absolute bottom-2 right-2 text-emerald-600 hover:bg-emerald-50 p-1.5 rounded-full transition disabled:opacity-50 disabled:cursor-not-allowed"
              disabled={isThinking || !input.trim()}
              title="发送"
            >
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5">
                <path d="M3.105 2.289a.75.75 0 0 0-.826.95l1.414 4.925A1.5 1.5 0 0 0 5.135 9.25h6.115a.75.75 0 0 1 0 1.5H5.135a1.5 1.5 0 0 0-1.442 1.086l-1.414 4.926a.75.75 0 0 0 .826.95 28.89 28.89 0 0 0 15.293-7.154.75.75 0 0 0 0-1.115A28.897 28.897 0 0 0 3.105 2.289Z" />
              </svg>
            </button>
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="absolute bottom-2 right-11 text-gray-400 hover:text-gray-600 p-1.5 rounded-full transition disabled:opacity-50 disabled:cursor-not-allowed"
              disabled={isThinking}
              title="上传 Excel"
            >
              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
                <path strokeLinecap="round" strokeLinejoin="round" d="M18.375 12.739l-7.693 7.693a4.5 4.5 0 0 1-6.364-6.364l10.94-10.94a3 3 0 1 1 4.243 4.243L9.75 16.5a1.5 1.5 0 0 1-2.121-2.121l8.19-8.19" />
              </svg>
            </button>
            <input
              type="file"
              ref={fileInputRef}
              className="hidden"
              accept=".xlsx, .xls"
              onChange={handleFileChange}
            />
          </div>
        </form>
      </div>
    </div>
  );
};

export default ChatPanel;
