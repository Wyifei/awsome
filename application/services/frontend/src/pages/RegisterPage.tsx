import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Form, Input, Button, Typography, message, Modal } from 'antd'
import { LockOutlined, MailOutlined } from '@ant-design/icons'
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

interface RegisterForm {
  email: string
  password: string
  confirmPassword: string
}

export default function RegisterPage() {
  const [loading, setLoading] = useState(false)
  const [verifyModalVisible, setVerifyModalVisible] = useState(false)
  const [verifyEmail, setVerifyEmail] = useState('')
  const [verifyCode, setVerifyCode] = useState('')
  const [resendLoading, setResendLoading] = useState(false)
  const { register, confirmRegistration, resendVerificationCode } = useAuth()
  const navigate = useNavigate()

  const onFinish = async (values: RegisterForm) => {
    setLoading(true)
    try {
      await register(values.email, values.email, values.password)
      setVerifyEmail(values.email)
      setVerifyModalVisible(true)
      message.success('注册成功，验证码已发送到您的邮箱')
    } catch (error) {
      message.error(error instanceof Error ? error.message : '注册失败')
    } finally {
      setLoading(false)
    }
  }

  const handleVerify = async () => {
    if (!verifyCode) {
      message.error('请输入验证码')
      return
    }
    setLoading(true)
    try {
      await confirmRegistration(verifyEmail, verifyCode)
      message.success('验证成功，请登录')
      setVerifyModalVisible(false)
      navigate('/login')
    } catch (error) {
      message.error(error instanceof Error ? error.message : '验证失败')
    } finally {
      setLoading(false)
    }
  }

  const handleResendCode = async () => {
    setResendLoading(true)
    try {
      await resendVerificationCode(verifyEmail)
      message.success('验证码已重新发送')
    } catch (error) {
      message.error(error instanceof Error ? error.message : '发送失败')
    } finally {
      setResendLoading(false)
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
            创建账号
          </Title>
          <Text className="auth-subtitle">
            加入 E-Mobility 企业平台
          </Text>
        </div>

        {/* Register Form */}
        <Form
          name="register"
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
            rules={[
              { required: true, message: '请输入密码' },
              { min: 8, message: '密码至少8个字符' },
              {
                pattern: /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).+$/,
                message: '密码需包含大小写字母和数字'
              }
            ]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="设置密码"
            />
          </Form.Item>
          <Form.Item
            name="confirmPassword"
            dependencies={['password']}
            rules={[
              { required: true, message: '请确认密码' },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue('password') === value) {
                    return Promise.resolve()
                  }
                  return Promise.reject(new Error('两次输入的密码不一致'))
                }
              })
            ]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="确认密码"
            />
          </Form.Item>

          {/* Password Requirements Hint */}
          <div style={{
            background: '#f9fafb',
            borderRadius: 8,
            padding: '12px 16px',
            marginBottom: 20,
            border: '1px solid #e5e7eb'
          }}>
            <Text style={{ fontSize: 12, color: '#6b7280' }}>
              密码要求：至少8位，包含大写字母、小写字母和数字
            </Text>
          </div>

          <Form.Item style={{ marginBottom: 16 }}>
            <Button type="primary" htmlType="submit" loading={loading} block>
              注册
            </Button>
          </Form.Item>
        </Form>

        {/* Divider */}
        <div className="auth-divider">
          <span>已有账号？</span>
        </div>

        {/* Login Link */}
        <div style={{ textAlign: 'center' }}>
          <Link to="/login" className="auth-link" style={{ fontSize: 15 }}>
            立即登录
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
            注册即表示同意我们的服务条款和隐私政策
          </Text>
        </div>
      </div>

      {/* Email Verification Modal */}
      <Modal
        title="邮箱验证"
        open={verifyModalVisible}
        onOk={handleVerify}
        onCancel={() => setVerifyModalVisible(false)}
        confirmLoading={loading}
        okText="验证"
        cancelText="取消"
        centered
      >
        <div style={{ padding: '8px 0' }}>
          <Text style={{ color: '#6b7280', display: 'block', marginBottom: 16 }}>
            验证码已发送到 <strong style={{ color: '#111827' }}>{verifyEmail}</strong>，
            请输入验证码完成注册：
          </Text>
          <Input
            placeholder="请输入6位验证码"
            value={verifyCode}
            onChange={(e) => setVerifyCode(e.target.value)}
            maxLength={6}
            size="large"
            style={{ marginBottom: 12, borderRadius: 8 }}
          />
          <div style={{ textAlign: 'right' }}>
            <Button
              type="link"
              onClick={handleResendCode}
              loading={resendLoading}
              style={{ padding: 0, fontSize: 14 }}
            >
              重新发送验证码
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  )
}
