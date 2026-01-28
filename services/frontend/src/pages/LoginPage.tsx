import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Form, Input, Button, Card, Typography, message, Modal } from 'antd'
import { MailOutlined, LockOutlined } from '@ant-design/icons'
import { useAuth } from '../hooks/useAuth'

const { Title, Text } = Typography

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

  const onFinish = async (values: LoginForm) => {
    setLoading(true)
    try {
      // 使用 email 作为用户名登录
      await login(values.email, values.password)
      message.success('登录成功')
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
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      justifyContent: 'center',
      alignItems: 'center',
      background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)'
    }}>
      <Card style={{ width: 400, borderRadius: 8 }}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <Title level={2} style={{ marginBottom: 8 }}>用户登录</Title>
          <Text type="secondary">统一身份认证平台</Text>
        </div>
        <Form
          name="login"
          onFinish={onFinish}
          autoComplete="off"
          size="large"
        >
          <Form.Item
            name="email"
            rules={[
              { required: true, message: '请输入邮箱' },
              { type: 'email', message: '请输入有效的邮箱地址' }
            ]}
          >
            <Input prefix={<MailOutlined />} placeholder="邮箱" />
          </Form.Item>
          <Form.Item
            name="password"
            rules={[{ required: true, message: '请输入密码' }]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder="密码" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} block>
              登录
            </Button>
          </Form.Item>
        </Form>
        <div style={{ textAlign: 'center', marginBottom: 12 }}>
          <Button
            type="link"
            onClick={() => setForgotPasswordVisible(true)}
            style={{ padding: 0 }}
          >
            忘记密码？
          </Button>
        </div>
        <div style={{ textAlign: 'center' }}>
          <Text>还没有账号？</Text>
          <Link to="/register">立即注册</Link>
        </div>
      </Card>

      {/* 忘记密码 - 输入邮箱 */}
      <Modal
        title="忘记密码"
        open={forgotPasswordVisible}
        onOk={handleForgotPassword}
        onCancel={() => setForgotPasswordVisible(false)}
        confirmLoading={loading}
        okText="发送验证码"
        cancelText="取消"
      >
        <p style={{ marginBottom: 16 }}>
          请输入您的注册邮箱，我们将发送重置验证码：
        </p>
        <Input
          prefix={<MailOutlined />}
          placeholder="请输入邮箱"
          value={forgotEmail}
          onChange={(e) => setForgotEmail(e.target.value)}
        />
      </Modal>

      {/* 重置密码 - 输入验证码和新密码 */}
      <Modal
        title="重置密码"
        open={resetPasswordVisible}
        onOk={handleResetPassword}
        onCancel={() => setResetPasswordVisible(false)}
        confirmLoading={loading}
        okText="重置密码"
        cancelText="取消"
      >
        <p style={{ marginBottom: 16 }}>
          验证码已发送到 <strong>{forgotEmail}</strong>
        </p>
        <Input
          placeholder="请输入6位验证码"
          value={resetCode}
          onChange={(e) => setResetCode(e.target.value)}
          maxLength={6}
          style={{ marginBottom: 12 }}
        />
        <Input.Password
          prefix={<LockOutlined />}
          placeholder="新密码（至少8位，包含大小写字母和数字）"
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
          style={{ marginBottom: 12 }}
        />
        <Input.Password
          prefix={<LockOutlined />}
          placeholder="确认新密码"
          value={confirmNewPassword}
          onChange={(e) => setConfirmNewPassword(e.target.value)}
        />
      </Modal>
    </div>
  )
}
