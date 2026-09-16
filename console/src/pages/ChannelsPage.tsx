import { EditOutlined, PlusOutlined } from "@ant-design/icons";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Empty, Form, Input, Modal, Popconfirm, Select, Space, Switch, Table, Tag, Typography, message } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useState } from "react";

import { ApiError, api } from "../api/client";
import type { NotificationChannelData } from "../api/types";

interface ChannelFormValues {
  name: string;
  regions: string[];
  webhook?: string;
  secret?: string;
  enabled: boolean;
}

type ChannelPayload = Pick<ChannelFormValues, "name" | "regions" | "enabled"> & Partial<Pick<ChannelFormValues, "webhook" | "secret">>;

const regionOptions = [
  { value: "ALL", label: "全部站点" },
  { value: "US", label: "美站" },
  { value: "DE", label: "德站" },
  { value: "HK", label: "港站" },
  { value: "SG", label: "新加坡站" },
  { value: "UK", label: "英站" },
];

function channelPayload(values: ChannelFormValues): ChannelPayload {
  const payload: ChannelPayload = {
    name: values.name.trim(),
    regions: values.regions,
    enabled: values.enabled,
  };
  if (values.webhook?.trim()) payload.webhook = values.webhook.trim();
  if (values.secret?.trim()) payload.secret = values.secret.trim();
  return payload;
}

function channelError(error: unknown): string {
  return error instanceof Error ? error.message : "保存失败，请稍后重试";
}

