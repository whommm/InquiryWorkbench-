import React from 'react';

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description?: string;
  confirmText?: string;
  cancelText?: string;
  danger?: boolean;
  loading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

const ConfirmDialog: React.FC<ConfirmDialogProps> = ({
  open,
  title,
  description,
  confirmText = '确认',
  cancelText = '取消',
  danger = false,
  loading = false,
  onConfirm,
  onCancel,
}) => {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[80] bg-black/45 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="modal-shell w-full max-w-md p-5">
        <h3 className="text-base font-semibold text-gray-900">{title}</h3>
        {description && <p className="mt-2 text-sm text-gray-600">{description}</p>}
        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="px-3 py-1.5 rounded-md border border-gray-200 text-sm text-gray-600 hover:bg-gray-50"
          >
            {cancelText}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={loading}
            className={`px-3 py-1.5 rounded-md text-sm disabled:opacity-60 ${
              danger ? 'btn-danger' : 'btn-primary'
            }`}
          >
            {loading ? '处理中...' : confirmText}
          </button>
        </div>
      </div>
    </div>
  );
};

export default ConfirmDialog;

