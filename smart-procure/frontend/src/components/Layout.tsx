import React, { useEffect, useRef, useState } from 'react';

interface LayoutProps {
  left: React.ReactNode;
  right: React.ReactNode;
  collapsed?: boolean;
  onToggleCollapse?: () => void;
}

const Layout: React.FC<LayoutProps> = ({ left, right, collapsed = false, onToggleCollapse }) => {
  const minSidebarWidth = 360;
  const maxSidebarWidth = 560;

  const clampWidth = (value: number) =>
    Math.min(maxSidebarWidth, Math.max(minSidebarWidth, value));

  const [sidebarWidth, setSidebarWidth] = useState(() => clampWidth(420));
  const isDraggingRef = useRef(false);
  const dragStartXRef = useRef(0);
  const dragStartWidthRef = useRef(0);

  useEffect(() => {
    const handlePointerMove = (e: PointerEvent) => {
      if (!isDraggingRef.current) return;
      const delta = e.clientX - dragStartXRef.current;
      setSidebarWidth(clampWidth(dragStartWidthRef.current + delta));
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
  }, [maxSidebarWidth, minSidebarWidth]);

  const startDragging = (e: React.PointerEvent<HTMLDivElement>) => {
    isDraggingRef.current = true;
    dragStartXRef.current = e.clientX;
    dragStartWidthRef.current = sidebarWidth;
    document.body.style.cursor = 'col-resize';
    document.body.classList.add('select-none');
  };

  return (
    <div className="h-full w-full overflow-hidden bg-gray-50">
      <div className="flex h-full w-full">
        {/* 折叠时显示展开按钮 */}
        {collapsed ? (
          <div className="h-full shrink-0 flex items-center">
            <button
              onClick={onToggleCollapse}
              className="h-full w-8 bg-gray-100 hover:bg-gray-200 border-r border-gray-200 flex items-center justify-center transition-colors"
              title="展开对话栏"
            >
              <svg className="w-4 h-4 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 5l7 7-7 7M5 5l7 7-7 7" />
              </svg>
            </button>
          </div>
        ) : (
          <>
            <div
              className="h-full shrink-0 relative"
              style={{ width: `${sidebarWidth}px` }}
            >
              {/* 折叠按钮 - 右上角 */}
              <button
                onClick={onToggleCollapse}
                className="absolute top-2 right-2 z-10 w-7 h-7 bg-gray-200 hover:bg-gray-300 rounded flex items-center justify-center transition-colors"
                title="隐藏对话栏"
              >
                <svg className="w-4 h-4 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
                </svg>
              </button>
              {left}
            </div>

            <div
              className="relative h-full w-2 shrink-0 bg-transparent"
              onPointerDown={startDragging}
              role="separator"
              aria-orientation="vertical"
              aria-label="调整侧边栏宽度"
              tabIndex={0}
            >
              <div className="absolute left-1/2 top-0 h-full w-px -translate-x-1/2 bg-gray-200" />
              <div className="absolute left-1/2 top-1/2 h-14 w-1 -translate-x-1/2 -translate-y-1/2 rounded-full bg-gray-300/80" />
            </div>
          </>
        )}

        <div className="min-w-0 flex-1 h-full">
          <div className="h-full bg-white overflow-hidden">{right}</div>
        </div>
      </div>
    </div>
  );
};

export default Layout;
