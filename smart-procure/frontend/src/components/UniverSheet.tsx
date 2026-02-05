import React, { useCallback, useEffect, useRef } from 'react';
import "@univerjs/design/lib/index.css";
import "@univerjs/ui/lib/index.css";
import "@univerjs/sheets-ui/lib/index.css";
import "@univerjs/docs-ui/lib/index.css";
import "@univerjs/sheets-formula-ui/lib/index.css";
import "@univerjs/sheets-filter-ui/lib/index.css";

import { Univer, UniverInstanceType, LocaleType, Tools } from "@univerjs/core";
import { FUniver } from '@univerjs/core/facade';
import { defaultTheme } from "@univerjs/design";
import { UniverFormulaEnginePlugin } from '@univerjs/engine-formula';
import { UniverRenderEnginePlugin } from "@univerjs/engine-render";
import { UniverSheetsPlugin } from "@univerjs/sheets";
import { UniverSheetsUIPlugin } from "@univerjs/sheets-ui";
import { UniverSheetsFormulaPlugin } from "@univerjs/sheets-formula";
import { UniverSheetsFormulaUIPlugin } from "@univerjs/sheets-formula-ui";
import { UniverSheetsFilterPlugin } from "@univerjs/sheets-filter";
import { UniverSheetsFilterUIPlugin } from "@univerjs/sheets-filter-ui";
import { UniverUIPlugin } from "@univerjs/ui";
import { UniverDocsPlugin } from "@univerjs/docs";
import { UniverDocsUIPlugin } from "@univerjs/docs-ui";

import '@univerjs/ui/facade';
import '@univerjs/sheets/facade';
import '@univerjs/sheets-ui/facade';

import DesignZhCN from '@univerjs/design/locale/zh-CN';
import UIZhCN from '@univerjs/ui/locale/zh-CN';
import SheetsZhCN from '@univerjs/sheets/locale/zh-CN';
import SheetsUIZhCN from '@univerjs/sheets-ui/locale/zh-CN';
import DocsUIZhCN from '@univerjs/docs-ui/locale/zh-CN';
import SheetsFormulaZhCN from '@univerjs/sheets-formula/locale/zh-CN';
import SheetsFormulaUIZhCN from '@univerjs/sheets-formula-ui/locale/zh-CN';
import SheetsFilterUIZhCN from '@univerjs/sheets-filter-ui/locale/zh-CN';

interface UniverSheetProps {
  data: unknown[][];
  onDataChange?: (next: unknown[][]) => void;
  onRowClick?: (rowIndex: number) => void;
}

