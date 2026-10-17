import { useEffect, useState } from 'react';
import { Form, Input, Button, message } from 'antd';
import { UserOutlined, MailOutlined, EditOutlined, LockOutlined } from '@ant-design/icons';
import api from '../services/api';

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-2 border-b border-rule/60 last:border-0">
      <span className="eyebrow shrink-0">{label}</span>
      <span className="text-[13px] text-ink-1 text-right break-all">{value}</span>
    </div>
  );
}

export default function Profile() {
  const [form] = Form.useForm();
  const [user, setUser] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    loadProfile();
  }, []);

  const loadProfile = async () => {
    try {
      const res: any = await api.get('/user/profile');
      if (res.code === 200) {
        setUser(res.data);
        form.setFieldsValue({
          nickname: res.data.nickname,
          email: res.data.email,
          avatar: res.data.avatar,
        });
      }
    } catch (e) {}
  };

  const handleUpdate = async (values: any) => {
    setLoading(true);
    try {
      const res: any = await api.put('/user/profile', values);
      if (res.code === 200) {
        message.success('资料更新成功');
        setUser(res.data);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-[minmax(0,1fr)_minmax(0,1.45fr)] gap-4">
        {/* 身份 */}
        <div className="surface-sub p-6 text-center flex flex-col items-center justify-center">
          <span className="grid place-items-center w-16 h-16 rounded-[14px] bg-accent-wash text-accent border border-[#ecd6cd] text-[22px] font-semibold">
            {(user?.nickname || user?.username || '?').slice(0, 1)}
          </span>
          <h3 className="mt-4 text-[16px] font-semibold tracking-tight">
            {user?.nickname || user?.username || '未登录'}
          </h3>
          <p className="mt-1 text-[12.5px] text-ink-3">{user?.email || '未设置邮箱'}</p>
          <div className="mt-4 eyebrow">
            {user?.role === 'admin' ? 'administrator' : user?.role === 'teacher' ? 'teacher' : 'student'}
          </div>
        </div>

        {/* 账号信息 */}
        <div className="surface p-5">
          <div className="flex items-center gap-2 pb-3">
            <span className="eyebrow">account</span>
          </div>
          <Row label="用户名" value={<span className="num">{user?.username || '-'}</span>} />
          <Row
            label="状态"
            value={
              <span className={user?.status === 1 ? 'text-ok' : 'text-danger'}>
                {user?.status === 1 ? '正常' : '已禁用'}
              </span>
            }
          />
          <Row label="用户 ID" value={<span className="num">{user?.id ?? '-'}</span>} />
          <Row
            label="注册时间"
            value={
              <span className="num text-[12px]">
                {user?.created_at ? new Date(user.created_at).toLocaleString() : '-'}
              </span>
            }
          />
        </div>
      </div>

      {/* 编辑资料 */}
      <div className="surface p-5">
        <div className="flex items-center gap-2 pb-4">
          <EditOutlined className="text-accent text-[13px]" />
          <span className="eyebrow">profile</span>
          <span className="text-[13px] text-ink-2">编辑资料</span>
        </div>
        <Form form={form} onFinish={handleUpdate} layout="vertical" className="max-w-xl">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4">
            <Form.Item label="昵称" name="nickname">
              <Input prefix={<UserOutlined className="text-ink-3" />} placeholder="昵称" />
            </Form.Item>
            <Form.Item label="邮箱" name="email">
              <Input prefix={<MailOutlined className="text-ink-3" />} placeholder="邮箱" />
            </Form.Item>
          </div>
          <Form.Item label="头像 URL" name="avatar">
            <Input placeholder="头像图片链接（可选）" />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={loading}>
            保存修改
          </Button>
        </Form>
      </div>

      {/* 修改密码 */}
      <div className="surface p-5">
        <div className="flex items-center gap-2 pb-4">
          <LockOutlined className="text-accent text-[13px]" />
          <span className="eyebrow">security</span>
          <span className="text-[13px] text-ink-2">修改密码</span>
        </div>
        <Form
          onFinish={async (values) => {
            try {
              await api.put('/user/change-password', values);
              message.success('密码修改成功');
            } catch (e) {}
          }}
          layout="vertical"
          className="max-w-xl"
        >
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4">
            <Form.Item
              label="原密码"
              name="old_password"
              rules={[{ required: true, message: '请输入原密码' }]}
            >
              <Input.Password prefix={<LockOutlined className="text-ink-3" />} placeholder="原密码" />
            </Form.Item>
            <Form.Item
              label="新密码"
              name="new_password"
              rules={[{ required: true, min: 6, message: '密码至少 6 位' }]}
            >
              <Input.Password prefix={<LockOutlined className="text-ink-3" />} placeholder="新密码" />
            </Form.Item>
          </div>
          <Button danger htmlType="submit">
            修改密码
          </Button>
        </Form>
      </div>
    </div>
  );
}
