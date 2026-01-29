import { useState, useEffect } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { Layout, Menu, Avatar, Dropdown, Space } from 'antd'
import {
  DashboardOutlined,
  UserOutlined,
  LogoutOutlined,
  DeleteOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined
} from '@ant-design/icons'
import { useAuth } from '../contexts/AuthContext'
import { profileService } from '../services/profileService'
import type { UserProfile } from '../types'

const { Header, Sider, Content } = Layout

// Electric Bolt SVG Icon for brand identity
const ElectricBoltIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style={{ width: 20, height: 20 }}>
    <path
      d="M13 2L3 14H12L11 22L21 10H12L13 2Z"
      fill="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
)

export default function MainLayout() {
  const [collapsed, setCollapsed] = useState(false)
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const navigate = useNavigate()
  const location = useLocation()
  const { user, logout } = useAuth()

  useEffect(() => {
    const loadProfile = async () => {
      try {
        const response = await profileService.getProfile()
        setProfile(response.data)
      } catch {
        // Profile may not exist yet
      }
    }
    loadProfile()
  }, [])

  const menuItems = [
    {
      key: '/dashboard',
      icon: <DashboardOutlined />,
      label: '仪表盘'
    },
    {
      key: '/profile',
      icon: <UserOutlined />,
      label: '个人资料'
    }
  ]

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  const userMenuItems = [
    {
      key: 'profile',
      icon: <UserOutlined />,
      label: '个人资料',
      onClick: () => navigate('/profile')
    },
    {
      key: 'delete-account',
      icon: <DeleteOutlined />,
      label: '注销账号',
      onClick: () => navigate('/delete-account'),
      danger: true
    },
    {
      type: 'divider' as const
    },
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: '退出登录',
      onClick: handleLogout,
      danger: true
    }
  ]

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        trigger={null}
        collapsible
        collapsed={collapsed}
        className="main-layout-sider"
        style={{
          background: 'linear-gradient(180deg, #0a1628 0%, #0f2744 100%)',
          borderRight: '1px solid rgba(6, 182, 212, 0.1)'
        }}
      >
        {/* Brand Header */}
        <div className="brand-header">
          <div className="brand-header-logo" style={{
            width: 36,
            height: 36,
            background: 'linear-gradient(135deg, #06b6d4 0%, #2563eb 100%)',
            borderRadius: 8,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            marginRight: collapsed ? 0 : 12,
            boxShadow: '0 0 20px rgba(6, 182, 212, 0.3)',
            color: 'white',
            flexShrink: 0
          }}>
            <ElectricBoltIcon />
          </div>
          {!collapsed && (
            <span style={{
              color: 'white',
              fontSize: 16,
              fontWeight: 600,
              letterSpacing: '-0.3px',
              whiteSpace: 'nowrap'
            }}>
              E-Mobility
            </span>
          )}
        </div>

        {/* Navigation Menu */}
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
          style={{
            background: 'transparent',
            borderRight: 'none',
            marginTop: 8
          }}
        />
      </Sider>

      <Layout>
        {/* Top Header */}
        <Header
          className="main-header"
          style={{
            padding: '0 24px',
            background: '#fff',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            borderBottom: '1px solid #e5e7eb',
            boxShadow: '0 1px 2px 0 rgba(0, 0, 0, 0.03)'
          }}
        >
          {/* Collapse Toggle */}
          <div
            onClick={() => setCollapsed(!collapsed)}
            style={{
              width: 40,
              height: 40,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              borderRadius: 8,
              cursor: 'pointer',
              transition: 'all 0.2s ease',
              color: '#6b7280'
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = '#f3f4f6'
              e.currentTarget.style.color = '#111827'
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'transparent'
              e.currentTarget.style.color = '#6b7280'
            }}
          >
            {collapsed ? (
              <MenuUnfoldOutlined style={{ fontSize: 18 }} />
            ) : (
              <MenuFoldOutlined style={{ fontSize: 18 }} />
            )}
          </div>

          {/* User Dropdown */}
          <Dropdown
            menu={{ items: userMenuItems }}
            placement="bottomRight"
            trigger={['click']}
          >
            <Space
              style={{
                cursor: 'pointer',
                padding: '6px 12px',
                borderRadius: 8,
                transition: 'all 0.2s ease'
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = '#f3f4f6'
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = 'transparent'
              }}
            >
              <Avatar
                icon={<UserOutlined />}
                src={profile?.avatar}
                style={{
                  background: profile?.avatar ? 'transparent' : 'linear-gradient(135deg, #06b6d4 0%, #2563eb 100%)',
                  boxShadow: '0 2px 8px rgba(6, 182, 212, 0.2)'
                }}
              />
              <span style={{ color: '#374151', fontWeight: 500 }}>
                {profile?.nickname || user?.email?.split('@')[0]}
              </span>
            </Space>
          </Dropdown>
        </Header>

        {/* Main Content Area */}
        <Content
          className="main-content"
          style={{
            margin: 24,
            padding: 24,
            background: '#fff',
            borderRadius: 16,
            boxShadow: '0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.06)',
            minHeight: 280
          }}
        >
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
