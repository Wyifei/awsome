import { useState, useEffect } from 'react'
import { Card, Form, Input, Button, Avatar, Upload, message, Tabs, Descriptions } from 'antd'
import { UserOutlined, UploadOutlined } from '@ant-design/icons'
import { useAuth } from '../hooks/useAuth'
import { userService } from '../services/userService'
import type { UserProfile } from '../types'

export default function ProfilePage() {
  const { user } = useAuth()
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [profile, setProfile] = useState<UserProfile | null>(null)

  useEffect(() => {
    loadProfile()
  }, [])

  const loadProfile = async () => {
    try {
      const response = await userService.getProfile()
      setProfile(response.data)
      form.setFieldsValue(response.data)
    } catch {
      // Profile may not exist yet
    }
  }

  const onFinish = async (values: Partial<UserProfile>) => {
    setLoading(true)
    try {
      await userService.updateProfile(values)
      message.success('资料更新成功')
      loadProfile()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '更新失败')
    } finally {
      setLoading(false)
    }
  }

  const tabItems = [
    {
      key: 'info',
      label: '基本信息',
      children: (
        <Descriptions column={1} bordered>
          <Descriptions.Item label="用户名">{user?.username}</Descriptions.Item>
          <Descriptions.Item label="邮箱">{user?.email}</Descriptions.Item>
          <Descriptions.Item label="邮箱验证">
            {user?.emailVerified ? '已验证' : '未验证'}
          </Descriptions.Item>
          <Descriptions.Item label="手机号">{user?.phoneNumber || '未绑定'}</Descriptions.Item>
        </Descriptions>
      )
    },
    {
      key: 'profile',
      label: '个人资料',
      children: (
        <Form
          form={form}
          layout="vertical"
          onFinish={onFinish}
          initialValues={profile || {}}
        >
          <div style={{ textAlign: 'center', marginBottom: 24 }}>
            <Avatar size={100} icon={<UserOutlined />} src={profile?.avatar} />
            <div style={{ marginTop: 8 }}>
              <Upload showUploadList={false}>
                <Button icon={<UploadOutlined />}>更换头像</Button>
              </Upload>
            </div>
          </div>
          <Form.Item name="nickname" label="昵称">
            <Input placeholder="请输入昵称" />
          </Form.Item>
          <Form.Item name="address" label="地址">
            <Input placeholder="请输入地址" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading}>
              保存修改
            </Button>
          </Form.Item>
        </Form>
      )
    }
  ]

  return (
    <Card title="个人中心">
      <Tabs items={tabItems} />
    </Card>
  )
}
