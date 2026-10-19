import { Navigate, Route, Routes } from 'react-router-dom';
import { Spin } from 'antd';
import { AuthProvider, useAuth } from './auth/AuthContext';
import AppLayout from './layouts/AppLayout';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Inbox from './pages/Inbox';
import MyRequests from './pages/MyRequests';
import Monitor from './pages/Monitor';
import InstanceDetail from './pages/InstanceDetail';
import FormsPage from './pages/FormsPage';
import FormDesignerPage from './pages/FormDesignerPage';
import ProcessesPage from './pages/ProcessesPage';
import ProcessDesignerPage from './pages/ProcessDesignerPage';
import LookupsPage from './pages/LookupsPage';
import OrgPage from './pages/OrgPage';
import UsersPage from './pages/UsersPage';
import AuditPage from './pages/AuditPage';
import DecisionsPage from './pages/DecisionsPage';
import CalendarsPage from './pages/CalendarsPage';
import ReportsPage from './pages/ReportsPage';

function Protected({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 120 }}><Spin size="large" /></div>;
  if (!user) return <Navigate to="/login" replace />;
  return <AppLayout>{children}</AppLayout>;
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={<Protected><Dashboard /></Protected>} />
        <Route path="/inbox" element={<Protected><Inbox /></Protected>} />
        <Route path="/my-requests" element={<Protected><MyRequests /></Protected>} />
        <Route path="/monitor" element={<Protected><Monitor /></Protected>} />
        <Route path="/instances/:id" element={<Protected><InstanceDetail /></Protected>} />
        <Route path="/forms" element={<Protected><FormsPage /></Protected>} />
        <Route path="/forms/:id/design" element={<Protected><FormDesignerPage /></Protected>} />
        <Route path="/processes" element={<Protected><ProcessesPage /></Protected>} />
        <Route path="/processes/:id/design" element={<Protected><ProcessDesignerPage /></Protected>} />
        <Route path="/decisions" element={<Protected><DecisionsPage /></Protected>} />
        <Route path="/calendars" element={<Protected><CalendarsPage /></Protected>} />
        <Route path="/reports" element={<Protected><ReportsPage /></Protected>} />
        <Route path="/lookups" element={<Protected><LookupsPage /></Protected>} />
        <Route path="/org" element={<Protected><OrgPage /></Protected>} />
        <Route path="/users" element={<Protected><UsersPage /></Protected>} />
        <Route path="/audit" element={<Protected><AuditPage /></Protected>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  );
}
