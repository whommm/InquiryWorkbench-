import { useState } from 'react';
import { useAuthStore } from '../stores/useAuthStore';

interface LoginProps {
  onSwitchToRegister: () => void;
}

export default function Login({ onSwitchToRegister }: LoginProps) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { setAuth } = useAuthStore();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || '登录失败');
      }

      setAuth(data.access_token, data.user);
    } catch (err) {
      setError(err instanceof Error ? err.message : '登录失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex">
      {/* 左侧品牌区域 */}
      <div className="hidden lg:flex lg:w-1/2 bg-gradient-to-br from-emerald-600 via-emerald-500 to-teal-500 p-12 flex-col justify-between">
        <div>
          <div className="flex items-center gap-3 mb-8">
            <div className="w-12 h-12 bg-white/20 backdrop-blur rounded-xl flex items-center justify-center text-white font-bold text-2xl">
              S
            </div>
            <span className="text-white text-2xl font-bold">SmartProcure</span>
          </div>
          <h1 className="text-4xl font-bold text-white mb-4">智能采购工作台</h1>
          <p className="text-emerald-100 text-lg leading-relaxed">
            AI 驱动的采购管理平台，让询价、比价、供应商管理更高效。
          </p>
        </div>
        <div className="space-y-4">
          <div className="flex items-center gap-3 text-white/90">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
            <span>智能解析报价单，自动提取关键信息</span>
          </div>
          <div className="flex items-center gap-3 text-white/90">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
            <span>AI 推荐最优供应商，历史报价一目了然</span>
          </div>
          <div className="flex items-center gap-3 text-white/90">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
            <span>多标签页管理，高效处理多个询价单</span>
          </div>
        </div>
      </div>

      {/* 右侧登录区域 */}
      <div className="flex-1 flex items-center justify-center bg-gray-50 p-8">
        <div className="w-full max-w-md">
          <div className="lg:hidden flex items-center justify-center gap-3 mb-8">
            <div className="w-10 h-10 bg-emerald-600 rounded-lg flex items-center justify-center text-white font-bold text-xl">
              S
            </div>
            <span className="text-gray-800 text-xl font-bold">SmartProcure</span>
          </div>

          <div className="bg-white p-8 rounded-2xl shadow-lg border border-gray-100">
            <h2 className="text-2xl font-bold text-gray-900 mb-2">欢迎回来</h2>
            <p className="text-gray-500 mb-6">登录您的账户以继续</p>

            <form onSubmit={handleSubmit}>
              <div className="mb-4">
                <label className="block text-sm font-medium text-gray-700 mb-1.5">
                  用户名
                </label>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500 transition-all"
                  placeholder="请输入用户名"
                  required
                />
              </div>
              <div className="mb-6">
                <label className="block text-sm font-medium text-gray-700 mb-1.5">
                  密码
                </label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500 transition-all"
                  placeholder="请输入密码"
                  required
                />
              </div>
              {error && (
                <div className="mb-4 p-3 bg-red-50 border border-red-200 text-red-600 text-sm rounded-lg">{error}</div>
              )}
              <button
                type="submit"
                disabled={loading}
                className="w-full btn-primary py-2.5 rounded-lg font-medium disabled:opacity-50 transition-all hover:shadow-md"
              >
                {loading ? '登录中...' : '登录'}
              </button>
            </form>
            <p className="mt-6 text-center text-sm text-gray-600">
              没有账号？
              <button
                onClick={onSwitchToRegister}
                className="text-emerald-600 hover:text-emerald-700 font-medium ml-1"
              >
                立即注册
              </button>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
