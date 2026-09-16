import { useQuery } from "@tanstack/react-query";
import { Alert, Empty, Tag } from "antd";
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import { useMemo, useState } from "react";

import { api } from "../api/client";
import type { EventData, PaginatedData } from "../api/types";

interface EventQuery {
  page: number;
  pageSize: number;
}

function eventListPath(query: EventQuery): string {
  const params = new URLSearchParams({ page: String(query.page), page_size: String(query.pageSize) });
  return `events?${params.toString()}`;
}

function formatDate(value?: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "-"
    : new Intl.DateTimeFormat("zh-CN", { dateStyle: "short", timeStyle: "short", hour12: false }).format(date);
}

function notificationResult(event: EventData) {
  const notifications = event.notifications;
  if (!notifications?.total) return <Tag>未发送通知</Tag>;
  const label = `发送成功 ${notifications.success}/${notifications.total}`;
  return (
    <Tag color={notifications.failed ? "warning" : "success"}>
      {notifications.failed ? `${label}，失败 ${notifications.failed}` : label}
    </Tag>
  );
}

export function EventsPage() {
  const [query, setQuery] = useState<EventQuery>({ page: 1, pageSize: 20 });
  const events = useQuery({
    queryKey: ["events", query],
    queryFn: () => api.get<PaginatedData<EventData>>(eventListPath(query)),
  });
  const columns = useMemo<ProColumns<EventData>[]>(() => [
    { title: "商品", dataIndex: ["product", "name"], width: 250, ellipsis: true, search: false },
    { title: "商城", dataIndex: ["site", "name"], width: 160, ellipsis: true, search: false },
    { title: "规格", dataIndex: ["variant", "name"], width: 150, ellipsis: true, search: false },
    {
      title: "价格",
      key: "price",
      width: 120,
      search: false,
      render: (_, event) => event.price ? `${event.currency ?? ""} ${event.price}`.trim() : "-",
    },
    {
      title: "补货时间",
      key: "timestamp",
      width: 176,
      search: false,
      render: (_, event) => formatDate(event.timestamp ?? event.created_at),
    },
    {
      title: "通知结果",
      key: "notifications",
      width: 164,
      search: false,
      render: (_, event) => notificationResult(event),
    },
  ], []);

  return (
    <div>
      {events.isError && <Alert type="error" showIcon message="补货记录加载失败，请稍后重试" style={{ marginBottom: 16 }} />}
      <ProTable<EventData>
        rowKey="id"
        columns={columns}
        dataSource={events.data?.items ?? []}
        loading={events.isLoading || events.isFetching}
        search={false}
        options={false}
        pagination={{
          current: query.page,
          pageSize: query.pageSize,
          total: events.data?.total ?? 0,
          showSizeChanger: true,
          onChange: (page, pageSize) => setQuery({ page, pageSize }),
        }}
        scroll={{ x: 1020 }}
        locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无补货记录" /> }}
      />
    </div>
  );
}
