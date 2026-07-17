import { useState, useEffect, useRef, useCallback } from 'react';
import {
  Card, Table, Button, Input, Tag, Modal, Form, Select, message,
  Space, Popconfirm, Upload,
} from 'antd';
import {
  PlusOutlined, SearchOutlined, FileTextOutlined,
  DeleteOutlined, ReloadOutlined, UploadOutlined, RedoOutlined,
} from '@ant-design/icons';
import api from '../services/api';

/* ---------- types ---------- */
interface Document {
  id: number;
  title: string;
  content?: string;
  category: string;
  department: string;
  file_type: string;
  status: number;
  chunk_count?: number;
  created_by: number;
  created_at: string;
}

/* status labels matching backend enum:
   1=UPLOADED, 2=PROCESSING, 3=READY, 4=FAILED */
const STATUS_MAP: Record<number, { label: string; color: string }> = {
  1: { label: '待处理', color: 'gold' },
  2: { label: '处理中', color: 'processing' },
  3: { label: '已完成', color: 'success' },
  4: { label: '处理失败', color: 'error' },
};

/* ---------- component ---------- */
export default function Documents() {
  /* ---- state ---- */
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
  const [uploading, setUploading] = useState(false);
  const [form] = Form.useForm();

  /* polling ref — 3 s interval while any row is 1 or 2 */
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const loadDocRef = useRef<() => Promise<void>>(undefined);

  const stopPoll = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  useEffect(() => {
    return () => stopPoll();
  }, [stopPoll]);

  /* ---- data fetching ---- */
  const loadDocuments = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        page: String(pagination.current),
        page_size: String(pagination.pageSize),
      });
      if (category) params.set('category', category);
      if (keyword) params.set('keyword', keyword);
      const res: any = await api.get(`/document/list?${params}`);
      if (res.code === 200) {
        const items: Document[] = res.data.items;
        setDocuments(items);
        setPagination((p) => ({ ...p, total: res.data.total }));

        /* start / stop 3s polling based on pending statuses */
        const hasPending = items.some((d) => d.status === 1 || d.status === 2);
        if (hasPending && !pollRef.current) {
          pollRef.current = setInterval(() => {
            loadDocRef.current?.();
          }, 3000);
        } else if (!hasPending) {
          stopPoll();
        }
      }
    } finally {
      setLoading(false);
    }
  }, [pagination.current, pagination.pageSize, category, keyword, stopPoll]);

  /* keep ref in sync so interval always calls latest version */
  loadDocRef.current = loadDocuments;

  const loadCategories = async () => {
    try {
      const r: any = await api.get('/document/categories');
      if (r.code === 200) setCategories(r.data.categories || []);
    } catch {
      /* ignore */
    }
  };

  useEffect(() => {
    loadDocuments();
    loadCategories();
    // only re-run when filter/page changes — polling manages itself
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pagination.current, pagination.pageSize, category, keyword]);

  /* ---- upload ---- */
  const beforeUpload = (file: File) => {
    const allowedTypes = '.pdf,.doc,.docx,.txt';
    const ext = '.' + file.name.split('.').pop()?.toLowerCase();
    if (!allowedTypes.includes(ext)) {
      message.error(`不支持的文件格式: ${ext}，允许: ${allowedTypes}`);
      return Upload.LIST_IGNORE;
    }
    if (file.size > 50 * 1024 * 1024) {
      message.error('文件大小不能超过 50MB');
      return Upload.LIST_IGNORE;
    }
    return true;
  };

  const customUpload = async (options: any) => {
    const { file, onSuccess, onError } = options;
    const formData = new FormData();
    formData.append('file', file as File);
    setUploading(true);
    try {
      const res: any = await api.post('/document/upload', formData, {
        timeout: 120000,
      });
      if (res.code === 200) {
        message.success('上传成功，正在处理');
        onSuccess(res);
        /* jump to page 1 and always refresh so the new doc is visible */
        setPagination((p) => ({ ...p, current: 1 }));
        await loadDocRef.current?.();
      } else {
        message.error(res.message || '上传失败');
        onError(new Error(res.message));
      }
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '上传请求失败');
      onError(err);
    } finally {
      setUploading(false);
    }
  };

  /* ---- crud ---- */
  const openCreate = () => {
    setModalMode('create');
    setEditingId(null);
    form.resetFields();
    setModalOpen(true);
  };

  const openEdit = async (id: number) => {
    setModalMode('edit');
    setEditingId(id);
    try {
      const r: any = await api.get(`/document/${id}`);
      if (r.code === 200) form.setFieldsValue(r.data);
      setModalOpen(true);
    } catch {
      /* ignore */
    }
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
      setModalOpen(false);
      form.resetFields();
      loadDocuments();
    } catch {
      /* error toast from interceptor */
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await api.delete(`/document/${id}`);
      message.success('已删除');
      loadDocuments();
    } catch {
      /* error toast from interceptor */
    }
  };

  const handleReprocess = async (id: number) => {
    try {
      const res: any = await api.post(`/document/${id}/reprocess`);
      if (res.code === 200) {
        message.success('已提交重新处理');
        loadDocuments();
      } else {
        message.error(res.message || '操作失败');
      }
    } catch {
      /* error toast from interceptor */
    }
  };

  const handleRebuild = async () => {
    setRebuilding(true);
    try {
      const res: any = await api.post('/document/rebuild-index');
      if (res.code === 200) {
        message.success(
          `重建索引完成: ${res.data?.docs_count || 0} 篇文档, ${res.data?.chunks_count || 0} 个切片`,
        );
        loadDocuments();
      } else {
        message.error(res.message || '重建索引失败');
      }
    } catch {
      message.error('重建索引失败，请检查权限或联系管理员');
    } finally {
      setRebuilding(false);
    }
  };

  /* ---- columns ---- */
  const columns = [
    { title: 'ID', dataIndex: 'id', width: 60 },
    {
      title: '标题',
      dataIndex: 'title',
      render: (t: string) => (
        <Space>
          <FileTextOutlined className="text-blue-500" />
          <span className="font-medium">{t}</span>
        </Space>
      ),
    },
    {
      title: '分类',
      dataIndex: 'category',
      width: 110,
      render: (c: string) => (c ? <Tag color="blue">{c}</Tag> : '-'),
    },
    {
      title: '部门',
      dataIndex: 'department',
      width: 120,
      render: (d: string) => d || '-',
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 90,
      render: (s: number) => {
        const st = STATUS_MAP[s];
        return st ? <Tag color={st.color}>{st.label}</Tag> : <Tag>{s}</Tag>;
      },
    },
    {
      title: '切片数',
      dataIndex: 'chunk_count',
      width: 80,
      render: (c: number) => (c != null ? c : '-'),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 160,
      render: (d: string) => new Date(d).toLocaleString(),
    },
    {
      title: '操作',
      width: 180,
      render: (_: any, r: Document) => (
        <Space>
          <Button type="link" size="small" onClick={() => openEdit(r.id)}>
            编辑
          </Button>
          {r.status === 4 && (
            <Button
              type="link"
              size="small"
              icon={<RedoOutlined />}
              onClick={() => handleReprocess(r.id)}
            >
              重新处理
            </Button>
          )}
          <Popconfirm
            title="确认删除？"
            onConfirm={() => handleDelete(r.id)}
            okText="删除"
            cancelText="取消"
          >
            <Button type="link" danger size="small" icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  /* ---- render ---- */
  return (
    <Card className="shadow-sm" title="知识库文档管理">
      {/* Toolbar */}
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
          onChange={(v) => setCategory(v || '')}
          allowClear
          style={{ width: 160 }}
          options={categories.map((c) => ({ label: c, value: c }))}
        />

        {/* File upload — primary action. accept lists real extensions so Windows dialog shows all supported types (bare "*" is invalid and breaks the picker). */}
        <Upload
          accept=".pdf,.doc,.docx,.txt"
          showUploadList={false}
          beforeUpload={beforeUpload}
          customRequest={customUpload}
          disabled={uploading}
        >
          <Button
            type="primary"
            icon={<UploadOutlined />}
            loading={uploading}
          >
            {uploading ? '上传中...' : '上传文档'}
          </Button>
        </Upload>

        <Button icon={<PlusOutlined />} onClick={openCreate}>
          新建文档
        </Button>

        <Button
          icon={<ReloadOutlined />}
          onClick={handleRebuild}
          loading={rebuilding}
          disabled={rebuilding}
        >
          {rebuilding ? '重建中...' : '重建索引'}
        </Button>
      </div>

      {/* Table */}
      <Table
        rowKey="id"
        columns={columns}
        dataSource={documents}
        loading={loading}
        pagination={{
          ...pagination,
          showSizeChanger: true,
          showTotal: (t) => `共 ${t} 条`,
          onChange: (p, ps) => setPagination({ current: p, pageSize: ps, total: pagination.total }),
        }}
      />

      {/* Create / Edit modal */}
      <Modal
        title={modalMode === 'create' ? '新建文档' : '编辑文档'}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={handleSubmit}
        okText={modalMode === 'create' ? '创建' : '保存'}
        width={600}
      >
        <Form form={form} layout="vertical">
          <Form.Item
            label="标题"
            name="title"
            rules={[{ required: true, message: '请输入标题' }]}
          >
            <Input />
          </Form.Item>
          <Form.Item label="内容" name="content">
            <Input.TextArea rows={5} placeholder="可选，上传文件会自动提取内容" />
          </Form.Item>
          <Form.Item label="分类" name="category">
            <Input placeholder="可选" />
          </Form.Item>
          <Form.Item label="部门" name="department">
            <Input placeholder="可选" />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}
