import { Card, Row, Col, Statistic, Typography } from 'antd'
import { UserOutlined, SafetyOutlined, ClockCircleOutlined } from '@ant-design/icons'
import { useAuth } from '../hooks/useAuth'

const { Title } = Typography

export default function DashboardPage() {
  const { user } = useAuth()

  return (
    <div>
      <Title level={4} style={{ marginBottom: 24 }}>
        欢迎回来，{user?.username || user?.email}
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
      <Card style={{ marginTop: 24 }}>
        <Title level={5}>快速入口</Title>
        <p>您可以在左侧菜单中访问个人资料设置。</p>
      </Card>
    </div>
  )
}
