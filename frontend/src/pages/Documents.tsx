import { useState, useEffect } from 'react';
import {
  Card,
  Table,
  Button,
  Input,
  Tag,
  Modal,
  Form,
  Select,
  message,
  Space,
  Popconfirm,
} from 'antd';
import { PlusOutlined, SearchOutlined, FileTextOutlined, DeleteOutlined } from '@ant-design/icons';
import api from '../services/api';

interface Document {
  id: number;
  title: string;
  category: string;
  department: string;
  file_type: string;
  status: number;
  created_by: number;
  created_at: string;
}

export default function Documents() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(false);
  const [pagination, setPagination] = useState({ current: 1, pageSize: 10, total: 0 });
  const [category, setCategory] = useState<string>('');
  const [keyword, setKeyword] = useState('');
  const [categories, setCategories] = useState<string[]>([]);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [form] = Form.useForm();

  useEffect(() => {
    loadDocuments();
    loadCategories();
  }, [pagination.current, pagination.pageSize, category, keyword]);

  const loadDocuments = async () => {
    setLoading(true);
    try {
      const params: any = {
        page: pagination.current,
        page_size: pagination.pageSize,
      };
      if (category) params.category = category;
      if (keyword) params.keyword = keyword;

      const query = new URLSearchParams(params).toString();
      const res: any = await api.get(`/document/list?${query}`);
      if (res.code === 200) {
        setDocuments(res.data.items);
        setPagination((p) => ({ ...p, total: res.data.total }));
      }
    } finally {
      setLoading(false);
    }
  };

  const loadCategories = async () => {
    try {
      const res: any = await api.get('/document/categories');
      if (res.code === 200) {
        setCategories(res.data.categories || []);
      }
    } catch (e) {}
  };

  const handleCreate = async (values: any) => {
    try {
      const res: any = await api.post('/document', values);
      if (res.code === 200) {
        message.success('文档创建成功');
        setIsModalOpen(false);
        form.resetFields();
        loadDocuments();
      }
    } catch (e) {}
  };

  const handleDelete = async (id: number) => {
    try {
      await api.delete(`/document/${id}`);
      message.success('文档已删除');
      loadDocuments();
    } catch (e) {}
  };

  const statusMap: Record<number, { label: string; color: string }> = {
    0: { label: '草稿', color: 'default' },
    1: { label: '已发布', color: 'success' },
    2: { label: '已归档', color: 'warning' },
  };

  const columns = [
    {
      title: 'ID',
      dataIndex: 'id',
      width: 70,
    },
    {
      title: '标题',
      dataIndex: 'title',
      render: (text: string) => (
        <Space>
          <FileTextOutlined className="text-blue-500" />
          <span className="font-medium">{text}</span>
        </Space>
      ),
    },
    {
      title: '分类',
      dataIndex: 'category',
      width: 120,
      render: (cat: string) => cat ? <Tag color="blue">{cat}</Tag> : '-',
    },
    {
      title: '部门',
      dataIndex: 'department',
      width: 140,
      render: (dept: string) => dept || '-',
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (status: number) => (
        <Tag color={statusMap[status]?.color}>{statusMap[status]?.label}</Tag>
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 170,
      render: (date: string) => new Date(date).toLocaleString(),
    },
    {
      title: '操作',
      width: 100,
      render: (_: any, record: Document) => (
        <Popconfirm
          title="确认删除？"
          description="删除后将无法恢复"
          onConfirm={() => handleDelete(record.id)}
          okText="删除"
          cancelText="取消"
        >
          <Button type="text" danger icon={<DeleteOutlined />} size="small" />
        </Popconfirm>
      ),
    },
  ];

  return (
    <Card className="shadow-sm" title="知识库文档管理">
      <div className="flex flex-wrap gap-3 mb-4">
        <Input
          placeholder="搜索标题"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          prefix={<SearchOutlined />}
          style={{ width: 240 }}
          allowClear
        />
        <Select
          placeholder="选择分类"
          value={category || undefined}
          onChange={(val) => setCategory(val || '')}
          allowClear
          style={{ width: 160 }}
          options={categories.map((c) => ({ label: c, value: c }))}
        />
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => setIsModalOpen(true)}
          className="bg-gradient-to-r from-blue-500 to-indigo-600 ml-auto"
        >
          新增文档
        </Button>
      </div>

      <Table
        rowKey="id"
        columns={columns}
        dataSource={documents}
        loading={loading}
        pagination={{
          ...pagination,
          showSizeChanger: true,
          showTotal: (total) => `共 ${total} 条`,
          onChange: (page, pageSize) => setPagination({ current: page, pageSize, total: pagination.total }),
        }}
      />

      <Modal
        title="新增文档"
        open={isModalOpen}
        onCancel={() => setIsModalOpen(false)}
        footer={null}
      >
        <Form form={form} onFinish={handleCreate} layout="vertical">
          <Form.Item
            label="标题"
            name="title"
            rules={[{ required: true, message: '请输入标题' }]}
          >
            <Input placeholder="文档标题" />
          </Form.Item>
          <Form.Item label="内容" name="content">
            <Input.TextArea rows={4} placeholder="文档内容" />
          </Form.Item>
          <Form.Item label="分类" name="category">
            <Input placeholder="例如：academic, news" />
          </Form.Item>
          <Form.Item label="部门" name="department">
            <Input placeholder="所属部门" />
          </Form.Item>
          <Form.Item label="文件类型" name="file_type" initialValue="txt">
            <Select
              options={[
                { label: 'TXT', value: 'txt' },
                { label: 'PDF', value: 'pdf' },
                { label: 'DOCX', value: 'docx' },
                { label: 'MD', value: 'md' },
              ]}
            />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block className="bg-gradient-to-r from-blue-500 to-indigo-600">
              创建
            </Button>
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}
