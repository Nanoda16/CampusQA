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
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 via-indigo-50 to-purple-50 p-4">
      <Card
        className="w-full max-w-md shadow-2xl rounded-2xl overflow-hidden"
        styles={{ body: { padding: '32px' } }}
      >
        <div className="text-center mb-8">
          <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center text-white text-2xl font-bold mx-auto mb-4 shadow-lg">
            HHU
          </div>
          <h1 className="text-2xl font-bold text-gray-800 mb-1">河海大学校园问答助手</h1>
          <p className="text-gray-500 text-sm">基于 LLM + RAG 的智能问答系统</p>
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
                  className="bg-gradient-to-r from-blue-500 to-indigo-600"
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
                  className="bg-gradient-to-r from-blue-500 to-indigo-600"
                >
                  注册
                </Button>
              </Form.Item>
            </Form>
          </Tabs.TabPane>
        </Tabs>

        <div className="mt-4 p-3 bg-gray-50 rounded-lg text-xs text-gray-500">
          <p className="mb-1">测试账号：admin / admin123</p>
          <p>未注册可直接切换“注册”创建账号</p>
        </div>
      </Card>
    </div>
  );
}
