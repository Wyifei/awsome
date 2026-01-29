import { useState, useEffect } from 'react'
import { Card, Row, Col, Statistic, Typography, Table, Collapse } from 'antd'
import { UserOutlined, SafetyOutlined, ClockCircleOutlined, KeyOutlined } from '@ant-design/icons'
import { useAuth } from '../contexts/AuthContext'
import { fetchAuthSession } from 'aws-amplify/auth'
import { profileService } from '../services/profileService'
import type { UserProfile } from '../types'

const { Title, Text } = Typography

interface TokenInfo {
  accessToken: string | null
  idToken: string | null
  refreshToken: string | null
  accessTokenPayload: Record<string, unknown> | null
  idTokenPayload: Record<string, unknown> | null
}

export default function DashboardPage() {
  const { user } = useAuth()
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [tokenInfo, setTokenInfo] = useState<TokenInfo>({
    accessToken: null,
    idToken: null,
    refreshToken: null,
    accessTokenPayload: null,
    idTokenPayload: null
  })

  useEffect(() => {
    const loadData = async () => {
      // 加载 profile
      try {
        const response = await profileService.getProfile()
        setProfile(response.data)
      } catch {
        // Profile may not exist yet
      }

      // 加载 tokens
      try {
        const session = await fetchAuthSession()
        setTokenInfo({
          accessToken: session.tokens?.accessToken?.toString() || null,
          idToken: session.tokens?.idToken?.toString() || null,
          refreshToken: (session as { tokens?: { refreshToken?: { toString: () => string } } }).tokens?.refreshToken?.toString() || null,
          accessTokenPayload: session.tokens?.accessToken?.payload as Record<string, unknown> || null,
          idTokenPayload: session.tokens?.idToken?.payload as Record<string, unknown> || null
        })
      } catch (error) {
        console.error('Failed to fetch tokens:', error)
      }
    }
    loadData()
  }, [])

  const payloadColumns = [
    { title: '字段', dataIndex: 'key', key: 'key', width: 200 },
    { title: '值', dataIndex: 'value', key: 'value', render: (val: unknown) => (
      <Text style={{ wordBreak: 'break-all' }}>{String(val)}</Text>
    )}
  ]

  const convertPayloadToTable = (payload: Record<string, unknown> | null) => {
    if (!payload) return []
    return Object.entries(payload).map(([key, value]) => ({
      key,
      value: typeof value === 'object' ? JSON.stringify(value) : value
    }))
  }

  const collapseItems = [
    {
      key: 'accessToken',
      label: (
        <span>
          <KeyOutlined style={{ marginRight: 8 }} />
          Access Token
        </span>
      ),
      children: (
        <div>
          <Card size="small" title="Token 字符串" style={{ marginBottom: 16 }}>
            <Text copyable style={{ wordBreak: 'break-all', fontSize: 12 }}>
              {tokenInfo.accessToken || '未获取'}
            </Text>
          </Card>
          <Card size="small" title="Token Payload (解码后)">
            <Table
              dataSource={convertPayloadToTable(tokenInfo.accessTokenPayload)}
              columns={payloadColumns}
              pagination={false}
              size="small"
              rowKey="key"
            />
          </Card>
        </div>
      )
    },
    {
      key: 'idToken',
      label: (
        <span>
          <KeyOutlined style={{ marginRight: 8 }} />
          ID Token
        </span>
      ),
      children: (
        <div>
          <Card size="small" title="Token 字符串" style={{ marginBottom: 16 }}>
            <Text copyable style={{ wordBreak: 'break-all', fontSize: 12 }}>
              {tokenInfo.idToken || '未获取'}
            </Text>
          </Card>
          <Card size="small" title="Token Payload (解码后)">
            <Table
              dataSource={convertPayloadToTable(tokenInfo.idTokenPayload)}
              columns={payloadColumns}
              pagination={false}
              size="small"
              rowKey="key"
            />
          </Card>
        </div>
      )
    },
    {
      key: 'refreshToken',
      label: (
        <span>
          <KeyOutlined style={{ marginRight: 8 }} />
          Refresh Token
        </span>
      ),
      children: (
        <Card size="small" title="Token 字符串">
          <Text copyable style={{ wordBreak: 'break-all', fontSize: 12 }}>
            {tokenInfo.refreshToken || '未获取 (Amplify 默认不暴露 refresh token)'}
          </Text>
        </Card>
      )
    }
  ]

  return (
    <div>
      <Title level={4} style={{ marginBottom: 24 }}>
        欢迎回来，{profile?.nickname || user?.email}
      </Title>
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={8}>
          <Card>
            <Statistic
              title="账号状态"
              value="已认证"
              prefix={<SafetyOutlined style={{ color: '#52c41a' }} />}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={8}>
          <Card>
            <Statistic
              title="邮箱验证"
              value={user?.emailVerified ? '已验证' : '未验证'}
              prefix={<UserOutlined />}
              valueStyle={{ color: user?.emailVerified ? '#52c41a' : '#faad14' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={8}>
          <Card>
            <Statistic
              title="上次登录"
              value="刚刚"
              prefix={<ClockCircleOutlined />}
            />
          </Card>
        </Col>
      </Row>

      <Card style={{ marginTop: 24 }} title="认证 Token 信息">
        <Collapse items={collapseItems} />
      </Card>

      <Card style={{ marginTop: 24 }}>
        <Title level={5}>快速入口</Title>
        <p>您可以在左侧菜单中访问个人资料设置。</p>
      </Card>
    </div>
  )
}
