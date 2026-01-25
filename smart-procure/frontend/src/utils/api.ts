import axios from 'axios';

const api = axios.create({
  baseURL: '/api', // Relative path for proxy
});

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
