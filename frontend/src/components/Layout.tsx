import { Layout, Menu, Avatar, Dropdown, Button, Space, Badge } from 'antd';
import {
  MessageOutlined,
  FileTextOutlined,
  UserOutlined,
  LogoutOutlined,
  DashboardOutlined,
  TeamOutlined,
} from '@ant-design/icons';
import { useNavigate, useLocation, Outlet } from 'react-router-dom';
import { useEffect, useState } from 'react';

const { Header, Sider, Content } = Layout;

export default function AppLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const [user, setUser] = useState<any>(null);

  useEffect(() => {
    const userStr = localStorage.getItem('user');
    const user = userStr ? JSON.parse(userStr) : null;
    if (!user) {
      navigate('/login');
      return;
    }
    setUser(user);
  }, [navigate]);

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    navigate('/login');
  };

  const menuItems = [
    {
      key: '/chat',
      icon: <MessageOutlined />,
      label: '智能问答',
    },
    {
      key: '/documents',
      icon: <FileTextOutlined />,
      label: '知识库文档',
    },
    {
      key: '/profile',
      icon: <UserOutlined />,
      label: '个人中心',
    },
  ];

  if (user?.role === 'admin') {
    menuItems.push({
      key: '/admin',
      icon: <DashboardOutlined />,
      label: '缓存管理',
    });
    menuItems.push({
      key: '/users',
      icon: <TeamOutlined />,
      label: '人员管理',
    });
  }

  const dropdownItems = [
    {
      key: 'profile',
      icon: <UserOutlined />,
      label: '个人中心',
      onClick: () => navigate('/profile'),
    },
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: '退出登录',
      onClick: handleLogout,
    },
  ];

  return (
    <Layout className="min-h-screen">
      <Sider theme="dark" width={220}>
        <div className="h-16 flex items-center px-5 border-b border-white/10">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-white/10 flex items-center justify-center text-white text-sm font-semibold tracking-wide">
              HHU
            </div>
            <span className="font-semibold text-white/95">校园问答助手</span>
          </div>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
          style={{ borderRight: 0, paddingTop: 8, background: 'transparent' }}
        />
        <div className="absolute bottom-0 left-0 right-0 p-4 text-xs text-white/35 text-center border-t border-white/10">
          CampusQA v1.0
        </div>
      </Sider>

      <Layout>
        <Header className="bg-white border-b border-slate-200 px-6 flex items-center justify-between" style={{ height: 64 }}>
          <div className="text-gray-500 text-sm">
            {location.pathname === '/chat' && '智能问答 · 基于 RAG + LLM'}
            {location.pathname === '/documents' && '知识库文档管理'}
            {location.pathname === '/profile' && '个人中心'}
            {location.pathname === '/admin' && '管理员 · 缓存管理'}
            {location.pathname === '/users' && '管理员 · 人员管理'}
          </div>
          <Space>
            <Badge color={user?.role === 'admin' ? 'red' : 'blue'} text={user?.role === 'admin' ? '管理员' : '学生'} />
            <Dropdown menu={{ items: dropdownItems }} placement="bottomRight">
              <Button type="text" className="flex items-center gap-2">
                <Avatar size="small" icon={<UserOutlined />} />
                <span className="hidden sm:inline">{user?.nickname || user?.username || '用户'}</span>
              </Button>
            </Dropdown>
          </Space>
        </Header>
        <Content className="p-6 overflow-auto">
          <div className="max-w-6xl mx-auto">
            <Outlet />
          </div>
        </Content>
      </Layout>
    </Layout>
  );
}
