import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Form, Input, Button, Card, Typography, message, Modal } from 'antd'
import { LockOutlined, MailOutlined } from '@ant-design/icons'
import { useAuth } from '../hooks/useAuth'

const { Title, Text } = Typography

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
      // 注册时 username 参数已不使用，使用 email 作为用户名
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
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      justifyContent: 'center',
      alignItems: 'center',
      background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)'
    }}>
      <Card style={{ width: 400, borderRadius: 8 }}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <Title level={2} style={{ marginBottom: 8 }}>用户注册</Title>
          <Text type="secondary">创建您的账号</Text>
        </div>
        <Form
          name="register"
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
            rules={[
              { required: true, message: '请输入密码' },
              { min: 8, message: '密码至少8个字符' },
              {
                pattern: /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).+$/,
                message: '密码需包含大小写字母和数字'
              }
            ]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder="密码" />
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
            <Input.Password prefix={<LockOutlined />} placeholder="确认密码" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} block>
              注册
            </Button>
          </Form.Item>
        </Form>
        <div style={{ textAlign: 'center' }}>
          <Text>已有账号？</Text>
          <Link to="/login">立即登录</Link>
        </div>
      </Card>

      <Modal
        title="邮箱验证"
        open={verifyModalVisible}
        onOk={handleVerify}
        onCancel={() => setVerifyModalVisible(false)}
        confirmLoading={loading}
        okText="验证"
        cancelText="取消"
      >
        <p style={{ marginBottom: 16 }}>
          验证码已发送到 <strong>{verifyEmail}</strong>，请输入验证码完成注册：
        </p>
        <Input
          placeholder="请输入6位验证码"
          value={verifyCode}
          onChange={(e) => setVerifyCode(e.target.value)}
          maxLength={6}
          style={{ marginBottom: 12 }}
        />
        <div style={{ textAlign: 'right' }}>
          <Button
            type="link"
            onClick={handleResendCode}
            loading={resendLoading}
            style={{ padding: 0 }}
          >
            重新发送验证码
          </Button>
        </div>
      </Modal>
    </div>
  )
}
