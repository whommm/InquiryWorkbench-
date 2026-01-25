import React, { useCallback, useEffect, useRef } from 'react';
import "@univerjs/design/lib/index.css";
import "@univerjs/ui/lib/index.css";
import "@univerjs/sheets-ui/lib/index.css";
import "@univerjs/docs-ui/lib/index.css";
import "@univerjs/sheets-formula-ui/lib/index.css";

import { Univer, UniverInstanceType, LocaleType, Tools } from "@univerjs/core";
import { FUniver } from '@univerjs/core/facade';
import { defaultTheme } from "@univerjs/design";
import { UniverFormulaEnginePlugin } from '@univerjs/engine-formula';
import { UniverRenderEnginePlugin } from "@univerjs/engine-render";
import { UniverSheetsPlugin } from "@univerjs/sheets";
import { UniverSheetsUIPlugin } from "@univerjs/sheets-ui";
import { UniverSheetsFormulaPlugin } from "@univerjs/sheets-formula";
import { UniverSheetsFormulaUIPlugin } from "@univerjs/sheets-formula-ui";
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

interface UniverSheetProps {
  data: unknown[][];
  onDataChange?: (next: unknown[][]) => void;
}

const UniverSheet: React.FC<UniverSheetProps> = ({ data, onDataChange }) => {
  const onDataChangeRef = useRef<typeof onDataChange>(onDataChange);
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
  const changeListenerDisposableRef = useRef<{ dispose: () => void } | null>(null);

  const writeDataToActiveSheet = useCallback((univerAPI: ReturnType<typeof FUniver.newAPI>, next: unknown[][]) => {
    const rowCount = Math.max(next.length, 20);
    let maxCol = 0;
    next.forEach((row) => {
      if (Array.isArray(row) && row.length > maxCol) maxCol = row.length;
    });
    const colCount = Math.max(maxCol, 26);
    const normalized: string[][] = Array.from({ length: rowCount }, () =>
      Array.from({ length: colCount }, () => '')
    );
    next.forEach((row, r) => {
      if (!Array.isArray(row)) return;
      row.forEach((cell, c) => {
        if (r >= rowCount || c >= colCount) return;
        normalized[r][c] = cell === null || cell === undefined ? '' : String(cell);
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
      await Promise.resolve(range.setValues(normalized));
      try {
        ws.refreshCanvas?.();
      } catch {
        void 0;
      }

      setTimeout(() => {
        isProgrammaticWriteRef.current = false;
      }, 0);
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

    const hasCellValue = (v: unknown): v is { v?: unknown } =>
      typeof v === 'object' && v !== null && 'v' in v;

    const writeCell = (r: number, c: number, v: unknown) => {
      if (r < 0 || c < 0 || r >= rowCount || c >= colCount) return;
      if (hasCellValue(v)) {
        next[r][c] = v.v ?? '';
        return;
      }
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
              SheetsFormulaUIZhCN
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
            if (cmd.id !== 'sheet.command.set-range-values') return;

            const params =
              cmd.params && typeof cmd.params === 'object'
                ? (cmd.params as { range?: unknown; value?: unknown })
                : undefined;
            const range = params?.range as
              | {
                  unitId?: unknown;
                  startRow?: unknown;
                  endRow?: unknown;
                  startColumn?: unknown;
                  endColumn?: unknown;
                }
              | undefined;
            if (!range) return;
            const activeUnitId = univerAPI.getActiveWorkbook?.()?.getId?.() as string | undefined;
            const rangeUnitId = typeof range.unitId === 'string' ? range.unitId : undefined;
            if (rangeUnitId && activeUnitId && rangeUnitId !== activeUnitId) return;

            const normalizedRange = {
              startRow: typeof range.startRow === 'number' ? range.startRow : 0,
              endRow:
                typeof range.endRow === 'number'
                  ? range.endRow
                  : typeof range.startRow === 'number'
                    ? range.startRow
                    : 0,
              startColumn: typeof range.startColumn === 'number' ? range.startColumn : 0,
              endColumn:
                typeof range.endColumn === 'number'
                  ? range.endColumn
                  : typeof range.startColumn === 'number'
                    ? range.startColumn
                    : 0,
            };
            const next = applyRangeToData(latestDataRef.current ?? [], normalizedRange, params?.value);
            latestDataRef.current = next;
            onDataChangeRef.current?.(next);
          });
          changeListenerDisposableRef.current = disposable;
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
        <div ref={containerRef} className="flex-1 w-full overflow-hidden relative" />
    </div>
  );
};

export default UniverSheet;
