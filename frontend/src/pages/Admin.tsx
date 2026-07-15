import { Card } from 'antd';
import { DashboardOutlined } from '@ant-design/icons';

export default function Admin() {
  return (
    <Card
      className="shadow-sm"
      title={<><DashboardOutlined className="mr-2" />缓存管理控制台</>}
      bodyStyle={{ padding: 0, height: 'calc(100vh - 180px)' }}
    >
      <iframe
        src="/admin/cache"
        title="Cache Management"
        style={{ width: '100%', height: '100%', border: 'none', borderRadius: '0 0 8px 8px' }}
      />
    </Card>
  );
}
