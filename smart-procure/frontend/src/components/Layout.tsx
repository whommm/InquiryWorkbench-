import React, { useEffect, useRef, useState } from 'react';

interface LayoutProps {
  left: React.ReactNode;
  right: React.ReactNode;
}

const Layout: React.FC<LayoutProps> = ({ left, right }) => {
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
        <div
          className="h-full shrink-0"
          style={{ width: `${sidebarWidth}px` }}
        >
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

        <div className="min-w-0 flex-1 h-full">
          <div className="h-full bg-white overflow-hidden">{right}</div>
        </div>
      </div>
    </div>
  );
};

export default Layout;
