import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, Typography, Button, Input, Steps, Alert, Modal, message } from 'antd'
import { ExclamationCircleOutlined, MailOutlined, DeleteOutlined } from '@ant-design/icons'
import { useAuth } from '../contexts/AuthContext'
import { authService } from '../services/authService'

const { Title, Text, Paragraph } = Typography

export default function DeleteAccountPage() {
  const navigate = useNavigate()
  const { user, logout } = useAuth()
  const [currentStep, setCurrentStep] = useState(0)
  const [loading, setLoading] = useState(false)
  const [verificationCode, setVerificationCode] = useState('')
  const [_codeSent, setCodeSent] = useState(false)

  // Step 1: Send verification code
  const handleSendCode = async () => {
    if (!user?.email) {
      message.error('无法获取用户邮箱')
      return
    }

    setLoading(true)
    try {
      await authService.sendDeleteAccountCode(user.email)
      setCodeSent(true)
      message.success('验证码已发送到您的邮箱')
      setCurrentStep(1)
    } catch (error) {
      message.error(error instanceof Error ? error.message : '发送验证码失败')
    } finally {
      setLoading(false)
    }
  }

  // Step 2: Verify code and delete account
  const handleDeleteAccount = async () => {
    if (!verificationCode || verificationCode.length !== 6) {
      message.error('请输入6位验证码')
      return
    }

    Modal.confirm({
      title: '确认注销账号',
      icon: <ExclamationCircleOutlined />,
      content: (
        <div>
          <p>您确定要注销账号吗？此操作将：</p>
          <ul>
            <li>永久删除您的所有个人信息</li>
            <li>删除您的账号数据</li>
            <li>此操作不可撤销</li>
          </ul>
        </div>
      ),
      okText: '确认注销',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        setLoading(true)
        try {
          await authService.deleteAccount(user!.email, verificationCode)
          message.success('账号已注销')
          // Logout and redirect to login
          await logout()
          navigate('/login')
        } catch (error) {
          message.error(error instanceof Error ? error.message : '注销失败')
        } finally {
          setLoading(false)
        }
      }
    })
  }

  const steps = [
    {
      title: '发送验证码',
      description: '验证您的身份'
    },
    {
      title: '输入验证码',
      description: '确认注销操作'
    },
    {
      title: '完成注销',
      description: '账号已删除'
    }
  ]

  return (
    <Card>
      <Title level={4}>
        <DeleteOutlined style={{ marginRight: 8, color: '#ff4d4f' }} />
        注销账号
      </Title>

      <Alert
        message="警告"
        description="注销账号后，您的所有数据将被永久删除，无法恢复。请谨慎操作。"
        type="warning"
        showIcon
        style={{ marginBottom: 24 }}
      />

      <Steps current={currentStep} items={steps} style={{ marginBottom: 32 }} />

      {currentStep === 0 && (
        <div>
          <Paragraph>
            为了确认是您本人操作，我们需要向您的注册邮箱发送一个验证码：
          </Paragraph>
          <div style={{
            background: '#f5f5f5',
            padding: 16,
            borderRadius: 8,
            marginBottom: 24,
            display: 'flex',
            alignItems: 'center',
            gap: 8
          }}>
            <MailOutlined />
            <Text strong>{user?.email}</Text>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <Button onClick={() => navigate(-1)}>
              返回
            </Button>
            <Button
              type="primary"
              danger
              loading={loading}
              onClick={handleSendCode}
            >
              发送验证码
            </Button>
          </div>
        </div>
      )}

      {currentStep === 1 && (
        <div>
          <Paragraph>
            验证码已发送到 <Text strong>{user?.email}</Text>，请输入验证码完成注销：
          </Paragraph>
          <Input
            placeholder="请输入6位验证码"
            value={verificationCode}
            onChange={(e) => setVerificationCode(e.target.value)}
            maxLength={6}
            style={{ width: 200, marginBottom: 16 }}
            size="large"
          />
          <div style={{ marginBottom: 16 }}>
            <Button
              type="link"
              onClick={handleSendCode}
              loading={loading}
              style={{ padding: 0 }}
            >
              重新发送验证码
            </Button>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <Button onClick={() => navigate(-1)}>
              取消
            </Button>
            <Button
              type="primary"
              danger
              loading={loading}
              onClick={handleDeleteAccount}
            >
              确认注销账号
            </Button>
          </div>
        </div>
      )}
    </Card>
  )
}
