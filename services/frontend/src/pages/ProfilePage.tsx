import { useState, useEffect } from 'react'
import { Card, Form, Input, Button, Avatar, Upload, message, Tabs, Descriptions, Select, DatePicker } from 'antd'
import { UserOutlined, UploadOutlined } from '@ant-design/icons'
import { useAuth } from '../contexts/AuthContext'
import { profileService } from '../services/profileService'
import type { UserProfile } from '../types'
import type { UploadProps } from 'antd/es/upload/interface'
import dayjs from 'dayjs'

export default function ProfilePage() {
  const { user } = useAuth()
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [profile, setProfile] = useState<UserProfile | null>(null)

  useEffect(() => {
    loadProfile()
  }, [])

  const loadProfile = async () => {
    try {
      const response = await profileService.getProfile()
      setProfile(response.data)
      form.setFieldsValue({
        ...response.data,
        birthday: response.data.birthday ? dayjs(response.data.birthday) : undefined
      })
    } catch {
      // Profile may not exist yet
    }
  }

  const onFinish = async (values: Record<string, unknown>) => {
    setLoading(true)
    try {
      const genderValue = values.gender as string | undefined
      const updateData = {
        nickname: values.nickname as string | undefined,
        gender: genderValue?.toLowerCase() as 'male' | 'female' | 'other' | undefined,
        birthday: values.birthday ? (values.birthday as dayjs.Dayjs).format('YYYY-MM-DD') : undefined,
        address: values.address as string | undefined
      }
      await profileService.updateProfile(updateData)
      message.success('资料更新成功')
      loadProfile()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '更新失败')
    } finally {
      setLoading(false)
    }
  }

  const handleAvatarUpload: UploadProps['customRequest'] = async (options) => {
    const { file, onSuccess, onError } = options
    setUploading(true)
    try {
      const result = await profileService.uploadAvatar(file as File)
      message.success('头像上传成功')
      setProfile(prev => prev ? { ...prev, avatar: result.avatarUrl } : null)
      onSuccess?.(result)
    } catch (error) {
      message.error(error instanceof Error ? error.message : '上传失败')
      onError?.(error as Error)
    } finally {
      setUploading(false)
    }
  }

  const handleAvatarDelete = async () => {
    try {
      await profileService.deleteAvatar()
      message.success('头像已删除')
      setProfile(prev => prev ? { ...prev, avatar: undefined } : null)
    } catch (error) {
      message.error(error instanceof Error ? error.message : '删除失败')
    }
  }

  const formatGender = (gender: string | undefined) => {
    switch (gender?.toUpperCase()) {
      case 'MALE': return '男'
      case 'FEMALE': return '女'
      case 'OTHER': return '其他'
      default: return '未设置'
    }
  }

  const tabItems = [
    {
      key: 'info',
      label: '基本信息',
      children: (
        <Descriptions column={1} bordered>
          <Descriptions.Item label="显示名称">{profile?.nickname || user?.email}</Descriptions.Item>
          <Descriptions.Item label="邮箱">{user?.email}</Descriptions.Item>
          <Descriptions.Item label="邮箱验证">
            {user?.emailVerified ? '已验证' : '未验证'}
          </Descriptions.Item>
          <Descriptions.Item label="手机号">{user?.phoneNumber || '未绑定'}</Descriptions.Item>
          <Descriptions.Item label="账号状态">{user?.status || '-'}</Descriptions.Item>
          <Descriptions.Item label="昵称">{profile?.nickname || '未设置'}</Descriptions.Item>
          <Descriptions.Item label="性别">{formatGender(profile?.gender)}</Descriptions.Item>
          <Descriptions.Item label="生日">{profile?.birthday || '未设置'}</Descriptions.Item>
          <Descriptions.Item label="地址">{profile?.address || '未设置'}</Descriptions.Item>
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
            <div style={{ marginTop: 8, display: 'flex', justifyContent: 'center', gap: 8 }}>
              <Upload
                showUploadList={false}
                customRequest={handleAvatarUpload}
                accept="image/jpeg,image/png,image/gif,image/webp"
                maxCount={1}
              >
                <Button icon={<UploadOutlined />} loading={uploading}>
                  更换头像
                </Button>
              </Upload>
              {profile?.avatar && (
                <Button danger onClick={handleAvatarDelete}>
                  删除头像
                </Button>
              )}
            </div>
          </div>
          <Form.Item name="nickname" label="昵称">
            <Input placeholder="请输入昵称" maxLength={64} />
          </Form.Item>
          <Form.Item name="gender" label="性别">
            <Select placeholder="请选择性别" allowClear>
              <Select.Option value="MALE">男</Select.Option>
              <Select.Option value="FEMALE">女</Select.Option>
              <Select.Option value="OTHER">其他</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item name="birthday" label="生日">
            <DatePicker style={{ width: '100%' }} placeholder="请选择生日" />
          </Form.Item>
          <Form.Item name="address" label="地址">
            <Input placeholder="请输入地址" maxLength={256} />
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
