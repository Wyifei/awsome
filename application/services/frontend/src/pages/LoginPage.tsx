import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Form, Input, Button, Typography, message, Modal } from 'antd'
import { MailOutlined, LockOutlined } from '@ant-design/icons'
import { useAuth } from '../contexts/AuthContext'

const { Title, Text } = Typography

// Electric Bolt SVG Icon for brand identity
const ElectricBoltIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path
      d="M13 2L3 14H12L11 22L21 10H12L13 2Z"
      fill="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
)

interface LoginForm {
  email: string
  password: string
}

export default function LoginPage() {
  const [loading, setLoading] = useState(false)
  const [forgotPasswordVisible, setForgotPasswordVisible] = useState(false)
  const [resetPasswordVisible, setResetPasswordVisible] = useState(false)
  const [forgotEmail, setForgotEmail] = useState('')
  const [resetCode, setResetCode] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmNewPassword, setConfirmNewPassword] = useState('')
  const { login, forgotPassword, resetPassword } = useAuth()
  const navigate = useNavigate()

  const onFinish = async (values: LoginForm) => {
    setLoading(true)
    try {
      await login(values.email, values.password)
      message.success('登录成功')
      navigate('/dashboard')
    } catch (error) {
      message.error(error instanceof Error ? error.message : '登录失败')
    } finally {
      setLoading(false)
    }
  }

  const handleForgotPassword = async () => {
    if (!forgotEmail) {
      message.error('请输入邮箱')
      return
    }
    setLoading(true)
    try {
      await forgotPassword(forgotEmail)
      message.success('重置验证码已发送到您的邮箱')
      setForgotPasswordVisible(false)
      setResetPasswordVisible(true)
    } catch (error) {
      message.error(error instanceof Error ? error.message : '发送失败')
    } finally {
      setLoading(false)
    }
  }

  const handleResetPassword = async () => {
    if (!resetCode) {
      message.error('请输入验证码')
      return
    }
    if (!newPassword) {
      message.error('请输入新密码')
      return
    }
    if (newPassword !== confirmNewPassword) {
      message.error('两次输入的密码不一致')
      return
    }
    if (newPassword.length < 8) {
      message.error('密码至少8个字符')
      return
    }
    setLoading(true)
    try {
      await resetPassword(forgotEmail, resetCode, newPassword)
      message.success('密码重置成功，请登录')
      setResetPasswordVisible(false)
      setForgotEmail('')
      setResetCode('')
      setNewPassword('')
      setConfirmNewPassword('')
    } catch (error) {
      message.error(error instanceof Error ? error.message : '重置失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="auth-page-container">
      <div className="glass-card" style={{ width: 420, padding: '40px 40px 32px' }}>
        {/* Brand Logo */}
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <div className="brand-logo">
            <div className="brand-icon">
              <ElectricBoltIcon />
            </div>
          </div>
          <Title level={2} className="auth-title" style={{ marginTop: 16 }}>
            欢迎回来
          </Title>
          <Text className="auth-subtitle">
            E-Mobility 统一身份认证平台
          </Text>
        </div>

        {/* Login Form */}
        <Form
          name="login"
          onFinish={onFinish}
          autoComplete="off"
          size="large"
          className="auth-form"
        >
          <Form.Item
            name="email"
            rules={[
              { required: true, message: '请输入邮箱' },
              { type: 'email', message: '请输入有效的邮箱地址' }
            ]}
          >
            <Input
              prefix={<MailOutlined />}
              placeholder="工作邮箱"
            />
          </Form.Item>
          <Form.Item
            name="password"
            rules={[{ required: true, message: '请输入密码' }]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="密码"
            />
          </Form.Item>
          <Form.Item style={{ marginBottom: 16 }}>
            <Button type="primary" htmlType="submit" loading={loading} block>
              登录
            </Button>
          </Form.Item>
        </Form>

        {/* Forgot Password Link */}
        <div style={{ textAlign: 'center', marginBottom: 20 }}>
          <Button
            type="link"
            onClick={() => setForgotPasswordVisible(true)}
            style={{ padding: 0, color: '#6b7280', fontSize: 14 }}
          >
            忘记密码？
          </Button>
        </div>

        {/* Divider */}
        <div className="auth-divider">
          <span>还没有账号？</span>
        </div>

        {/* Register Link */}
        <div style={{ textAlign: 'center' }}>
          <Link to="/register" className="auth-link" style={{ fontSize: 15 }}>
            创建企业账号
          </Link>
        </div>

        {/* Footer */}
        <div style={{
          textAlign: 'center',
          marginTop: 32,
          paddingTop: 24,
          borderTop: '1px solid #e5e7eb'
        }}>
          <Text style={{ color: '#9ca3af', fontSize: 12 }}>
            © 2024 E-Mobility Platform. 企业级身份认证解决方案
          </Text>
        </div>
      </div>

      {/* Forgot Password Modal */}
      <Modal
        title="找回密码"
        open={forgotPasswordVisible}
        onOk={handleForgotPassword}
        onCancel={() => setForgotPasswordVisible(false)}
        confirmLoading={loading}
        okText="发送验证码"
        cancelText="取消"
        centered
      >
        <div style={{ padding: '8px 0' }}>
          <Text style={{ color: '#6b7280', display: 'block', marginBottom: 16 }}>
            请输入您的注册邮箱，我们将发送密码重置验证码：
          </Text>
          <Input
            prefix={<MailOutlined style={{ color: '#9ca3af' }} />}
            placeholder="请输入邮箱"
            value={forgotEmail}
            onChange={(e) => setForgotEmail(e.target.value)}
            size="large"
            style={{ borderRadius: 8 }}
          />
        </div>
      </Modal>

      {/* Reset Password Modal */}
      <Modal
        title="重置密码"
        open={resetPasswordVisible}
        onOk={handleResetPassword}
        onCancel={() => setResetPasswordVisible(false)}
        confirmLoading={loading}
        okText="确认重置"
        cancelText="取消"
        centered
      >
        <div style={{ padding: '8px 0' }}>
          <Text style={{ color: '#6b7280', display: 'block', marginBottom: 16 }}>
            验证码已发送到 <strong style={{ color: '#111827' }}>{forgotEmail}</strong>
          </Text>
          <Input
            placeholder="请输入6位验证码"
            value={resetCode}
            onChange={(e) => setResetCode(e.target.value)}
            maxLength={6}
            size="large"
            style={{ marginBottom: 12, borderRadius: 8 }}
          />
          <Input.Password
            prefix={<LockOutlined style={{ color: '#9ca3af' }} />}
            placeholder="新密码（至少8位，包含大小写字母和数字）"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            size="large"
            style={{ marginBottom: 12, borderRadius: 8 }}
          />
          <Input.Password
            prefix={<LockOutlined style={{ color: '#9ca3af' }} />}
            placeholder="确认新密码"
            value={confirmNewPassword}
            onChange={(e) => setConfirmNewPassword(e.target.value)}
            size="large"
            style={{ borderRadius: 8 }}
          />
        </div>
      </Modal>
    </div>
  )
}
