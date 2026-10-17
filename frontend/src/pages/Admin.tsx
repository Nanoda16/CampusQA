import { useState, useEffect } from 'react';
import { Button, message, Table, Tag, Input, Badge } from 'antd';
import { DeleteOutlined, ReloadOutlined, FireOutlined, DatabaseOutlined, ClockCircleOutlined, ThunderboltOutlined } from '@ant-design/icons';
import api from '../services/api';

function Metric({
  label,
  value,
  icon,
  sub,
}: {
  label: string;
  value: React.ReactNode;
  icon: React.ReactNode;
  sub?: React.ReactNode;
}) {
  return (
    <div className="px-4 py-4 lg:px-5">
      <div className="flex items-center gap-1.5 text-ink-3">
        <span className="text-[11px]">{icon}</span>
        <span className="eyebrow">{label}</span>
      </div>
      <div className="mt-2 num text-[24px] leading-none text-ink-1">{value}</div>
      {sub && <div className="mt-2 text-[11.5px] text-ink-3">{sub}</div>}
    </div>
  );
}

export default function Admin() {
  const [stats, setStats] = useState<any>({});
  const [keys, setKeys] = useState<any[]>([]);
  const [keyPattern, setKeyPattern] = useState('campus:qa:*');
  const [warmupLimit, setWarmupLimit] = useState(10);

  useEffect(() => { loadCacheData(); const timer = setInterval(loadCacheData, 5000); return () => clearInterval(timer); }, []);

  const loadCacheData = async () => {
    try {
      const s: any = await api.get('/admin/cache/stats'); if (s.code === 200) setStats(s.data);
      const k: any = await api.get(`/admin/cache/keys?pattern=${keyPattern}`); if (k.code === 200) setKeys(k.data.keys || []);
    } catch (e) {}
  };

  const clearCache = async (type: string) => {
    const paths: Record<string, string> = { all: '/admin/cache/clear', qa: '/admin/cache/clear/qa', sessions: '/admin/cache/clear/sessions', hot: '/admin/cache/clear/hot' };
    try { const r: any = await api.delete(paths[type]); message.success(r.message); loadCacheData(); } catch (e) {}
  };

  return (
    <div className="space-y-4">
      {/* 概览 */}
      <div className="surface p-4 md:p-5">
        <div className="flex items-center justify-between pb-3 border-b border-rule/70">
          <div className="flex items-baseline gap-3">
            <span className="eyebrow">cache</span>
            <span className="text-[13px] text-ink-2">缓存概览</span>
          </div>
          <div className="flex items-center gap-2">
            <Badge
              status={stats.server_type === 'real' ? 'success' : 'warning'}
              text={<span className="text-[11.5px] text-ink-3">{stats.server_type === 'real' ? 'Redis' : '本地降级'}</span>}
            />
          </div>
        </div>
        <div className="grid grid-cols-2 lg:grid-cols-4 divide-rule/70 [&>*]:border-b [&>*]:border-rule/70 lg:[&>*]:border-b-0 lg:[&>*]:border-r lg:[&>*:last-child]:border-r-0">
          <Metric
            label="total keys"
            value={stats.total_keys || 0}
            icon={<DatabaseOutlined />}
            sub={<>命中率 <span className="num">{stats.hit_ratio !== 'N/A' ? `${stats.hit_ratio}%` : '-'}</span></>}
          />
          <Metric
            label="q&a"
            value={stats.keys_by_prefix?.['Q&A 缓存']?.count || 0}
            icon={<ThunderboltOutlined />}
            sub="问答结果缓存"
          />
          <Metric
            label="sessions"
            value={stats.keys_by_prefix?.['会话缓存']?.count || 0}
            icon={<ClockCircleOutlined />}
            sub="会话上下文"
          />
          <Metric
            label="memory"
            value={<span className="text-[18px]">{stats.memory_human || '-'}</span>}
            icon={<DatabaseOutlined />}
            sub="进程占用"
          />
        </div>
      </div>

      {/* 清理动作 */}
      <div className="surface p-3 flex flex-wrap items-center gap-2">
        <span className="eyebrow px-1">maintenance</span>
        <Button danger icon={<DeleteOutlined />} onClick={() => clearCache('all')}>清空全部</Button>
        <Button icon={<DeleteOutlined />} onClick={() => clearCache('qa')}>清空 Q&A</Button>
        <Button icon={<DeleteOutlined />} onClick={() => clearCache('sessions')}>清空会话</Button>
        <Button icon={<ReloadOutlined />} onClick={() => clearCache('hot')}>重置热门</Button>
        <div className="flex-1" />
        <Button type="primary" icon={<ReloadOutlined />} onClick={loadCacheData}>刷新</Button>
      </div>

      {/* 预热与查询 */}
      <div className="surface p-4 flex flex-wrap items-center gap-2.5">
        <span className="eyebrow">warmup</span>
        <Input
          type="number"
          value={warmupLimit}
          onChange={(e) => setWarmupLimit(Number(e.target.value))}
          style={{ width: 80 }}
          min={1}
          aria-label="预热条数"
        />
        <Button
          icon={<FireOutlined />}
          onClick={async () => {
            try {
              const r: any = await api.post(`/admin/cache/warmup?limit=${warmupLimit}`);
              message.success(r.message);
            } catch (e) {}
          }}
        >
          预热热门
        </Button>
        <div className="w-px h-6 bg-rule mx-1" />
        <span className="eyebrow">pattern</span>
        <Input
          value={keyPattern}
          onChange={(e) => setKeyPattern(e.target.value)}
          style={{ width: 200 }}
          onPressEnter={loadCacheData}
          aria-label="键名匹配"
          className="num"
        />
        <Button onClick={loadCacheData}>查询</Button>
      </div>

      {/* 明细 */}
      <div className="surface overflow-hidden">
        <Table
          rowKey="key"
          dataSource={keys}
          size="small"
          pagination={false}
          columns={[
            {
              title: '缓存条目',
              dataIndex: 'key',
              ellipsis: true,
              render: (_: string, record: any) => (
                <div>
                  <div className="text-[13px] text-ink-1">{record.label || record.key}</div>
                  <div className="num text-[10.5px] text-ink-3 truncate">{record.key}</div>
                </div>
              ),
            },
            {
              title: 'Type',
              dataIndex: 'type',
              width: 90,
              render: (t: string) => <Tag>{t}</Tag>,
            },
            {
              title: 'TTL',
              dataIndex: 'ttl',
              width: 90,
              render: (t: number) => <span className="num text-ink-2">{t >= 0 ? t : '-'}</span>,
            },
          ]}
        />
      </div>
    </div>
  );
}
