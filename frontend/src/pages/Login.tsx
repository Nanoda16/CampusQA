import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Tabs, Form, Input, Button, message } from 'antd';
import { UserOutlined, LockOutlined, MailOutlined, ArrowRightOutlined } from '@ant-design/icons';
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

  const loginPane = (
    <Form onFinish={handleLogin} layout="vertical" requiredMark={false} size="large">
      <Form.Item
        name="username"
        label="用户名"
        rules={[{ required: true, message: '请输入用户名' }]}
      >
        <Input prefix={<UserOutlined className="text-ink-3" />} placeholder="admin" autoComplete="username" />
      </Form.Item>
      <Form.Item
        name="password"
        label="密码"
        rules={[{ required: true, message: '请输入密码' }]}
      >
        <Input.Password
          prefix={<LockOutlined className="text-ink-3" />}
          placeholder="请输入密码"
          autoComplete="current-password"
        />
      </Form.Item>
      <Button
        type="primary"
        htmlType="submit"
        loading={loading}
        block
        icon={<ArrowRightOutlined />}
        iconPosition="end"
        className="mt-1"
      >
        进入知识库
      </Button>
    </Form>
  );

  const registerPane = (
    <Form onFinish={handleRegister} layout="vertical" requiredMark={false} size="large">
      <Form.Item
        name="username"
        label="用户名"
        rules={[{ required: true, message: '请输入用户名' }]}
      >
        <Input prefix={<UserOutlined className="text-ink-3" />} placeholder="用于登录的唯一账号" />
      </Form.Item>
      <Form.Item
        name="password"
        label="密码"
        rules={[{ required: true, min: 6, message: '密码至少 6 位' }]}
      >
        <Input.Password prefix={<LockOutlined className="text-ink-3" />} placeholder="至少 6 位" />
      </Form.Item>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4">
        <Form.Item name="nickname" label="昵称（可选）">
          <Input placeholder="展示名称" />
        </Form.Item>
        <Form.Item name="email" label="邮箱（可选）">
          <Input prefix={<MailOutlined className="text-ink-3" />} placeholder="name@hhu.edu.cn" />
        </Form.Item>
      </div>
      <Button type="primary" htmlType="submit" loading={loading} block className="mt-1">
        创建账号
      </Button>
    </Form>
  );

  return (
    <div className="min-h-screen grid lg:grid-cols-[minmax(0,0.92fr)_minmax(0,1fr)] bg-paper-0">
      {/* ── 左：纸面说明页（窄屏隐藏） ─────────────────────────── */}
      <section className="hidden lg:flex flex-col px-12 xl:px-16 py-12">
        <div className="flex items-center gap-3">
          <span className="grid place-items-center w-10 h-10 rounded-[10px] bg-accent-wash text-accent border border-[#ecd6cd] text-[16px] font-semibold">
            问
          </span>
          <div className="leading-tight">
            <div className="text-[15px] font-semibold tracking-tight">校园问答</div>
            <div className="eyebrow mt-1">CAMPUS KNOWLEDGE · RAG</div>
          </div>
        </div>

        <div className="my-auto max-w-[440px] pt-10">
          <div className="w-9 h-[2px] bg-accent mb-6" aria-hidden />
          <div className="eyebrow mb-4">retrieval augmented generation</div>
          <h1 className="text-[30px] leading-[1.25] font-semibold tracking-[-0.022em]">
            把校园文件整理成
            <br />
            可以追问的答案。
          </h1>
          <p className="mt-5 text-[14px] leading-[1.75] text-ink-2">
            上传文档或放入知识目录后重建索引，提问时会同时走向量检索和关键词检索，
            融合排序取最相关的段落，答案后面附上原文出处。
          </p>

          <div className="mt-8 space-y-3">
            {[
              ['01', '混合检索', '向量 + BM25 双路召回，倒数排名融合'],
              ['02', '引用可核', '每条回答附带命中的原文片段与来源'],
              ['03', '内容自持', '知识库就是一个文本目录，随时替换'],
            ].map(([no, title, desc]) => (
              <div key={no} className="flex gap-3 items-baseline">
                <span className="num text-[11px] text-accent w-6 shrink-0">{no}</span>
                <span className="text-[13.5px] text-ink-1 font-medium w-[68px] shrink-0">
                  {title}
                </span>
                <span className="text-[12.5px] text-ink-3 leading-relaxed">{desc}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="eyebrow">hohai university · 2026</div>
      </section>

      {/* ── 右：表单 ─────────────────────────────────────────── */}
      <section className="flex items-center justify-center px-4 py-10 sm:px-8 bg-paper-1 lg:border-l lg:border-rule">
        <div className="w-full max-w-[420px]">
          {/* 窄屏品牌头 */}
          <div className="lg:hidden flex items-center gap-3 mb-8">
            <span className="grid place-items-center w-10 h-10 rounded-[10px] bg-accent-wash text-accent border border-[#ecd6cd] text-[16px] font-semibold">
              问
            </span>
            <div className="leading-tight">
              <div className="text-[15px] font-semibold tracking-tight">校园问答</div>
              <div className="eyebrow mt-1">CAMPUS · RAG</div>
            </div>
          </div>

          <div className="surface shadow-r3 p-7 sm:p-8">
            <div className="eyebrow mb-2">sign in</div>
            <h2 className="text-[20px] font-semibold tracking-tight mb-6">
              {activeTab === 'login' ? '登录知识库' : '创建账号'}
            </h2>

            <Tabs
              activeKey={activeTab}
              onChange={setActiveTab}
              items={[
                { key: 'login', label: '登录', children: loginPane },
                { key: 'register', label: '注册', children: registerPane },
              ]}
            />
          </div>

          <div className="mt-5 px-1 flex items-start gap-2.5 text-[12px] text-ink-3">
            <span className="mt-[7px] w-1.5 h-1.5 rounded-full bg-accent/60 shrink-0" aria-hidden />
            <p className="leading-relaxed">
              演示账号 <span className="num text-ink-2">admin / admin123</span>
              ，也可以切到「注册」自己建一个账号。
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}
