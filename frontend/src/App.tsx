import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { AuthProvider, useAuth } from './context/AuthContext';
import AppLayout from './components/Layout';
import Login from './pages/Login';
import Chat from './pages/Chat';
import Documents from './pages/Documents';
import Profile from './pages/Profile';
import Admin from './pages/Admin';
import UserManagement from './pages/UserManagement';

const FONT_SANS =
  "'PingFang SC', 'HarmonyOS Sans SC', 'Source Han Sans SC', 'Noto Sans SC', " +
  "'Microsoft YaHei UI', 'Microsoft YaHei', system-ui, -apple-system, 'Segoe UI', sans-serif";

/* 设计令牌与 index.css 中 :root 保持一致 */
const T = {
  paper0: '#f6f2e9',
  paper1: '#fbf8f1',
  paper2: '#ffffff',
  ink1: '#1c1b17',
  ink2: '#55504a',
  ink3: '#746d61',
  rule: '#e4ddce',
  rule2: '#d3c9b7',
  accent: '#a63d2f',
  accentWash: '#f5e5de',
  ok: '#41694f',
  warn: '#a87616',
  danger: '#a33128',
};

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuth();
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" replace />;
}

function App() {
  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: T.accent,
          colorInfo: T.accent,
          colorSuccess: T.ok,
          colorWarning: T.warn,
          colorError: T.danger,
          colorText: T.ink1,
          colorTextSecondary: T.ink2,
          colorTextTertiary: T.ink3,
          colorTextQuaternary: '#9b9487',
          colorBgBase: T.paper2,
          colorBgContainer: T.paper2,
          colorBgElevated: T.paper2,
          colorBgLayout: T.paper0,
          colorBorder: T.rule,
          colorBorderSecondary: '#eee8db',
          colorFillAlter: '#faf6ee',
          borderRadius: 8,
          borderRadiusLG: 12,
          borderRadiusSM: 4,
          fontFamily: FONT_SANS,
          fontSize: 14,
          controlHeight: 36,
          lineWidth: 1,
          wireframe: false,
          boxShadow: '0 1px 2px rgba(28,27,23,0.05), 0 10px 24px -14px rgba(28,27,23,0.18)',
          boxShadowSecondary: '0 2px 4px rgba(28,27,23,0.06), 0 18px 40px -20px rgba(28,27,23,0.22)',
        },
        components: {
          Layout: {
            bodyBg: T.paper0,
            headerBg: 'transparent',
            siderBg: T.paper1,
            triggerBg: T.paper1,
          },
          Menu: {
            itemBg: 'transparent',
            subMenuItemBg: 'transparent',
            itemColor: T.ink2,
            itemHoverColor: T.ink1,
            itemHoverBg: '#f1ebdd',
            itemSelectedBg: T.paper2,
            itemSelectedColor: T.ink1,
            itemActiveBg: T.paper2,
            itemBorderRadius: 8,
            itemHeight: 40,
            itemMarginInline: 8,
            itemMarginBlock: 2,
            iconSize: 15,
            collapsedIconSize: 16,
          },
          Card: {
            colorBgContainer: T.paper2,
            paddingLG: 20,
            headerBg: 'transparent',
            headerFontSize: 14,
          },
          Table: {
            headerBg: '#faf6ee',
            headerColor: T.ink2,
            headerSplitColor: 'transparent',
            borderColor: '#eee8db',
            rowHoverBg: '#faf6ee',
            cellPaddingBlock: 12,
            headerBorderRadius: 8,
          },
          Input: {
            activeBorderColor: T.accent,
            hoverBorderColor: T.rule2,
            activeShadow: '0 0 0 3px rgba(166,61,47,0.12)',
            paddingBlock: 6,
          },
          Button: {
            defaultShadow: 'none',
            primaryShadow: 'none',
            dangerShadow: 'none',
            fontWeight: 500,
          },
          Tabs: {
            inkBarColor: T.accent,
            itemSelectedColor: T.ink1,
            itemColor: T.ink3,
            itemHoverColor: T.ink1,
            titleFontSize: 14,
          },
          Tag: {
            defaultBg: '#f6f1e6',
            defaultColor: T.ink2,
          },
          Modal: {
            contentBg: T.paper2,
            headerBg: T.paper2,
          },
          Empty: {
            colorTextDescription: T.ink3,
          },
        },
      }}
    >
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route
              path="/*"
              element={
                <ProtectedRoute>
                  <AppLayout />
                </ProtectedRoute>
              }
            >
              <Route path="chat" element={<Chat />} />
              <Route path="documents" element={<Documents />} />
              <Route path="profile" element={<Profile />} />
              <Route path="admin" element={<Admin />} />
              <Route path="users" element={<UserManagement />} />
              <Route path="" element={<Navigate to="/chat" replace />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </ConfigProvider>
  );
}

export default App;
