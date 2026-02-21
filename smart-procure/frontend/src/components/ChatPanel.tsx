import React, { useEffect, useRef, useState } from 'react';
import type { ChatMessage } from '../hooks/useProcureState';
import type { ToolConfig } from './ToolConfigPanel';
import ToolConfigPanel from './ToolConfigPanel';
import ConfirmDialog from './ConfirmDialog';

interface ChatPanelProps {
  messages: ChatMessage[];
  onSendMessage: (msg: string) => Promise<void>;
  onFileUpload: (file: File) => Promise<void>;
  onClearHistory: () => Promise<void>;
  isThinking: boolean;
  toolConfigs: ToolConfig[];
  onToolToggle: (toolId: string) => void;
}

const trailingPunctuation = /[),.;!?]+$/;

const renderMessageWithLinks = (content: string) => {
  const lines = content.split('\n');
  const pattern = /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)|(https?:\/\/[^\s]+)/g;

  return lines.map((line, lineIdx) => {
    const parts: React.ReactNode[] = [];
    let cursor = 0;
    let match: RegExpExecArray | null;
    pattern.lastIndex = 0;

    while ((match = pattern.exec(line)) !== null) {
      const full = match[0];
      const mdText = match[1];
      const mdUrl = match[2];
      const rawUrl = match[3];
      const start = match.index;

      if (start > cursor) {
        parts.push(line.slice(cursor, start));
      }

      if (mdText && mdUrl) {
        parts.push(
          <a
            key={`md-${lineIdx}-${start}`}
            href={mdUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-emerald-700 underline break-all"
          >
            {mdText}
          </a>
        );
      } else if (rawUrl) {
        const cleanUrl = rawUrl.replace(trailingPunctuation, '');
        const suffix = rawUrl.slice(cleanUrl.length);
        parts.push(
          <a
            key={`url-${lineIdx}-${start}`}
            href={cleanUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-emerald-700 underline break-all"
          >
            {cleanUrl}
          </a>
        );
        if (suffix) {
          parts.push(suffix);
        }
      } else {
        parts.push(full);
      }

      cursor = start + full.length;
    }

    if (cursor < line.length) {
      parts.push(line.slice(cursor));
    }

    return (
      <React.Fragment key={`line-${lineIdx}`}>
        {parts}
        {lineIdx < lines.length - 1 ? <br /> : null}
      </React.Fragment>
    );
  });
};

const ChatPanel: React.FC<ChatPanelProps> = ({
  messages,
  onSendMessage,
  onFileUpload,
  onClearHistory,
  isThinking,
  toolConfigs,
  onToolToggle,
}) => {
  const [input, setInput] = useState('');
  const [showToolConfig, setShowToolConfig] = useState(false);
  const [confirmClearOpen, setConfirmClearOpen] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isThinking) return;
    void onSendMessage(input);
    setInput('');
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      void onFileUpload(e.target.files[0]);
    }
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (isThinking) return;
    const file = e.dataTransfer.files?.[0];
    if (!file) return;
    void onFileUpload(file);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key !== 'Enter' || e.shiftKey) return;
    e.preventDefault();
    if (!input.trim() || isThinking) return;
    void onSendMessage(input);
    setInput('');
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
      <div className="p-3 border-b border-gray-100 bg-gray-50 flex items-center gap-3 relative">
        <span className="font-semibold text-gray-700 flex items-center">
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5 text-emerald-500 mr-2">
            <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09Z" />
          </svg>
          AI 助手
        </span>

        <button
          type="button"
          onClick={() => setShowToolConfig(!showToolConfig)}
          aria-label="打开工具配置"
          className={`flex items-center gap-1 px-2 py-1 text-xs rounded-md transition-all ${
            showToolConfig ? 'text-emerald-600 bg-emerald-50' : 'text-gray-500 hover:text-emerald-600 hover:bg-emerald-50'
          }`}
          title="工具配置"
        >
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-4 h-4">
            <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 6h3m-7.5 6h12m-9 6h6" />
          </svg>
          <span>工具</span>
        </button>

        <button
          type="button"
          onClick={() => setConfirmClearOpen(true)}
          aria-label="清空聊天记录"
          className="flex items-center gap-1 px-2 py-1 text-xs text-gray-500 hover:text-orange-600 hover:bg-orange-50 rounded-md transition-all disabled:opacity-40 disabled:cursor-not-allowed"
          disabled={isThinking || messages.length === 0}
          title="清空聊天记录"
        >
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-4 h-4">
            <path strokeLinecap="round" strokeLinejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166" />
          </svg>
          <span>清空</span>
        </button>
      </div>

      {showToolConfig && (
        <ToolConfigPanel
          configs={toolConfigs}
          onToggle={onToolToggle}
          onClose={() => setShowToolConfig(false)}
        />
      )}

      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-4 scroll-smooth">
        {messages.map((msg, idx) => (
          <div key={idx} className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
            <div
              className={`max-w-[90%] rounded-lg p-3 text-sm shadow-sm ${
                msg.role === 'user' ? 'bg-emerald-600 text-white rounded-br-none' : 'bg-gray-100 text-gray-800 rounded-bl-none'
              }`}
            >
              <div className="whitespace-pre-wrap leading-relaxed">
                {msg.role === 'assistant' ? renderMessageWithLinks(msg.content) : msg.content}
              </div>
            </div>
            <span className="text-xs text-gray-400 mt-1.5 ml-1">{msg.role === 'assistant' ? 'AI 助手' : '我'}</span>
          </div>
        ))}

        {isThinking && (
          <div className="flex items-start">
            <div className="bg-gray-100 text-gray-800 rounded-lg rounded-bl-none p-3 shadow-sm">
              <div className="flex space-x-1.5 items-center h-5">
                <div className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce [animation-delay:-0.3s]" />
                <div className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce [animation-delay:-0.15s]" />
                <div className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" />
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="p-4 bg-white border-t border-gray-100">
        <form onSubmit={handleSubmit}>
          <div className="relative">
            <textarea
              ref={textareaRef}
              className="w-full border border-gray-300 rounded-lg pl-3 pr-20 py-2 text-sm focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500 resize-none shadow-inner"
              placeholder="输入报价信息或指令，例如：第2行，单价5000，含税含运，货期3天"
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
              aria-label="发送消息"
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
              aria-label="上传 Excel"
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

      <ConfirmDialog
        open={confirmClearOpen}
        title="清空当前会话?"
        description="该操作会删除当前标签页的聊天记录，且无法恢复。"
        confirmText="确认清空"
        cancelText="取消"
        danger
        onCancel={() => setConfirmClearOpen(false)}
        onConfirm={() => {
          setConfirmClearOpen(false);
          void onClearHistory();
        }}
      />
    </div>
  );
};

export default ChatPanel;
