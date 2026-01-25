import React, { useEffect, useRef, useState } from 'react';
import type { ChatMessage } from '../hooks/useProcureState';

interface ChatPanelProps {
  history: ChatMessage[];
  onSend: (msg: string) => void;
  onFileUpload: (file: File) => void;
  isThinking: boolean;
  onClear: () => void;
}

const ChatPanel: React.FC<ChatPanelProps> = ({ history, onSend, onFileUpload, isThinking, onClear }) => {
  const [input, setInput] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isThinking) return;
    onSend(input);
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
    onSend(input);
    setInput("");
  };

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = '0px';
    const next = Math.min(el.scrollHeight, 120);
    el.style.height = `${Math.max(next, 50)}px`;
  }, [input]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
  }, [history.length, isThinking]);

  return (
    <div className="flex flex-col h-full border-r border-gray-200 bg-gray-50/50">
      <div className="h-14 flex items-center justify-between px-4 bg-white border-b border-gray-100">
        <div className="flex items-center gap-2 font-semibold text-gray-700">
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5 text-gray-600">
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 3.75H7.5A2.25 2.25 0 0 0 5.25 6v1.5m13.5-3.75H16.5A2.25 2.25 0 0 0 14.25 6v1.5m-9 13.5h13.5A2.25 2.25 0 0 0 21 18.75V10.5A2.25 2.25 0 0 0 18.75 8.25H5.25A2.25 2.25 0 0 0 3 10.5v8.25A2.25 2.25 0 0 0 5.25 21ZM9 8.25V6m6 2.25V6M8.25 13.5h.008v.008H8.25V13.5Zm3.75 0h.008v.008H12V13.5Zm3.75 0h.008v.008h-.008V13.5Z" />
          </svg>
          智能采购助手
        </div>
        <button
          type="button"
          onClick={onClear}
          className="text-gray-400 hover:text-red-500 transition-colors"
          title="清空上下文"
          disabled={isThinking}
        >
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
            <path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" />
          </svg>
        </button>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-4">
        {history.length === 0 && (
          <div className="mx-auto bg-gray-200/60 text-gray-500 text-xs py-1 px-3 rounded-full w-fit">
            上传 Excel 或输入报价开始对话
          </div>
        )}

        {history.map((msg, i) => {
          if (msg.role === 'system') {
            return (
              <div key={i} className="mx-auto bg-gray-200/60 text-gray-500 text-xs py-1 px-3 rounded-full w-fit">
                {msg.content}
              </div>
            );
          }

          if (msg.role === 'user') {
            return (
              <div key={i} className="bg-blue-600 text-white shadow-md rounded-2xl rounded-tr-none px-4 py-3 max-w-[85%] ml-auto whitespace-pre-wrap break-words">
                {msg.content}
              </div>
            );
          }

          return (
            <div key={i} className="bg-white border border-gray-100 shadow-sm text-gray-800 rounded-2xl rounded-tl-none px-4 py-3 max-w-[85%] whitespace-pre-wrap break-words">
              {msg.content}
            </div>
          );
        })}

        {isThinking === true && (
          <div className="flex items-center gap-1 bg-white border border-gray-100 shadow-sm rounded-2xl rounded-tl-none px-4 py-3 w-fit">
            <span className="w-2 h-2 bg-blue-400 rounded-full animate-bounce [animation-delay:-0.3s]"></span>
            <span className="w-2 h-2 bg-blue-400 rounded-full animate-bounce [animation-delay:-0.15s]"></span>
            <span className="w-2 h-2 bg-blue-400 rounded-full animate-bounce"></span>
            <span className="text-xs text-gray-400 ml-2">AI 正在根据表格内容计算...</span>
          </div>
        )}
      </div>

      <div className="p-4 bg-white border-t border-gray-100">
        <form onSubmit={handleSubmit}>
          <div
            className="flex flex-col border border-gray-200 rounded-xl focus-within:ring-2 focus-within:ring-blue-100 focus-within:border-blue-400 transition-all bg-white overflow-hidden shadow-sm"
            onDrop={handleDrop}
            onDragOver={(e) => e.preventDefault()}
          >
            <textarea
              ref={textareaRef}
              className="w-full p-3 min-h-[50px] max-h-[120px] resize-none outline-none text-sm text-gray-700 placeholder-gray-400"
              placeholder="输入报价信息，或拖入文件..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={isThinking}
              rows={2}
            />
            <div className="flex justify-between items-center px-2 pb-2">
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="hover:bg-gray-100 p-2 rounded-lg text-gray-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  disabled={isThinking}
                  title="上传文件"
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

              <button
                type="submit"
                className={
                  isThinking
                    ? 'bg-gray-200 text-gray-400 rounded-lg p-2 transition-colors cursor-not-allowed'
                    : 'bg-blue-600 hover:bg-blue-700 text-white rounded-lg p-2 transition-colors'
                }
                disabled={isThinking || !input.trim()}
                title="发送"
              >
                {isThinking ? (
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" className="w-5 h-5 animate-spin" aria-hidden="true">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 0 1 8-8v4a4 4 0 0 0-4 4H4Z"></path>
                  </svg>
                ) : (
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5">
                    <path d="M3.105 2.289a.75.75 0 0 0-.826.95l1.414 4.925A1.5 1.5 0 0 0 5.135 9.25h6.115a.75.75 0 0 1 0 1.5H5.135a1.5 1.5 0 0 0-1.442 1.086l-1.414 4.926a.75.75 0 0 0 .826.95 28.89 28.89 0 0 0 15.293-7.154.75.75 0 0 0 0-1.115A28.897 28.897 0 0 0 3.105 2.289Z" />
                  </svg>
                )}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
};

export default ChatPanel;
