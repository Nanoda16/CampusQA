import axios from 'axios';
import { message } from 'antd';

const api = axios.create({
  baseURL: '/api',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Dynamic token getter — set by AuthContext on mount/token change,
// falls back to localStorage for environments outside React tree
let tokenGetter: () => string | null = () => localStorage.getItem('token');

export const setTokenGetter = (getter: () => string | null) => {
  tokenGetter = getter;
};

/**
 * 把 axios / 后端的错误翻译成使用者看得懂的中文。
 * 后端会尽量在 detail 里给出可执行的说明，能直接用就用；
 * 拿不到时按状态码兜底，绝不把 "Request failed with status code 500" 抛给用户。
 */
function humanizeError(error: any): string {
  const detail = error?.response?.data?.detail;

  if (typeof detail === 'string' && detail.trim()) return detail;
  if (Array.isArray(detail) && detail.length) {
    const msgs = detail.map((d: any) => d?.msg).filter(Boolean);
    return msgs.length ? msgs.join('；') : '提交的内容格式不正确';
  }

  if (!error?.response) {
    if (error?.code === 'ECONNABORTED') return '请求超时，请稍后重试';
    return '连不上后端服务，请确认 backend 已经启动（默认 8002 端口）';
  }

  switch (error.response.status) {
    case 400:
      return '请求参数有问题，请检查填写的内容';
    case 401:
      return '登录已过期，请重新登录';
    case 403:
      return '没有权限执行这个操作';
    case 404:
      return '要访问的内容不存在';
    case 422:
      return '提交的内容格式不正确';
    case 502:
    case 503:
    case 504:
      return '依赖的服务暂时不可用（AI 服务或数据库），请稍后重试';
    case 500:
      return '服务端处理请求时出错，请看后端控制台的日志';
    default:
      return `请求失败（${error.response.status}）`;
  }
}

// Request interceptor: add token, fix FormData content-type
api.interceptors.request.use((config) => {
  const token = tokenGetter();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  // Let axios set multipart/form-data with boundary for FormData
  if (config.data instanceof FormData) {
    delete config.headers['Content-Type'];
  }
  return config;
});

// Response interceptor: handle errors
api.interceptors.response.use(
  (response) => response.data,
  (error) => {
    if (error.response?.status === 401) {
      message.error('登录已过期，请重新登录');
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      window.location.href = '/login';
    } else {
      message.error(humanizeError(error));
    }
    return Promise.reject(error);
  }
);

export default api;