const UniverSheet: React.FC<UniverSheetProps> = ({ data, onDataChange, onRowClick }) => {
  const onDataChangeRef = useRef<typeof onDataChange>(onDataChange);
  const onRowClickRef = useRef<typeof onRowClick>(onRowClick);
  const containerRef = useRef<HTMLDivElement>(null);
  const univerRef = useRef<Univer | null>(null);
  const univerAPIRef = useRef<ReturnType<typeof FUniver.newAPI> | null>(null);
  const lifecycleDisposableRef = useRef<{ dispose: () => void } | null>(null);
  const readyRef = useRef(false);
  const pendingDataRef = useRef<unknown[][] | null>(null);
  const latestDataRef = useRef<unknown[][]>([]);
  const mountNodeRef = useRef<HTMLDivElement | null>(null);
  const workbookIdRef = useRef<string | null>(null);
  const readyPollTimerRef = useRef<number | null>(null);
  const isProgrammaticWriteRef = useRef(false);
  const isUserEditRef = useRef(false); // 标记数据变化是否来自用户编辑
  const changeListenerDisposableRef = useRef<{ dispose: () => void } | null>(null);
  const selectionListenerDisposableRef = useRef<{ dispose: () => void } | null>(null);

  const writeDataToActiveSheet = useCallback((univerAPI: ReturnType<typeof FUniver.newAPI>, next: unknown[][]) => {
    const rowCount = Math.max(next.length, 20);
    let maxCol = 0;
    next.forEach((row) => {
      if (Array.isArray(row) && row.length > maxCol) maxCol = row.length;
    });
    const colCount = Math.max(maxCol, 26);

    // Support both plain values and formula objects
    const normalized: (string | { f?: string; v?: unknown })[][] = Array.from({ length: rowCount }, () =>
      Array.from({ length: colCount }, () => '')
    );

    next.forEach((row, r) => {
      if (!Array.isArray(row)) return;
      row.forEach((cell, c) => {
        if (r >= rowCount || c >= colCount) return;

        // Handle null/undefined
        if (cell === null || cell === undefined) {
          normalized[r][c] = '';
          return;
        }

        // Handle formula objects (e.g., {f: "=SUM(A1:A10)", v: 100})
        if (typeof cell === 'object' && cell !== null && 'f' in cell) {
          normalized[r][c] = cell as { f?: string; v?: unknown };
          return;
        }

        // Handle string values that might be formulas
        const cellStr = String(cell);
        if (cellStr.startsWith('=')) {
          // This is a formula - preserve it as a formula object
          normalized[r][c] = { f: cellStr };
          return;
        }

        // Regular value
        normalized[r][c] = cellStr;
      });
    });

    return Promise.resolve().then(async () => {
      const wb = univerAPI.getActiveWorkbook();
      if (!wb) return;
      const ws = wb.getActiveSheet();
      if (!ws) return;

      isProgrammaticWriteRef.current = true;

      if (typeof ws.setRowCount === 'function') {
        await Promise.resolve(ws.setRowCount(Math.max(rowCount, 2000)));
      }
      if (typeof ws.setColumnCount === 'function') {
        await Promise.resolve(ws.setColumnCount(Math.max(colCount, 200)));
      }

      const range = ws.getRange(0, 0, rowCount, colCount);
      await Promise.resolve(range.setValues(normalized as any));
      try {
        ws.refreshCanvas?.();
      } catch {
        void 0;
      }

      // 延迟重置标志，确保 Univer 内部的异步操作完成
      // 使用较长的延迟时间避免后续的 mutation 被误处理
      setTimeout(() => {
        isProgrammaticWriteRef.current = false;
      }, 200);
    });
  }, []);

  const applyRangeToData = useCallback((
    base: unknown[][],
    range: { startRow: number; endRow: number; startColumn: number; endColumn: number },
    value: unknown
  ) => {
    const rowCount = Math.max(base.length, range.endRow + 1, 20);
    let maxCol = 0;
    base.forEach((r) => {
      if (Array.isArray(r) && r.length > maxCol) maxCol = r.length;
    });
    const colCount = Math.max(maxCol, range.endColumn + 1, 26);

    const next: unknown[][] = Array.from({ length: rowCount }, (_, r) =>
      Array.from({ length: colCount }, (_, c) => (base[r]?.[c] ?? ''))
    );

    const hasCellValue = (v: unknown): v is { v?: unknown; f?: string } =>
      typeof v === 'object' && v !== null && ('v' in v || 'f' in v);

    const writeCell = (r: number, c: number, v: unknown) => {
      if (r < 0 || c < 0 || r >= rowCount || c >= colCount) return;

      // Handle formula/value objects from Univerjs
      if (hasCellValue(v)) {
        // If it has a formula, preserve the formula
        if (v.f) {
          next[r][c] = v.f;
        } else {
          next[r][c] = v.v ?? '';
        }
        return;
      }

      // Handle regular values
      next[r][c] = v ?? '';
    };

    if (Array.isArray(value)) {
      const values = value as unknown[];
      for (let r = range.startRow; r <= range.endRow; r++) {
        for (let c = range.startColumn; c <= range.endColumn; c++) {
          const vr = values[r - range.startRow];
          const vc = Array.isArray(vr) ? (vr as unknown[])[c - range.startColumn] : vr;
          writeCell(r, c, vc);
        }
      }
    } else {
      for (let r = range.startRow; r <= range.endRow; r++) {
        for (let c = range.startColumn; c <= range.endColumn; c++) {
          writeCell(r, c, value);
        }
      }
    }

    return next;
  }, []);

  // Initialize Univer (Run once)
  useEffect(() => {
    if (!containerRef.current || univerRef.current) return;

    try {
        if (mountNodeRef.current) {
          mountNodeRef.current.remove();
          mountNodeRef.current = null;
        }
        const mountNode = document.createElement('div');
        mountNode.style.width = '100%';
        mountNode.style.height = '100%';
        mountNode.id = `univer-sheet-mount-${Date.now()}`;
        mountNode.tabIndex = 0;
        mountNode.style.outline = 'none';
        containerRef.current.appendChild(mountNode);
        mountNodeRef.current = mountNode;

        // Initialize Univer with Locale
        const univer = new Univer({
          theme: defaultTheme,
          locale: LocaleType.ZH_CN,
          locales: {
            [LocaleType.ZH_CN]: Tools.deepMerge(
              DesignZhCN,
              UIZhCN,
              SheetsZhCN,
              SheetsUIZhCN,
              DocsUIZhCN,
              SheetsFormulaZhCN,
              SheetsFormulaUIZhCN,
              SheetsFilterUIZhCN
            ),
          },
        });
        univerRef.current = univer;

        // Register Plugins
        univer.registerPlugin(UniverRenderEnginePlugin);
        univer.registerPlugin(UniverFormulaEnginePlugin);
        univer.registerPlugin(UniverUIPlugin, {
          container: mountNode.id,
          header: true,
          footer: false,
        });

        univer.registerPlugin(UniverDocsPlugin, {
          hasScroll: false,
        });
        univer.registerPlugin(UniverDocsUIPlugin);
        
        univer.registerPlugin(UniverSheetsPlugin);
        univer.registerPlugin(UniverSheetsUIPlugin);
        univer.registerPlugin(UniverSheetsFormulaPlugin);
        univer.registerPlugin(UniverSheetsFormulaUIPlugin);
        univer.registerPlugin(UniverSheetsFilterPlugin);
        univer.registerPlugin(UniverSheetsFilterUIPlugin);
        univer.createUnit(UniverInstanceType.UNIVER_SHEET, {});

        const univerAPI = FUniver.newAPI(univer);
        univerAPIRef.current = univerAPI;
        workbookIdRef.current = null;

        const ensureWorkbookReady = () => {
          if (!univerAPIRef.current) return false;
          const api = univerAPIRef.current;
          try {
            const active = api.getActiveWorkbook();
            if (!active) return false;
            if (!workbookIdRef.current) {
              workbookIdRef.current = active.getId?.() ?? null;
            }
            const sheet = api.getActiveWorkbook()?.getActiveSheet?.();
            if (!sheet) return false;
            return true;
          } catch (e) {
            console.warn('Ensure workbook failed:', e);
            return false;
          }
        };

        const flushPending = () => {
          if (!ensureWorkbookReady()) return;
          readyRef.current = true;
          if (!pendingDataRef.current) return;
          const next = pendingDataRef.current;
          pendingDataRef.current = null;
          void Promise.resolve(writeDataToActiveSheet(univerAPI, next)).catch((e: unknown) => {
            console.error("Failed to update workbook:", e);
          });
        };

        if (changeListenerDisposableRef.current) {
          try {
            changeListenerDisposableRef.current.dispose();
          } catch {
            void 0;
          }
          changeListenerDisposableRef.current = null;
        }

        if (typeof univerAPI.onCommandExecuted === 'function') {
          const disposable = univerAPI.onCommandExecuted((command: unknown) => {
            if (isProgrammaticWriteRef.current) return;
            if (!command || typeof command !== 'object') return;
            const cmd = command as { id?: unknown; params?: unknown };

            // 只监听 mutation，不监听 command
            // 用户编辑、清除、撤销/重做等操作都会触发 mutation
            // 不需要单独处理 command，避免重复触发 onDataChange
            const isMutationSetValues = cmd.id === 'sheet.mutation.set-range-values';

            if (!isMutationSetValues) return;

            console.log('[UniverSheet] Data change command:', cmd.id, 'params:', JSON.stringify(cmd.params));

            const params =
              cmd.params && typeof cmd.params === 'object'
                ? (cmd.params as { range?: unknown; value?: unknown; cellValue?: unknown })
                : undefined;

            // 处理 mutation 的 cellValue 格式 (用于撤销/重做)
            // 格式: {"cellValue":{"5":{"2":{"v":"1",...}}}} 表示行5列2的值
            if (isMutationSetValues && params?.cellValue) {
              const cellValue = params.cellValue as Record<string, Record<string, { v?: unknown; f?: string }>>;
              const rowKeys = Object.keys(cellValue).map(Number).sort((a, b) => a - b);
              console.log('[UniverSheet] cellValue mutation - rows:', rowKeys.join(','), 'total:', rowKeys.length);

              const next = [...latestDataRef.current.map(row => [...row])];

              // 确保数组足够大
              const maxRow = Math.max(...Object.keys(cellValue).map(Number), next.length - 1);
              while (next.length <= maxRow) {
                next.push([]);
              }

              for (const [rowStr, cols] of Object.entries(cellValue)) {
                const rowIdx = parseInt(rowStr, 10);
                if (isNaN(rowIdx) || rowIdx < 0) continue;

                const maxCol = Math.max(...Object.keys(cols).map(Number), (next[rowIdx]?.length || 0) - 1);
                while ((next[rowIdx]?.length || 0) <= maxCol) {
                  next[rowIdx] = next[rowIdx] || [];
                  next[rowIdx].push('');
                }

                for (const [colStr, cell] of Object.entries(cols)) {
                  const colIdx = parseInt(colStr, 10);
                  if (isNaN(colIdx) || colIdx < 0) continue;

                  // 提取值：优先公式，其次值
                  let value: unknown = '';
                  if (cell?.f) {
                    value = cell.f;
                  } else if (cell?.v !== undefined && cell?.v !== null) {
                    value = cell.v;
                  }
                  next[rowIdx][colIdx] = value;
                }
              }

              latestDataRef.current = next;
              isUserEditRef.current = true; // 标记这是用户编辑
              console.log('[UniverSheet] Applied cellValue mutation, calling onDataChange');
              onDataChangeRef.current?.(next);
            }
          });
          changeListenerDisposableRef.current = disposable;
        }

        // Add row click listener
        if (typeof univerAPI.onCommandExecuted === 'function') {
          const selectionDisposable = univerAPI.onCommandExecuted((command: unknown) => {
            if (!command || typeof command !== 'object') return;
            const cmd = command as { id?: unknown; params?: unknown };

            // Log all commands to see what's being executed
            console.log('[UniverSheet] Command executed:', cmd.id);

            // Listen for selection change commands
            if (cmd.id === 'sheet.command.set-selections' || cmd.id === 'sheet.operation.set-selections') {
              console.log('[UniverSheet] Selection command detected!');
              try {
                const activeSheet = univerAPI.getActiveWorkbook()?.getActiveSheet();
                if (!activeSheet) {
                  console.log('[UniverSheet] No active sheet');
                  return;
                }

                const selection = activeSheet.getSelection();
                if (!selection) {
                  console.log('[UniverSheet] No selection');
                  return;
                }

                const range = selection.getActiveRange();
                if (!range) {
                  console.log('[UniverSheet] No active range');
                  return;
                }

                // Access the internal _range object to get row number
                const rangeData = (range as any)._range;
                if (!rangeData) {
                  console.log('[UniverSheet] No _range data');
                  return;
                }

                const startRow = rangeData.startRow;
                console.log('[UniverSheet] Selected row:', startRow);

                if (typeof startRow === 'number' && startRow >= 0) {
                  console.log('[UniverSheet] Calling onRowClick with row:', startRow);
                  onRowClickRef.current?.(startRow);
                }
              } catch (e) {
                console.warn('Failed to handle row click:', e);
              }
            }
          });
          selectionListenerDisposableRef.current = selectionDisposable;
        }

        if (
          typeof univerAPI.addEvent === 'function' &&
          univerAPI.Event?.LifeCycleChanged &&
          univerAPI.Enum?.LifecycleStages
        ) {
          const lifecycleDisposable = univerAPI.addEvent(
            univerAPI.Event.LifeCycleChanged,
            ({ stage }: { stage: unknown }) => {
              const rendered =
                stage === univerAPI.Enum.LifecycleStages.Rendered ||
                stage === univerAPI.Enum.LifecycleStages.Steady;
              if (!rendered) return;
              flushPending();
              mountNodeRef.current?.focus();
            }
          );
          lifecycleDisposableRef.current = lifecycleDisposable;
        } else {
          if (readyPollTimerRef.current !== null) {
            window.clearTimeout(readyPollTimerRef.current);
            readyPollTimerRef.current = null;
          }
          let attempts = 0;
          const retry = () => {
            if (readyRef.current) return;
            flushPending();
            attempts += 1;
            if (attempts >= 20) return;
            readyPollTimerRef.current = window.setTimeout(retry, 150);
          };
          retry();
        }

    } catch (error) {
        console.error("Failed to initialize Univer:", error);
    }

    // Cleanup on unmount
    return () => {
        readyRef.current = false;
        pendingDataRef.current = null;
        workbookIdRef.current = null;

        if (readyPollTimerRef.current !== null) {
          window.clearTimeout(readyPollTimerRef.current);
          readyPollTimerRef.current = null;
        }

        if (changeListenerDisposableRef.current) {
          try {
            changeListenerDisposableRef.current.dispose();
          } catch (e) {
            console.warn("Univer change listener dispose error:", e);
          }
          changeListenerDisposableRef.current = null;
        }

        if (selectionListenerDisposableRef.current) {
          try {
            selectionListenerDisposableRef.current.dispose();
          } catch (e) {
            console.warn("Univer selection listener dispose error:", e);
          }
          selectionListenerDisposableRef.current = null;
        }

        if (lifecycleDisposableRef.current) {
          try {
            lifecycleDisposableRef.current.dispose();
          } catch (e) {
            console.warn("Univer lifecycle dispose error:", e);
          }
          lifecycleDisposableRef.current = null;
        }

        const univerToDispose = univerRef.current;
        univerRef.current = null;
        univerAPIRef.current = null;

        if (mountNodeRef.current) {
          mountNodeRef.current.remove();
          mountNodeRef.current = null;
        }

        if (univerToDispose) {
            setTimeout(() => {
              try {
                univerToDispose.dispose();
              } catch (e) {
                console.warn("Univer dispose error:", e);
              }
            }, 0);
        }
    };
  }, [applyRangeToData, writeDataToActiveSheet]);

  useEffect(() => {
    onDataChangeRef.current = onDataChange;
  }, [onDataChange]);

  // Update Workbook Data
  useEffect(() => {
    if (!data) return;
    latestDataRef.current = data;

    // 如果数据变化来自用户编辑，不要写回 Univer（避免污染撤销栈）
    if (isUserEditRef.current) {
      console.log('[UniverSheet] Skipping write-back for user edit');
      isUserEditRef.current = false;
      return;
    }

    const univer = univerRef.current;
    const univerAPI = univerAPIRef.current;
    if (!univer || !univerAPI) return;
    if (!readyRef.current) {
      pendingDataRef.current = data;
      return;
    }

    try {
        void Promise.resolve(writeDataToActiveSheet(univerAPI, data)).catch((e: unknown) => {
          console.error("Failed to update workbook:", e);
        });

    } catch (e) {
        console.error("Failed to update workbook:", e);
    }
  }, [data, writeDataToActiveSheet]);

  return (
    <div className="h-full w-full flex flex-col relative">
        <div ref={containerRef} className="flex-1 w-full relative" />
    </div>
  );
};

export default UniverSheet;
