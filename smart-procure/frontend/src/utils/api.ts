import axios from 'axios';

// 401 事件，用于通知应用层处理登出
export const AUTH_EXPIRED_EVENT = 'auth:expired';

const api = axios.create({
  baseURL: '/api', // Relative path for proxy
});

// 请求拦截器 - 自动添加 Token
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// 响应拦截器 - 处理 401 错误
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // 清除本地存储的认证信息
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      // 触发自定义事件，让应用层决定如何处理（如显示提示后再跳转）
      window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT));
    }
    return Promise.reject(error);
  }
);

export const initSheet = async () => {
  const response = await api.get('/init');
  return response.data;
};

export type ChatHistoryMessage = {
  role: 'user' | 'assistant' | 'system';
  content: string;
};

export const sendChat = async (
  message: string,
  currentSheetData: unknown[][],
  chatHistory?: ChatHistoryMessage[]
) => {
  const response = await api.post('/chat', {
    message,
    current_sheet_data: currentSheetData,
    chat_history: chatHistory,
  });
  return response.data;
};

export const uploadFile = async (file: File) => {
  const formData = new FormData();
  formData.append('file', file);
  const response = await api.post('/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
  return response.data;
};

// Sheet save/load API functions
export const saveSheet = async (data: {
  id?: string;
  name: string;
  sheet_data: unknown[][];
  chat_history: ChatHistoryMessage[];
}) => {
  const response = await api.post('/sheets/save', data);
  return response.data;
};

export const listSheets = async (limit: number = 50, offset: number = 0) => {
  const response = await api.get('/sheets/list', { params: { limit, offset } });
  return response.data;
};

export const getSheet = async (sheetId: string) => {
  const response = await api.get(`/sheets/${sheetId}`);
  return response.data;
};

export const deleteSheet = async (sheetId: string) => {
  const response = await api.delete(`/sheets/${sheetId}`);
  return response.data;
};

export const exportSheet = async (sheetId: string) => {
  const response = await api.get(`/sheets/${sheetId}/export`, {
    responseType: 'blob',
  });
  return response.data;
};

// Supplier API functions
export const searchSuppliers = async (query: string, limit: number = 10) => {
  const response = await api.get('/suppliers/search', { params: { q: query, limit } });
  return response.data;
};

export const listSuppliers = async (limit: number = 50, offset: number = 0) => {
  const response = await api.get('/suppliers/list', { params: { limit, offset } });
  return response.data;
};

export const deleteSupplier = async (supplierId: number) => {
  const response = await api.delete(`/suppliers/${supplierId}`);
  return response.data;
};

export const recommendSuppliers = async (data: {
  product_name: string;
  spec?: string;
  brand?: string;
  limit?: number;
}) => {
  const response = await api.post('/suppliers/recommend', data);
  return response.data;
};

export const extractSuppliersFromSheet = async (sheetData: unknown[][]) => {
  const response = await api.post('/sheets/extract-suppliers', {
    sheet_data: sheetData,
  });
  return response.data;
};

export const getNotifications = async () => {
  const response = await api.get('/notifications');
  return response.data;
};
