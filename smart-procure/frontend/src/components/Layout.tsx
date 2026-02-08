import React, { useEffect, useRef, useState } from 'react';
import Header from './Header';

interface LayoutProps {
  showChat: boolean;
  onToggleChat: () => void;
  sidebarContent: React.ReactNode;
  mainContent: React.ReactNode;
  chatPanel: React.ReactNode;
  rightPanel?: React.ReactNode;
  showRightPanel?: boolean;
  onToggleRightPanel?: () => void;
  children?: React.ReactNode;
}

const Layout: React.FC<LayoutProps> = ({
  showChat,
  onToggleChat,
  sidebarContent,
  mainContent,
  chatPanel,
  rightPanel,
  showRightPanel = false,
  onToggleRightPanel,
  children
}) => {
  const minChatWidth = 360;
  const maxChatWidth = 600;

  const clampWidth = (value: number) =>
    Math.min(maxChatWidth, Math.max(minChatWidth, value));

  const [chatWidth, setChatWidth] = useState(() => clampWidth(400));
  const isDraggingRef = useRef(false);
  const dragStartXRef = useRef(0);
  const dragStartWidthRef = useRef(0);

  useEffect(() => {
    const handlePointerMove = (e: PointerEvent) => {
      if (!isDraggingRef.current) return;
      // Dragging left increases width (since chat is on the left)
      // Wait, in previous design Chat was on Left.
      // Let's stick to Chat on Left for consistency with "sidebar".
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
  }, [maxChatWidth, minChatWidth]);

  const startDragging = (e: React.PointerEvent<HTMLDivElement>) => {
    isDraggingRef.current = true;
    dragStartXRef.current = e.clientX;
    dragStartWidthRef.current = chatWidth;
    document.body.style.cursor = 'col-resize';
    document.body.classList.add('select-none');
  };

  return (
    <div className="h-full w-full overflow-hidden bg-gray-50 flex flex-col">
      {/* Global Header */}
      <Header onToggleSidebar={onToggleChat} />
      
      {/* Main Content Area */}
      <div className="flex-1 flex overflow-hidden relative">
        {/* Left Sidebar (Navigation) */}
        <div className="w-16 flex-shrink-0 bg-white border-r border-gray-200 flex flex-col items-center py-4 z-20">
           {sidebarContent}
        </div>

        {/* Chat Panel (Collapsible) */}
        <div 
          className={`h-full bg-white shadow-xl z-10 transition-all duration-300 ease-in-out flex flex-col relative border-r border-gray-200 ${
            !showChat ? 'w-0 opacity-0 overflow-hidden' : 'opacity-100'
          }`}
          style={{ width: !showChat ? 0 : `${chatWidth}px` }}
        >
          {chatPanel}
          
          {/* Resize Handle */}
          {showChat && (
            <div
              className="absolute right-0 top-0 h-full w-1 cursor-col-resize hover:bg-emerald-500/50 transition-colors z-20 group"
              onPointerDown={startDragging}
            >
              <div className="absolute top-1/2 -translate-y-1/2 right-0 w-1 h-8 bg-gray-300 rounded-full group-hover:bg-emerald-500 transition-colors" />
            </div>
          )}
        </div>

        {/* Main Workspace (UniverSheet) */}
        <div className="flex-1 h-full overflow-hidden bg-gray-50 p-2 sm:p-4 relative">
          {/* Floating Toggle Button (When Chat Collapsed) */}
          {!showChat && (
            <button
              onClick={onToggleChat}
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

        {/* Right Panel (Recommend Panel - Collapsible) */}
        <div
          className={`h-full bg-white shadow-xl z-10 transition-all duration-300 ease-in-out flex flex-col relative border-l border-gray-200 ${
            !showRightPanel ? 'w-0 opacity-0 overflow-hidden' : 'opacity-100'
          }`}
          style={{ width: showRightPanel ? '400px' : 0 }}
        >
          {rightPanel}
        </div>
      </div>
      
      {/* Overlays (History, Supplier, Recommend Panels) */}
      {children}
    </div>
  );
};

export default Layout;
