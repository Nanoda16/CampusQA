import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, Tabs, Form, Input, Button, message } from 'antd';
import { UserOutlined, LockOutlined, MailOutlined, LoginOutlined } from '@ant-design/icons';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';

export default function Login() {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [activeTab, setActiveTab] = useState('login');
  const [loading, setLoading] = useState(false);

  const handleLogin = async (values: any) => {
    setLoading(true);
    try {
      const res: any = await api.post('/user/login', values);
      if (res.code === 200) {
        login(res.data.access_token, res.data.user);
        message.success('登录成功');
        navigate('/chat');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleRegister = async (values: any) => {
    setLoading(true);
    try {
      const res: any = await api.post('/user/register', values);
      if (res.code === 200) {
        message.success('注册成功，请登录');
        setActiveTab('login');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-brand-900 p-4">
      <Card
        className="w-full max-w-md rounded-card overflow-hidden border border-brand-100"
        styles={{ body: { padding: '40px 36px' } }}
      >
        <div className="text-center mb-8">
          <div className="w-14 h-14 rounded-xl bg-brand-700 flex items-center justify-center text-white text-xl font-semibold tracking-wide mx-auto mb-4">
            HHU
          </div>
          <h1 className="text-xl font-semibold text-brand-900 mb-1">河海大学校园问答助手</h1>
          <p className="text-slate-500 text-sm">基于 LLM + RAG 的智能问答系统</p>
        </div>

        <Tabs activeKey={activeTab} onChange={setActiveTab} centered>
          <Tabs.TabPane tab="登录" key="login">
            <Form onFinish={handleLogin} size="large">
              <Form.Item
                name="username"
                rules={[{ required: true, message: '请输入用户名' }]}
              >
                <Input prefix={<UserOutlined />} placeholder="用户名" />
              </Form.Item>
              <Form.Item
                name="password"
                rules={[{ required: true, message: '请输入密码' }]}
              >
                <Input.Password prefix={<LockOutlined />} placeholder="密码" />
              </Form.Item>
              <Form.Item>
                <Button
                  type="primary"
                  htmlType="submit"
                  loading={loading}
                  block
                  icon={<LoginOutlined />}
                >
                  登录
                </Button>
              </Form.Item>
            </Form>
          </Tabs.TabPane>

          <Tabs.TabPane tab="注册" key="register">
            <Form onFinish={handleRegister} size="large">
              <Form.Item
                name="username"
                rules={[{ required: true, message: '请输入用户名' }]}
              >
                <Input prefix={<UserOutlined />} placeholder="用户名" />
              </Form.Item>
              <Form.Item
                name="password"
                rules={[{ required: true, min: 6, message: '密码至少6位' }]}
              >
                <Input.Password prefix={<LockOutlined />} placeholder="密码" />
              </Form.Item>
              <Form.Item name="nickname">
                <Input prefix={<UserOutlined />} placeholder="昵称（可选）" />
              </Form.Item>
              <Form.Item name="email">
                <Input prefix={<MailOutlined />} placeholder="邮箱（可选）" />
              </Form.Item>
              <Form.Item>
                <Button
                  type="primary"
                  htmlType="submit"
                  loading={loading}
                  block
                >
                  注册
                </Button>
              </Form.Item>
            </Form>
          </Tabs.TabPane>
        </Tabs>

        <div className="mt-4 p-3 bg-brand-50 border border-brand-100 rounded-lg text-xs text-slate-500">
          <p className="mb-1">测试账号：admin / admin123</p>
          <p>未注册可直接切换“注册”创建账号</p>
        </div>
      </Card>
    </div>
  );
}
