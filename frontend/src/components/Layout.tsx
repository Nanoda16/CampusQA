import { Avatar, Dropdown, Tooltip } from 'antd';
import {
  MessageOutlined,
  FileTextOutlined,
  UserOutlined,
  LogoutOutlined,
  DashboardOutlined,
  TeamOutlined,
  ReadOutlined,
} from '@ant-design/icons';
import { useNavigate, useLocation, Outlet } from 'react-router-dom';
import { useEffect, useState } from 'react';

interface NavItem {
  key: string;
  icon: React.ReactNode;
  label: string;
  eyebrow: string;
}

const PAGE_META: Record<string, { title: string; eyebrow: string; hint: string }> = {
  '/chat': { title: '智能问答', eyebrow: 'ask', hint: '混合检索 · 引用回答' },
  '/documents': { title: '知识库文档', eyebrow: 'corpus', hint: '上传、整理、重建索引' },
  '/profile': { title: '个人中心', eyebrow: 'account', hint: '账号与安全' },
  '/admin': { title: '缓存管理', eyebrow: 'admin', hint: '缓存命中与热度' },
  '/users': { title: '人员管理', eyebrow: 'admin', hint: '角色与状态' },
};

export default function AppLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const [user, setUser] = useState<any>(null);

  useEffect(() => {
    const userStr = localStorage.getItem('user');
    const parsed = userStr ? JSON.parse(userStr) : null;
    if (!parsed) {
      navigate('/login');
      return;
    }
    setUser(parsed);
  }, [navigate]);

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    navigate('/login');
  };

  const navItems: NavItem[] = [
    { key: '/chat', icon: <MessageOutlined />, label: '智能问答', eyebrow: 'ask' },
    { key: '/documents', icon: <FileTextOutlined />, label: '知识库文档', eyebrow: 'corpus' },
    { key: '/profile', icon: <UserOutlined />, label: '个人中心', eyebrow: 'account' },
  ];

  if (user?.role === 'admin') {
    navItems.push({
      key: '/admin',
      icon: <DashboardOutlined />,
      label: '缓存管理',
      eyebrow: 'admin',
    });
    navItems.push({
      key: '/users',
      icon: <TeamOutlined />,
      label: '人员管理',
      eyebrow: 'admin',
    });
  }

  const meta = PAGE_META[location.pathname] ?? PAGE_META['/chat'];

  const dropdownItems = [
    {
      key: 'profile',
      icon: <UserOutlined />,
      label: '个人中心',
      onClick: () => navigate('/profile'),
    },
    { type: 'divider' as const },
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: '退出登录',
      danger: true,
      onClick: handleLogout,
    },
  ];

  return (
    <div className="min-h-screen bg-paper-0 text-ink-1 flex">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-[100] focus:px-3 focus:py-2 focus:rounded-r2 focus:bg-paper-2 focus:text-ink-1 focus:border focus:border-rule focus:shadow-r2"
      >
        跳到主要内容
      </a>
      {/* ── 左侧阅览索引栏：浅纸面 + 发丝线，不用深色色块 ─────────── */}
      <aside className="hidden md:flex w-[236px] shrink-0 flex-col bg-paper-1 border-r border-rule">
        {/* 品牌锁定 */}
        <div className="px-5 pt-6 pb-5">
          <button
            onClick={() => navigate('/chat')}
            className="flex items-center gap-3 text-left group"
            aria-label="回到智能问答"
          >
            <span className="grid place-items-center w-9 h-9 rounded-[10px] bg-accent-wash text-accent border border-[#ecd6cd] text-[15px] font-semibold tracking-tight">
              问
            </span>
            <span className="leading-tight">
              <span className="block text-[15px] font-semibold tracking-tight text-ink-1">
                校园问答
              </span>
              <span className="eyebrow block mt-1">CAMPUS · RAG</span>
            </span>
          </button>
        </div>

        {/* 导航 */}
        <nav className="px-2 pb-2" aria-label="主导航">
          <div className="eyebrow px-3 pb-2">navigation</div>
          <ul className="space-y-0.5">
            {navItems.map((item) => {
              const active = location.pathname === item.key;
              return (
                <li key={item.key}>
                  <button
                    data-active={active}
                    onClick={() => navigate(item.key)}
                    aria-current={active ? 'page' : undefined}
                    className={`row-quiet w-full flex items-center gap-3 pl-4 pr-3 h-10 text-[13.5px] ${
                      active ? 'text-ink-1 font-medium' : 'text-ink-2'
                    }`}
                  >
                    <span className={active ? 'text-accent' : 'text-ink-3'}>{item.icon}</span>
                    <span className="truncate">{item.label}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>

        {/* 底部：用户 + 版本 */}
        <div className="mt-auto px-3 pb-4">
          <div className="surface-sub p-3 flex items-center gap-2.5">
            <Avatar size={28} className="!bg-[#efe6d6] !text-ink-2 shrink-0" icon={<UserOutlined />} />
            <div className="min-w-0 flex-1">
              <div className="text-[12.5px] text-ink-1 truncate leading-tight">
                {user?.nickname || user?.username || '未登录'}
              </div>
              <div className="eyebrow mt-1 truncate">
                {user?.role === 'admin' ? 'administrator' : 'student'}
              </div>
            </div>
            <Tooltip title="退出登录">
              <button
                onClick={handleLogout}
                aria-label="退出登录"
                className="grid place-items-center w-8 h-8 rounded-r2 text-ink-3 hover:text-danger hover:bg-[#f6ece9] transition-colors duration-150"
              >
                <LogoutOutlined />
              </button>
            </Tooltip>
          </div>
          <div className="eyebrow text-center mt-3 text-ink-3/70">CampusQA · v1.0</div>
        </div>
      </aside>

      {/* ── 主工作区 ─────────────────────────────────────────────── */}
      <div className="flex-1 min-w-0 flex flex-col">
        {/* 顶栏：透明，靠发丝线与内容区分，不做整条白底 */}
        <header className="h-14 shrink-0 px-5 md:px-8 flex items-center justify-between border-b border-rule/70">
          <div className="flex items-baseline gap-3 min-w-0">
            <span className="eyebrow hidden sm:inline">{meta.eyebrow}</span>
            <ReadOutlined className="sm:hidden text-ink-3" />
            <h1 className="text-[15px] font-semibold tracking-tight text-ink-1 truncate">
              {meta.title}
            </h1>
            <span className="hidden lg:inline text-[12.5px] text-ink-3 truncate">{meta.hint}</span>
          </div>

          <Dropdown menu={{ items: dropdownItems }} placement="bottomRight" trigger={['click']}>
            <button className="flex items-center gap-2 h-9 pl-1 pr-2.5 rounded-full hover:bg-paper-1 transition-colors duration-150">
              <Avatar
                size={26}
                className="!bg-accent-wash !text-accent"
                icon={<UserOutlined />}
              />
              <span className="hidden sm:inline text-[13px] text-ink-2 max-w-[120px] truncate">
                {user?.nickname || user?.username || '用户'}
              </span>
            </button>
          </Dropdown>
        </header>

        <main id="main-content" className="flex-1 min-h-0 overflow-auto">
          <div className="mx-auto w-full max-w-[1220px] px-4 md:px-8 py-5 md:py-6">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
