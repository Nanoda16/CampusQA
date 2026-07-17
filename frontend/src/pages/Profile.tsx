import { useEffect, useState } from 'react';
import { Card, Form, Input, Button, Avatar, message, Statistic, Row, Col } from 'antd';
import { UserOutlined, MailOutlined, EditOutlined, LockOutlined } from '@ant-design/icons';
import api from '../services/api';

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
    <div className="max-w-4xl mx-auto">
      <Row gutter={[24, 24]}>
        <Col xs={24} md={8}>
          <Card className="text-center shadow-sm">
            <Avatar
              size={100}
              icon={<UserOutlined />}
              className="bg-brand-700 mb-4"
            />
            <h3 className="text-xl font-bold text-gray-800 mb-1">{user?.nickname || user?.username}</h3>
            <p className="text-gray-500 mb-4">{user?.email || '未设置邮箱'}</p>
            <div className="text-left space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-500">用户名</span>
                <span className="font-medium">{user?.username}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">角色</span>
                <span className="font-medium">
                  {user?.role === 'admin' ? '管理员' : user?.role === 'teacher' ? '教师' : '学生'}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">状态</span>
                <span className="font-medium text-green-600">{user?.status === 1 ? '正常' : '禁用'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">注册时间</span>
                <span className="font-medium">{user?.created_at ? new Date(user.created_at).toLocaleString() : '-'}</span>
              </div>
            </div>
          </Card>
        </Col>

        <Col xs={24} md={16}>
          <Card className="shadow-sm" title={<><EditOutlined className="mr-2" />编辑资料</>}>
            <Form form={form} onFinish={handleUpdate} layout="vertical">
              <Form.Item label="昵称" name="nickname">
                <Input prefix={<UserOutlined />} placeholder="昵称" />
              </Form.Item>
              <Form.Item label="邮箱" name="email">
                <Input prefix={<MailOutlined />} placeholder="邮箱" />
              </Form.Item>
              <Form.Item label="头像 URL" name="avatar">
                <Input placeholder="头像图片链接" />
              </Form.Item>
              <Form.Item>
                <Button
                  type="primary"
                  htmlType="submit"
                  loading={loading}
                >
                  保存修改
                </Button>
              </Form.Item>
            </Form>
          </Card>

          <Row gutter={[16, 16]} className="mt-6">
            <Col span={24}>
              <Card className="shadow-sm" title={<><LockOutlined className="mr-2" />修改密码</>}>
                <Form onFinish={async (values) => {
                  try {
                    await api.put('/user/change-password', values);
                    message.success('密码修改成功');
                  } catch (e) {}
                }} layout="vertical">
                  <Form.Item label="原密码" name="old_password" rules={[{ required: true, message: '请输入原密码' }]}>
                    <Input.Password prefix={<LockOutlined />} placeholder="原密码" />
                  </Form.Item>
                  <Form.Item label="新密码" name="new_password" rules={[{ required: true, min: 6, message: '密码至少6位' }]}>
                    <Input.Password prefix={<LockOutlined />} placeholder="新密码" />
                  </Form.Item>
                  <Form.Item>
                    <Button type="primary" htmlType="submit" danger>修改密码</Button>
                  </Form.Item>
                </Form>
              </Card>
            </Col>
          </Row>
          <Row gutter={[16, 16]} className="mt-6">
            <Col span={12}>
              <Card className="shadow-sm">
                <Statistic title="用户ID" value={user?.id || '-'} />
              </Card>
            </Col>
            <Col span={12}>
              <Card className="shadow-sm">
                <Statistic title="角色代码" value={user?.role || '-'} />
              </Card>
            </Col>
          </Row>
        </Col>
      </Row>
    </div>
  );
}
