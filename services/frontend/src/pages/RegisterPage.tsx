import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Form, Input, Button, Card, Typography, message, Modal } from 'antd'
import { UserOutlined, LockOutlined, MailOutlined } from '@ant-design/icons'
import { useAuth } from '../hooks/useAuth'

const { Title, Text } = Typography

interface RegisterForm {
  username: string
  email: string
  password: string
  confirmPassword: string
}

export default function RegisterPage() {
  const [loading, setLoading] = useState(false)
  const [verifyModalVisible, setVerifyModalVisible] = useState(false)
  const [verifyUsername, setVerifyUsername] = useState('')
  const [verifyCode, setVerifyCode] = useState('')
  const { register, confirmRegistration } = useAuth()
  const navigate = useNavigate()

  const onFinish = async (values: RegisterForm) => {
    setLoading(true)
    try {
      await register(values.username, values.email, values.password)
      setVerifyUsername(values.username)
      setVerifyModalVisible(true)
      message.success('注册成功，请查收验证码')
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
      await confirmRegistration(verifyUsername, verifyCode)
      message.success('验证成功，请登录')
      setVerifyModalVisible(false)
      navigate('/login')
    } catch (error) {
      message.error(error instanceof Error ? error.message : '验证失败')
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
            name="username"
            rules={[
              { required: true, message: '请输入用户名' },
              { min: 3, message: '用户名至少3个字符' }
            ]}
          >
            <Input prefix={<UserOutlined />} placeholder="用户名" />
          </Form.Item>
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
              { min: 8, message: '密码至少8个字符' }
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
          验证码已发送到您的邮箱，请输入验证码完成注册：
        </p>
        <Input
          placeholder="请输入验证码"
          value={verifyCode}
          onChange={(e) => setVerifyCode(e.target.value)}
        />
      </Modal>
    </div>
  )
}
