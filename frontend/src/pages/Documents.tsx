import { useState, useEffect } from 'react';
import { Card, Table, Button, Input, Tag, Modal, Form, Select, message, Space, Popconfirm, Upload } from 'antd';
import { PlusOutlined, SearchOutlined, FileTextOutlined, DeleteOutlined, EditOutlined, ReloadOutlined, UploadOutlined } from '@ant-design/icons';
import api from '../services/api';

interface Document {
  id: number; title: string; content?: string; category: string;
  department: string; file_type: string; status: number; created_by: number; created_at: string;
}

export default function Documents() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(false);
  const [pagination, setPagination] = useState({ current: 1, pageSize: 10, total: 0 });
  const [category, setCategory] = useState('');
  const [keyword, setKeyword] = useState('');
  const [categories, setCategories] = useState<string[]>([]);
  const [modalOpen, setModalOpen] = useState(false);
  const [modalMode, setModalMode] = useState<'create' | 'edit'>('create');
  const [editingId, setEditingId] = useState<number | null>(null);
  const [rebuilding, setRebuilding] = useState(false);
  const [form] = Form.useForm();

  const handleRebuild = async () => {
    setRebuilding(true);
    try {
      const res: any = await api.post('/document/rebuild-index');
      if (res.code === 200) {
        message.success(
          `重建索引完成: ${res.data?.docs_count || 0} 篇文档, ${res.data?.chunks_count || 0} 个切片`
        );
        loadDocuments();
      } else {
        message.error(res.message || '重建索引失败');
      }
    } catch (e) {
      message.error('重建索引失败，请检查权限或联系管理员');
    } finally {
      setRebuilding(false);
    }
  };

  useEffect(() => { loadDocuments(); loadCategories(); }, [pagination.current, pagination.pageSize, category, keyword]);

  const loadDocuments = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page: String(pagination.current), page_size: String(pagination.pageSize) });
      if (category) params.set('category', category);
      if (keyword) params.set('keyword', keyword);
      const res: any = await api.get(`/document/list?${params}`);
      if (res.code === 200) { setDocuments(res.data.items); setPagination((p) => ({ ...p, total: res.data.total })); }
    } finally { setLoading(false); }
  };

  const loadCategories = async () => {
    try { const r: any = await api.get('/document/categories'); if (r.code === 200) setCategories(r.data.categories || []); } catch (e) {}
  };

  const openCreate = () => { setModalMode('create'); setEditingId(null); form.resetFields(); form.setFieldsValue({ file_type: 'txt', status: 1 }); setModalOpen(true); };
  const openEdit = async (id: number) => {
    setModalMode('edit'); setEditingId(id);
    try {
      const r: any = await api.get(`/document/${id}`);
      if (r.code === 200) form.setFieldsValue(r.data); setModalOpen(true);
    } catch (e) {}
  };

  const handleSubmit = async () => {
    const values = form.getFieldsValue();
    try {
      if (modalMode === 'create') {
        await api.post('/document', values);
        message.success('文档创建成功');
      } else {
        await api.put(`/document/${editingId}`, values);
        message.success('文档更新成功');
      }
      setModalOpen(false); form.resetFields(); loadDocuments();
    } catch (e) {}
  };

  const handleDelete = async (id: number) => {
    try { await api.delete(`/document/${id}`); message.success('已删除'); loadDocuments(); } catch (e) {}
  };

  const statusMap: Record<number, { label: string; color: string }> = { 0: { label: '草稿', color: 'default' }, 1: { label: '已发布', color: 'success' }, 2: { label: '已归档', color: 'warning' } };

  const columns = [
    { title: 'ID', dataIndex: 'id', width: 60 },
    { title: '标题', dataIndex: 'title', render: (t: string) => <Space><FileTextOutlined className="text-blue-500" /><span className="font-medium">{t}</span></Space> },
    { title: '分类', dataIndex: 'category', width: 110, render: (c: string) => c ? <Tag color="blue">{c}</Tag> : '-' },
    { title: '部门', dataIndex: 'department', width: 120, render: (d: string) => d || '-' },
    { title: '状态', dataIndex: 'status', width: 90, render: (s: number) => <Tag color={statusMap[s]?.color}>{statusMap[s]?.label}</Tag> },
    { title: '创建时间', dataIndex: 'created_at', width: 160, render: (d: string) => new Date(d).toLocaleString() },
    {
      title: '操作', width: 120,
      render: (_: any, r: Document) => (
        <Space>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => openEdit(r.id)}>编辑</Button>
          <Popconfirm title="确认删除？" onConfirm={() => handleDelete(r.id)} okText="删除" cancelText="取消">
            <Button type="link" danger size="small" icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Card className="shadow-sm" title="知识库文档管理">
      <div className="flex flex-wrap gap-3 mb-4">
        <Input placeholder="搜索标题" value={keyword} onChange={(e) => setKeyword(e.target.value)} prefix={<SearchOutlined />} style={{ width: 240 }} allowClear />
        <Select placeholder="选择分类" value={category || undefined} onChange={(v) => setCategory(v || '')} allowClear style={{ width: 160 }} options={categories.map((c) => ({ label: c, value: c }))} />
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate} className="bg-gradient-to-r from-blue-500 to-indigo-600">新增文档</Button>
        <Button
          icon={<ReloadOutlined />}
          onClick={handleRebuild}
          loading={rebuilding}
          disabled={rebuilding}
          className="bg-gradient-to-r from-orange-500 to-red-600 text-white border-none hover:opacity-90"
        >
          {rebuilding ? '重建中...' : '重建索引'}
        </Button>
      </div>
      <Table rowKey="id" columns={columns} dataSource={documents} loading={loading}
        pagination={{ ...pagination, showSizeChanger: true, showTotal: (t) => `共 ${t} 条`, onChange: (p, ps) => setPagination({ current: p, pageSize: ps, total: pagination.total }) }} />
      <Modal title={modalMode === 'create' ? '新增文档' : '编辑文档'} open={modalOpen} onCancel={() => setModalOpen(false)} onOk={handleSubmit} okText={modalMode === 'create' ? '创建' : '保存'} width={600}>
        <Form form={form} layout="vertical">
          <Form.Item label="标题" name="title" rules={[{ required: true, message: '请输入标题' }]}><Input /></Form.Item>
          <Form.Item label="内容" name="content"><Input.TextArea rows={6} /></Form.Item>
          <Form.Item label="上传 .txt 文件">
            <Upload
              accept=".txt"
              beforeUpload={(file) => {
                const reader = new FileReader();
                reader.onload = (e) => {
                  const text = e.target?.result as string;
                  form.setFieldsValue({ content: text, file_type: 'txt' });
                  message.success(`已读取文件: ${file.name}`);
                };
                reader.readAsText(file);
                return false; // 阻止自动上传
              }}
              showUploadList={false}
            >
              <Button icon={<UploadOutlined />}>选择 .txt 文件</Button>
            </Upload>
          </Form.Item>
          <Form.Item label="分类" name="category"><Input /></Form.Item>
          <Form.Item label="部门" name="department"><Input /></Form.Item>
          <Form.Item label="文件类型" name="file_type">
            <Select options={[{ label: 'TXT', value: 'txt' }, { label: 'PDF', value: 'pdf' }, { label: 'DOCX', value: 'docx' }, { label: 'MD', value: 'md' }]} />
          </Form.Item>
          <Form.Item label="状态" name="status">
            <Select options={[{ label: '草稿', value: 0 }, { label: '已发布', value: 1 }, { label: '已归档', value: 2 }]} />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}
