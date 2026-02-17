import React, { useEffect, useRef, useState } from 'react';
import Header from './Header';

interface LayoutProps {
  showChat: boolean;
  onToggleChat: () => void;
  onToggleRightPanel?: () => void;
  sidebarContent: React.ReactNode;
  mainContent: React.ReactNode;
  chatPanel: React.ReactNode;
  rightPanel?: React.ReactNode;
  showRightPanel?: boolean;
  children?: React.ReactNode;
}

const Layout: React.FC<LayoutProps> = ({
  showChat,
  onToggleChat,
  onToggleRightPanel,
  sidebarContent,
  mainContent,
  chatPanel,
  rightPanel,
  showRightPanel = false,
  children,
}) => {
  const minChatWidth = 360;
  const maxChatWidth = 600;
  const [isMobile, setIsMobile] = useState(() => window.innerWidth < 1024);

  const clampWidth = (value: number) => Math.min(maxChatWidth, Math.max(minChatWidth, value));

  const [chatWidth, setChatWidth] = useState(() => clampWidth(400));
  const isDraggingRef = useRef(false);
  const dragStartXRef = useRef(0);
  const dragStartWidthRef = useRef(0);

  useEffect(() => {
    const onResize = () => setIsMobile(window.innerWidth < 1024);
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  useEffect(() => {
    const handlePointerMove = (e: PointerEvent) => {
      if (!isDraggingRef.current) return;
      const delta = e.clientX - dragStartXRef.current;
      setChatWidth(clampWidth(dragStartWidthRef.current + delta));
    };

    const stopDragging = () => {
      if (!isDraggingRef.current) return;
      isDraggingRef.current = false;
      document.body.style.cursor = '';
      document.body.classList.remove('select-none');
    };

    window.addEventListener('pointermove', handlePointerMove);
    window.addEventListener('pointerup', stopDragging);
    window.addEventListener('pointercancel', stopDragging);

    return () => {
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('pointerup', stopDragging);
      window.removeEventListener('pointercancel', stopDragging);
    };
  }, []);

  const startDragging = (e: React.PointerEvent<HTMLDivElement>) => {
    isDraggingRef.current = true;
    dragStartXRef.current = e.clientX;
    dragStartWidthRef.current = chatWidth;
    document.body.style.cursor = 'col-resize';
    document.body.classList.add('select-none');
  };

  return (
    <div className="h-full w-full overflow-hidden bg-gray-50 flex flex-col">
      <Header onToggleSidebar={onToggleChat} />

      <div className="flex-1 flex overflow-hidden relative">
        {!isMobile && sidebarContent}

        {!isMobile && (
          <div
            className={`h-full bg-white shadow-xl z-10 transition-all duration-300 ease-in-out flex flex-col relative border-r border-gray-200 ${
              !showChat ? 'w-0 opacity-0 overflow-hidden' : 'opacity-100'
            }`}
            style={{ width: !showChat ? 0 : `${chatWidth}px` }}
          >
            {showChat && (
              <button
                type="button"
                onClick={onToggleChat}
                aria-label="收起 AI 助手"
                className="absolute top-2 right-3 z-30 h-7 w-7 rounded-md border border-gray-200 bg-white text-gray-500 hover:text-emerald-600 hover:border-emerald-200 hover:bg-emerald-50 transition-colors"
                title="收起助手"
              >
                <svg className="mx-auto h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                </svg>
              </button>
            )}

            {chatPanel}

            {showChat && (
              <div
                className="absolute right-0 top-0 h-full w-1 cursor-col-resize hover:bg-emerald-500/50 transition-colors z-20 group"
                onPointerDown={startDragging}
                role="separator"
                aria-orientation="vertical"
                aria-label="调整聊天面板宽度"
              >
                <div className="absolute top-1/2 -translate-y-1/2 right-0 w-1 h-8 bg-gray-300 rounded-full group-hover:bg-emerald-500 transition-colors" />
              </div>
            )}
          </div>
        )}

        <div className="flex-1 h-full overflow-hidden bg-gray-50 p-2 sm:p-4 relative">
          {!showChat && !isMobile && (
            <button
              onClick={onToggleChat}
              aria-label="展开 AI 助手"
              className="absolute left-4 top-4 z-20 p-2 bg-white rounded-lg shadow-md border border-gray-200 text-gray-500 hover:text-emerald-600 hover:border-emerald-200 transition-all"
              title="展开助手"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </button>
          )}

          <div className="h-full w-full bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden relative">
            {mainContent}
          </div>
        </div>

        {!isMobile && (
          <div
            className={`h-full bg-white shadow-xl z-10 transition-all duration-300 ease-in-out flex flex-col relative border-l border-gray-200 ${
              !showRightPanel ? 'w-0 opacity-0 overflow-hidden' : 'opacity-100'
            }`}
            style={{ width: !showRightPanel ? 0 : '360px' }}
          >
            {rightPanel}
          </div>
        )}
      </div>

      {isMobile && showChat && (
        <div className="fixed inset-0 z-40 bg-black/45" onClick={onToggleChat} aria-hidden="true">
          <div
            className="absolute right-0 top-0 h-full w-[min(92vw,420px)] bg-white shadow-2xl border-l border-gray-200"
            onClick={(e) => e.stopPropagation()}
          >
            {chatPanel}
          </div>
        </div>
      )}

      {isMobile && showRightPanel && (
        <div
          className="fixed inset-0 z-40 bg-black/45"
          onClick={() => onToggleRightPanel?.()}
          aria-hidden="true"
        >
          <div
            className="absolute right-0 top-0 h-full w-[min(92vw,380px)] bg-white shadow-2xl border-l border-gray-200"
            onClick={(e) => e.stopPropagation()}
          >
            {rightPanel}
          </div>
        </div>
      )}

      {children}
    </div>
  );
};

export default Layout;