export function ChannelsPage() {
  const [form] = Form.useForm<ChannelFormValues>();
  const queryClient = useQueryClient();
  const [editingChannel, setEditingChannel] = useState<NotificationChannelData | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testingChannelId, setTestingChannelId] = useState<number | null>(null);
  const [messageApi, contextHolder] = message.useMessage();
  const channels = useQuery({
    queryKey: ["notification-channels"],
    queryFn: () => api.get<NotificationChannelData[]>("notification-channels"),
  });

  const closeModal = () => {
    if (saving) return;
    setModalOpen(false);
    setEditingChannel(null);
    form.resetFields();
  };

  const openCreate = () => {
    setEditingChannel(null);
    form.setFieldsValue({ name: "", regions: ["ALL"], webhook: "", secret: "", enabled: true });
    setModalOpen(true);
  };

  const openEdit = (channel: NotificationChannelData) => {
    setEditingChannel(channel);
    // API responses intentionally contain no credentials; blank fields preserve them on PATCH.
    form.setFieldsValue({ name: channel.name, regions: channel.regions, webhook: "", secret: "", enabled: channel.enabled });
    setModalOpen(true);
  };

  const submitChannel = async (values: ChannelFormValues) => {
    const payload = channelPayload(values);
    setSaving(true);
    try {
      if (editingChannel) {
        await api.patch<NotificationChannelData>(`notification-channels/${editingChannel.id}`, payload);
        messageApi.success("飞书群已更新");
      } else {
        await api.post<NotificationChannelData>("notification-channels", payload);
        messageApi.success("飞书群已添加");
      }
      await queryClient.invalidateQueries({ queryKey: ["notification-channels"] });
      setModalOpen(false);
      setEditingChannel(null);
      form.resetFields();
    } catch (error) {
      if (error instanceof ApiError && error.fields) {
        const formFields = new Set<keyof ChannelFormValues>(["name", "regions", "webhook", "secret", "enabled"]);
        form.setFields(Object.entries(error.fields).flatMap(([name, reason]) => formFields.has(name as keyof ChannelFormValues)
          ? [{ name: name as keyof ChannelFormValues, errors: [Array.isArray(reason) ? reason[0] : reason] }]
          : []));
      } else {
        messageApi.error(channelError(error));
      }
    } finally {
      setSaving(false);
    }
  };

  const testChannel = async (channel: NotificationChannelData) => {
    setTestingChannelId(channel.id);
    try {
      await api.post<{ sent: boolean }>(`notification-channels/${channel.id}/test`);
      messageApi.success("测试消息已发送");
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "测试消息发送失败，请稍后重试");
    } finally {
      setTestingChannelId(null);
    }
  };

  const columns: ColumnsType<NotificationChannelData> = [
    { title: "群名称", dataIndex: "name", width: 220, ellipsis: true },
    { title: "接收范围", key: "regions", width: 200, render: (_, channel) => channel.receive_scope_label ?? channel.regions.join("、") },
    {
      title: "Webhook",
      dataIndex: "webhook_mask",
      width: 240,
      ellipsis: true,
      render: (mask: string | null | undefined, channel) => mask ? (
        <Typography.Text ellipsis={{ tooltip: mask }}>{mask}</Typography.Text>
      ) : <Tag color={channel.webhook_configured ? "processing" : "default"}>{channel.webhook_configured ? "已配置" : "未配置"}</Tag>,
    },
    {
      title: "加签密钥",
      key: "secret",
      width: 120,
      render: (_, channel) => <Tag color={channel.secret_configured ? "processing" : "default"}>{channel.secret_configured ? "已配置" : "未配置"}</Tag>,
    },
    { title: "状态", key: "enabled", width: 96, render: (_, channel) => <Tag color={channel.enabled ? "success" : "default"}>{channel.enabled ? "已启用" : "已停用"}</Tag> },
    {
      title: "操作",
      key: "actions",
      width: 196,
      fixed: "right",
      render: (_, channel) => (
        <Space size={0}>
          <Button type="link" size="small" icon={<EditOutlined />} aria-label="编辑" onClick={() => openEdit(channel)}>编辑</Button>
          <Popconfirm
            title="确认发送测试消息？"
            description="将向该飞书群发送一条固定的测试消息。"
            okText="确定"
            cancelText="取消"
            okButtonProps={{ loading: testingChannelId === channel.id }}
            onConfirm={() => testChannel(channel)}
          >
            <Button type="link" size="small" loading={testingChannelId === channel.id} disabled={testingChannelId !== null && testingChannelId !== channel.id}>测试发送</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      {contextHolder}
      {channels.isError && <Alert type="error" showIcon message="飞书群列表加载失败，请稍后重试" style={{ marginBottom: 16 }} />}
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 16 }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>添加飞书群</Button>
      </div>
      <Table<NotificationChannelData>
        rowKey="id"
        columns={columns}
        dataSource={channels.data ?? []}
        loading={channels.isLoading || channels.isFetching}
        pagination={false}
        scroll={{ x: 1008 }}
        locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无飞书群配置" /> }}
      />
      <Modal
        title={editingChannel ? "编辑飞书群" : "添加飞书群"}
        open={modalOpen}
        onCancel={closeModal}
        onOk={() => form.submit()}
        okText="保存"
        cancelText="取消"
        okButtonProps={{ "aria-label": "保存" }}
        confirmLoading={saving}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" requiredMark={false} onFinish={submitChannel} initialValues={{ regions: ["ALL"], enabled: true }}>
          <Form.Item label="群名称" name="name" rules={[{ required: true, whitespace: true, message: "请输入群名称" }]}>
            <Input autoFocus maxLength={100} />
          </Form.Item>
          <Form.Item label="接收范围" name="regions" rules={[{ required: true, type: "array", min: 1, message: "请选择接收范围" }]}>
            <Select
              mode="multiple"
              options={regionOptions}
              maxTagCount="responsive"
              placeholder="选择需要接收补货通知的站点"
              onChange={(values: string[]) => {
                const normalized = values.at(-1) === "ALL" ? ["ALL"] : values.filter((value) => value !== "ALL");
                form.setFieldValue("regions", normalized);
              }}
            />
          </Form.Item>
          <Form.Item
            label="Webhook"
            name="webhook"
            extra={editingChannel?.webhook_configured ? "Webhook 已配置，留空将保留现有地址。" : undefined}
            rules={[{ required: !editingChannel, whitespace: true, message: "请输入 Webhook 地址" }]}
          >
            <Input autoComplete="off" inputMode="url" placeholder={editingChannel ? "留空保持不变" : "https://open.feishu.cn/open-apis/bot/v2/hook/..."} />
          </Form.Item>
          <Form.Item
            label="加签密钥"
            name="secret"
            extra={editingChannel?.secret_configured ? "加签密钥已配置，留空将保留现有密钥。" : undefined}
          >
            <Input.Password autoComplete="new-password" placeholder={editingChannel ? "留空保持不变" : "可选"} />
          </Form.Item>
          <Form.Item label="启用" name="enabled" valuePropName="checked">
            <Switch checkedChildren="启用" unCheckedChildren="停用" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
