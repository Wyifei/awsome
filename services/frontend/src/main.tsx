import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { ConfigProvider, theme } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { Amplify } from 'aws-amplify'
import { AuthProvider } from './contexts/AuthContext'
import App from './App'
import './index.css'

// Configure Amplify
Amplify.configure({
  Auth: {
    Cognito: {
      userPoolId: import.meta.env.VITE_COGNITO_USER_POOL_ID,
      userPoolClientId: import.meta.env.VITE_COGNITO_CLIENT_ID,
      loginWith: {
        oauth: {
          domain: import.meta.env.VITE_COGNITO_DOMAIN,
          scopes: ['openid', 'email', 'profile'],
          redirectSignIn: [window.location.origin],
          redirectSignOut: [window.location.origin],
          responseType: 'code'
        }
      }
    }
  }
})

// Custom Ant Design theme for E-Mobility brand
const customTheme = {
  algorithm: theme.defaultAlgorithm,
  token: {
    // Primary brand colors
    colorPrimary: '#06b6d4',
    colorLink: '#2563eb',
    colorLinkHover: '#06b6d4',
    colorSuccess: '#10b981',
    colorWarning: '#f59e0b',
    colorError: '#ef4444',

    // Border radius
    borderRadius: 8,
    borderRadiusLG: 12,
    borderRadiusSM: 6,

    // Typography
    fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif",
    fontSize: 14,
    fontSizeHeading1: 32,
    fontSizeHeading2: 24,
    fontSizeHeading3: 20,

    // Shadows
    boxShadow: '0 1px 2px 0 rgba(0, 0, 0, 0.05)',
    boxShadowSecondary: '0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)',

    // Colors
    colorBgContainer: '#ffffff',
    colorBgLayout: '#f3f4f6',
    colorBorder: '#e5e7eb',
    colorBorderSecondary: '#f3f4f6',
    colorText: '#111827',
    colorTextSecondary: '#6b7280',
    colorTextTertiary: '#9ca3af',
  },
  components: {
    Button: {
      primaryShadow: '0 4px 14px rgba(6, 182, 212, 0.3)',
      defaultBorderColor: '#e5e7eb',
      fontWeight: 500,
    },
    Input: {
      activeBorderColor: '#06b6d4',
      hoverBorderColor: '#22d3ee',
      activeShadow: '0 0 0 4px rgba(6, 182, 212, 0.1)',
    },
    Card: {
      borderRadiusLG: 16,
    },
    Menu: {
      darkItemBg: 'transparent',
      darkItemSelectedBg: 'rgba(6, 182, 212, 0.2)',
      darkItemHoverBg: 'rgba(6, 182, 212, 0.1)',
      darkItemSelectedColor: '#22d3ee',
    },
    Layout: {
      siderBg: '#0a1628',
      headerBg: '#ffffff',
    },
    Modal: {
      borderRadiusLG: 16,
    },
    Message: {
      contentBg: '#ffffff',
    },
  },
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ConfigProvider locale={zhCN} theme={customTheme}>
      <BrowserRouter>
        <AuthProvider>
          <App />
        </AuthProvider>
      </BrowserRouter>
    </ConfigProvider>
  </React.StrictMode>
)
