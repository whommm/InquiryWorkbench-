import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  type AdminUserSummary,
  type OverviewResponse,
  type SheetDetail,
  getOverview,
  getStreamUrl,
  getUserDetail,
  login,
} from './api';

type AdminIdentity = {
  id: string;
  username: string;
  display_name?: string | null;
  role?: string;
};

type StreamStatus = 'connecting' | 'online' | 'offline';

function todayISODate(): string {
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, '0');
  const d = String(now.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

function formatPercent(value: number): string {
  return `${(Math.max(0, Math.min(1, value)) * 100).toFixed(1)}%`;
}

function formatTime(value?: string | null): string {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '-';
  return date.toLocaleString('zh-CN', { hour12: false });
}

function deriveKpis(users: AdminUserSummary[]): OverviewResponse['kpis'] {
  const activeUserCount = users.length;
  const updatedSheetCount = users.reduce((acc, item) => acc + item.today_updated_sheet_count, 0);
  const totalRows = users.reduce((acc, item) => acc + item.today_total_rows, 0);
  const quotedRows = users.reduce((acc, item) => acc + item.today_quoted_rows, 0);
  return {
    active_user_count: activeUserCount,
    updated_sheet_count: updatedSheetCount,
    total_rows: totalRows,
    quoted_rows: quotedRows,
    overall_progress: totalRows > 0 ? quotedRows / totalRows : 0,
  };
}

function App() {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem('admin_token'));
  const [admin, setAdmin] = useState<AdminIdentity | null>(() => {
    const raw = localStorage.getItem('admin_user');
    if (!raw) return null;
    try {
      return JSON.parse(raw) as AdminIdentity;
    } catch {
      return null;
    }
  });
  const [date, setDate] = useState(todayISODate);
  const [tz] = useState('Asia/Shanghai');
  const [streamStatus, setStreamStatus] = useState<StreamStatus>('offline');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>('');

  const [overview, setOverview] = useState<OverviewResponse>({
    date: todayISODate(),
    tz,
    kpis: {
      active_user_count: 0,
      updated_sheet_count: 0,
      total_rows: 0,
      quoted_rows: 0,
      overall_progress: 0,
    },
    users: [],
  });
  const [selectedUserId, setSelectedUserId] = useState<string>('');
  const [selectedUser, setSelectedUser] = useState<AdminUserSummary | null>(null);
  const [sheetDetails, setSheetDetails] = useState<SheetDetail[]>([]);

  const loadOverview = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError('');
    try {
      const data = await getOverview(date, tz);
      setOverview(data);
      if (!selectedUserId && data.users.length > 0) {
        setSelectedUserId(data.users[0].user_id);
      }
    } catch (err) {
      setError((err as Error).message || '加载总览失败');
    } finally {
      setLoading(false);
    }
  }, [date, selectedUserId, token, tz]);

  const loadUserDetail = useCallback(
    async (userId: string) => {
      if (!token || !userId) return;
      try {
        const data = await getUserDetail(userId, date, tz);
        setSelectedUser(data.user);
        setSheetDetails(data.sheets);
      } catch {
        setSelectedUser(null);
        setSheetDetails([]);
      }
    },
    [date, token, tz],
  );

  useEffect(() => {
    if (!token) return;
    void loadOverview();
  }, [loadOverview, token]);

  useEffect(() => {
    if (!selectedUserId) return;
    void loadUserDetail(selectedUserId);
  }, [loadUserDetail, selectedUserId]);

  useEffect(() => {
    if (!token) return;
    setStreamStatus('connecting');
    const source = new EventSource(getStreamUrl(date, tz));

    source.addEventListener('ready', () => {
      setStreamStatus('online');
    });

    source.addEventListener('progress_update', (event) => {
      try {
        const payload = JSON.parse((event as MessageEvent).data) as {
          user?: AdminUserSummary | null;
        };
        const changedUser = payload.user;
        if (!changedUser) return;

        setOverview((prev) => {
          const exists = prev.users.some((item) => item.user_id === changedUser.user_id);
          const nextUsers = exists
            ? prev.users.map((item) => (item.user_id === changedUser.user_id ? changedUser : item))
            : [changedUser, ...prev.users];
          const sortedUsers = [...nextUsers].sort(
            (a, b) =>
              a.today_progress - b.today_progress || b.today_total_rows - a.today_total_rows,
          );
          return {
            ...prev,
            users: sortedUsers,
            kpis: deriveKpis(sortedUsers),
          };
        });

        if (selectedUserId === changedUser.user_id) {
          void loadUserDetail(changedUser.user_id);
        }
      } catch {
        // Ignore malformed SSE payloads.
      }
    });

    source.onerror = () => {
      setStreamStatus('offline');
    };

    return () => {
      source.close();
      setStreamStatus('offline');
    };
  }, [date, loadUserDetail, selectedUserId, token, tz]);

  const displayUsers = useMemo(() => overview.users, [overview.users]);

  const handleLogin = async (username: string, password: string) => {
    setError('');
    setLoading(true);
    try {
      const result = await login(username, password);
      const role = (result.user.role || 'user').toLowerCase();
      if (role !== 'admin') {
        setError('该账号不是管理员，无法进入管理面板。');
        return;
      }
      localStorage.setItem('admin_token', result.access_token);
      localStorage.setItem('admin_user', JSON.stringify(result.user));
      setToken(result.access_token);
      setAdmin(result.user);
    } catch (err) {
      setError((err as Error).message || '登录失败');
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('admin_token');
    localStorage.removeItem('admin_user');
    setToken(null);
    setAdmin(null);
    setOverview((prev) => ({ ...prev, users: [] }));
    setSelectedUserId('');
    setSelectedUser(null);
    setSheetDetails([]);
  };

  if (!token || !admin) {
    return (
      <LoginScreen loading={loading} error={error} onSubmit={handleLogin} />
    );
  }

  return (
    <div className="page">
      <div className="orb orb-left" />
      <div className="orb orb-right" />

      <header className="topbar">
        <div>
          <p className="eyebrow">SmartProcure Admin</p>
          <h1>实时进度监控面板</h1>
        </div>
        <div className="topbar-actions">
          <label className="date-picker">
            <span>统计日期</span>
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </label>
          <button className="btn-secondary" onClick={() => void loadOverview()}>刷新</button>
          <span className={`stream-badge ${streamStatus}`}>{streamStatus}</span>
          <div className="admin-pill">
            <strong>{admin.display_name || admin.username}</strong>
            <button onClick={handleLogout}>退出</button>
          </div>
        </div>
      </header>

      {error ? <div className="error-banner">{error}</div> : null}

      <section className="kpi-grid">
        <KpiCard label="今日活跃账号" value={overview.kpis.active_user_count.toString()} />
        <KpiCard label="今日更新表格" value={overview.kpis.updated_sheet_count.toString()} />
        <KpiCard label="询价产品总行数" value={overview.kpis.total_rows.toString()} mono />
        <KpiCard
          label="已报价产品行数"
          value={`${overview.kpis.quoted_rows} (${formatPercent(overview.kpis.overall_progress)})`}
          mono
        />
      </section>

      <section className="content-grid">
        <div className="panel">
          <div className="panel-header">
            <h2>账号进度排行</h2>
            <span>{displayUsers.length} 个账号</span>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>账号</th>
                  <th>今日表格名称</th>
                  <th>进度</th>
                  <th>已报价/总行</th>
                  <th>今日更新表格</th>
                  <th>最近更新时间</th>
                </tr>
              </thead>
              <tbody>
                {displayUsers.map((item) => {
                  const active = item.user_id === selectedUserId;
                  return (
                    <tr
                      key={item.user_id}
                      className={active ? 'active' : ''}
                      onClick={() => setSelectedUserId(item.user_id)}
                    >
                      <td>{item.display_name || item.username}</td>
                      <td>
                        <div className="sheet-name-list">
                          {(item.updated_sheet_names || []).slice(0, 2).map((name) => (
                            <span key={`${item.user_id}-${name}`} className="sheet-pill" title={name}>
                              {name}
                            </span>
                          ))}
                          {(item.updated_sheet_names || []).length > 2 ? (
                            <span className="sheet-pill more">+{(item.updated_sheet_names || []).length - 2}</span>
                          ) : null}
                          {(item.updated_sheet_names || []).length === 0 ? (
                            <span className="sheet-pill empty">-</span>
                          ) : null}
                        </div>
                      </td>
                      <td>
                        <div className="progress-cell">
                          <div className="progress-track">
                            <div style={{ width: `${Math.round(item.today_progress * 100)}%` }} />
                          </div>
                          <span>{formatPercent(item.today_progress)}</span>
                        </div>
                      </td>
                      <td className="mono">{item.today_quoted_rows} / {item.today_total_rows}</td>
                      <td>{item.today_updated_sheet_count}</td>
                      <td>{formatTime(item.last_update_at)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        <div className="panel">
          <div className="panel-header">
            <h2>账号表格明细</h2>
            <span>{selectedUser ? (selectedUser.display_name || selectedUser.username) : '未选择'}</span>
          </div>
          <div className="detail-summary">
            <div>
              <label>总行数</label>
              <strong>{selectedUser?.today_total_rows ?? 0}</strong>
            </div>
            <div>
              <label>已报价行</label>
              <strong>{selectedUser?.today_quoted_rows ?? 0}</strong>
            </div>
            <div>
              <label>进度</label>
              <strong>{formatPercent(selectedUser?.today_progress ?? 0)}</strong>
            </div>
          </div>
          <div className="sheet-list">
            {sheetDetails.map((sheet) => (
              <article key={sheet.sheet_id} className="sheet-card">
                <div className="sheet-head">
                  <h3>{sheet.sheet_name}</h3>
                  <span>{formatPercent(sheet.progress)}</span>
                </div>
                <p>已报价 {sheet.quoted_rows} / 总行 {sheet.total_rows}</p>
                <small>更新时间: {formatTime(sheet.updated_at)}</small>
              </article>
            ))}
            {sheetDetails.length === 0 ? <p className="empty-tip">当前用户当天暂无更新表格。</p> : null}
          </div>
        </div>
      </section>
    </div>
  );
}

function LoginScreen(props: {
  loading: boolean;
  error: string;
  onSubmit: (username: string, password: string) => Promise<void>;
}) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  return (
    <div className="login-page">
      <div className="login-card">
        <p className="eyebrow">Admin Access</p>
        <h1>SmartProcure 管理端</h1>
        <p>请使用管理员账号登录</p>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void props.onSubmit(username, password);
          }}
        >
          <label>
            账号
            <input value={username} onChange={(e) => setUsername(e.target.value)} required />
          </label>
          <label>
            密码
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </label>
          {props.error ? <div className="error-banner">{props.error}</div> : null}
          <button type="submit" disabled={props.loading}>
            {props.loading ? '登录中...' : '进入管理端'}
          </button>
        </form>
      </div>
    </div>
  );
}

function KpiCard(props: { label: string; value: string; mono?: boolean }) {
  return (
    <article className="kpi-card">
      <span>{props.label}</span>
      <strong className={props.mono ? 'mono' : ''}>{props.value}</strong>
    </article>
  );
}

export default App;
