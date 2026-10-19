import React, { useEffect, useState } from 'react';
import { Button, Card, Divider, Form, Input, Typography, App } from 'antd';
import { LockOutlined, UserOutlined, SafetyCertificateOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { extractError } from '../api/client';

export default function Login() {
  const { login } = useAuth();
  const { message } = App.useApp();
  const nav = useNavigate();
  const [loading, setLoading] = useState(false);
  const [oidcEnabled, setOidcEnabled] = useState(false);
  const [oidcError, setOidcError] = useState('');

  useEffect(() => {
    // فاز ۵: نمایش دکمه ورود سازمانی در صورت فعال بودن OIDC + خطای بازگشتی از callback
    fetch('/api/v1/auth/config').then((r) => r.json())
      .then((c) => setOidcEnabled(!!c.oidc_enabled)).catch(() => {});
    const params = new URLSearchParams(window.location.search);
    const err = params.get('oidc_error');
    if (err) setOidcError(err === 'state' ? 'نشست ورود سازمانی منقضی شده؛ دوباره تلاش کنید'
      : err === 'inactive' ? 'حساب شما غیرفعال است'
        : err === 'identity' ? 'هویت از سرویس سازمانی دریافت نشد'
          : 'ورود سازمانی ناموفق بود؛ دوباره تلاش کنید');
  }, []);

  const onFinish = async (values: { username: string; password: string }) => {
    setLoading(true);
    try {
      await login(values.username, values.password);
      nav('/');
    } catch (err) {
      message.error(extractError(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'linear-gradient(135deg, #0e7490 0%, #155e75 50%, #164e63 100%)',
    }}>
      <Card style={{ width: 400, boxShadow: '0 12px 40px rgba(0,0,0,0.25)' }}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <Typography.Title level={3} style={{ marginBottom: 4 }}>سامانه مدیریت فرایندهای کسب‌وکار</Typography.Title>
          <Typography.Text type="secondary">BPMS — نسخه ۱.۰</Typography.Text>
        </div>
        <Form layout="vertical" onFinish={onFinish}>
          <Form.Item name="username" label="نام کاربری" rules={[{ required: true, message: 'نام کاربری را وارد کنید' }]}>
            <Input prefix={<UserOutlined />} placeholder="نام کاربری" size="large" />
          </Form.Item>
          <Form.Item name="password" label="گذرواژه" rules={[{ required: true, message: 'گذرواژه را وارد کنید' }]}>
            <Input.Password prefix={<LockOutlined />} placeholder="گذرواژه" size="large" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block size="large" loading={loading}>
            ورود به سامانه
          </Button>
        </Form>
        {oidcEnabled && (
          <>
            <Divider plain style={{ fontSize: 12, margin: '12px 0 8px' }}>یا</Divider>
            <Button block size="large" icon={<SafetyCertificateOutlined />} href="/api/v1/auth/oidc/login">
              ورود سازمانی (SSO سازمانی)
            </Button>
          </>
        )}
        {oidcError && (
          <Typography.Text type="danger" style={{ display: 'block', marginTop: 12, fontSize: 12 }}>
            {oidcError}
          </Typography.Text>
        )}
        <div style={{ marginTop: 16, textAlign: 'center', fontSize: 12, color: '#94a3b8' }}>
          کاربران نمونه: admin / manager / finance1 / user1 — گذرواژه: Bpms@1234
        </div>
      </Card>
    </div>
  );
}
