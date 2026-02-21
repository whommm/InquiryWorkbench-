import axios from 'axios';

export type AdminUserSummary = {
  user_id: string;
  username: string;
  display_name?: string | null;
  today_updated_sheet_count: number;
  today_total_rows: number;
  today_quoted_rows: number;
  today_progress: number;
  last_update_at?: string | null;
  updated_sheet_names?: string[];
  latest_sheet_name?: string | null;
};

export type SheetDetail = {
  sheet_id: string;
  sheet_name: string;
  updated_at?: string | null;
  total_rows: number;
  quoted_rows: number;
  progress: number;
};

export type OverviewResponse = {
  date: string;
  tz: string;
  kpis: {
    active_user_count: number;
    updated_sheet_count: number;
    total_rows: number;
    quoted_rows: number;
    overall_progress: number;
  };
  users: AdminUserSummary[];
};

export type UserDetailResponse = {
  date: string;
  tz: string;
  user: AdminUserSummary;
  sheets: SheetDetail[];
};

export type LoginResponse = {
  access_token: string;
  token_type: string;
  user: {
    id: string;
    username: string;
    display_name?: string | null;
    role?: string;
  };
};

const api = axios.create({
  baseURL: '/api',
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('admin_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export async function login(username: string, password: string): Promise<LoginResponse> {
  const response = await api.post('/auth/login', { username, password });
  return response.data;
}

export async function getOverview(date: string, tz: string): Promise<OverviewResponse> {
  const response = await api.get('/admin/progress/overview', { params: { date, tz } });
  return response.data;
}

export async function getUserDetail(userId: string, date: string, tz: string): Promise<UserDetailResponse> {
  const response = await api.get(`/admin/progress/users/${userId}`, { params: { date, tz } });
  return response.data;
}

export async function getStreamTicket(): Promise<string> {
  const response = await api.post('/admin/progress/stream-ticket');
  return response.data.ticket;
}

export async function getStreamUrl(date: string, tz: string): Promise<string> {
  const ticket = await getStreamTicket();
  const query = new URLSearchParams({ ticket, date, tz }).toString();
  return `/api/admin/progress/stream?${query}`;
}

// ========== 用户管理 API ==========

export type AdminUser = {
  id: string;
  username: string;
  display_name?: string | null;
  role: string;
  created_at?: string | null;
  last_login_at?: string | null;
};

export async function listUsers(): Promise<AdminUser[]> {
  const response = await api.get('/admin/users');
  return response.data.users;
}

export async function createUser(data: {
  username: string;
  password: string;
  display_name?: string;
  role: string;
}): Promise<void> {
  await api.post('/admin/users', data);
}

export async function deleteUser(userId: string): Promise<void> {
  await api.delete(`/admin/users/${userId}`);
}

export async function resetPassword(userId: string, newPassword: string): Promise<void> {
  await api.post(`/admin/users/${userId}/reset-password`, { new_password: newPassword });
}
