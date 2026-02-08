import React from 'react';

export interface ToolConfig {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
}

interface ToolConfigPanelProps {
  configs: ToolConfig[];
  onToggle: (toolId: string) => void;
  onClose: () => void;
}

const ToolConfigPanel: React.FC<ToolConfigPanelProps> = ({ configs, onToggle, onClose }) => {
  return (
    <div className="absolute top-12 right-0 w-80 bg-white rounded-lg shadow-xl border border-gray-200 z-50">
      <div className="flex items-center justify-between p-3 border-b border-gray-100">
        <span className="font-medium text-gray-700">AI 工具配置</span>
        <button
          onClick={onClose}
          className="text-gray-400 hover:text-gray-600 p-1 rounded"
        >
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
      <div className="p-3 space-y-3 max-h-80 overflow-y-auto">
        {configs.map((tool) => (
          <div
            key={tool.id}
            className="flex items-start gap-3 p-2 rounded-lg hover:bg-gray-50 transition-colors"
          >
            <button
              onClick={() => onToggle(tool.id)}
              className={`mt-0.5 w-10 h-5 rounded-full transition-colors flex-shrink-0 ${
                tool.enabled ? 'bg-emerald-500' : 'bg-gray-300'
              }`}
            >
              <div
                className={`w-4 h-4 bg-white rounded-full shadow transform transition-transform ${
                  tool.enabled ? 'translate-x-5' : 'translate-x-0.5'
                }`}
              />
            </button>
            <div className="flex-1 min-w-0">
              <div className="font-medium text-sm text-gray-800">{tool.name}</div>
              <div className="text-xs text-gray-500 mt-0.5">{tool.description}</div>
            </div>
          </div>
        ))}
      </div>
      <div className="p-3 border-t border-gray-100 bg-gray-50 rounded-b-lg">
        <p className="text-xs text-gray-500">
          关闭工具后，AI 将无法使用该功能
        </p>
      </div>
    </div>
  );
};

export default ToolConfigPanel;
