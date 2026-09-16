import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Empty, Tag, message } from "antd";
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import { useEffect, useMemo, useState } from "react";

import { api } from "../api/client";
import type { FailureData, PaginatedData } from "../api/types";

interface FailureQuery {
  page: number;
  pageSize: number;
}

function failureListPath(query: FailureQuery): string {
  const params = new URLSearchParams({ active: "1", page: String(query.page), page_size: String(query.pageSize) });
  return `failures?${params.toString()}`;
}

function formatDate(value?: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "-"
    : new Intl.DateTimeFormat("zh-CN", { dateStyle: "short", timeStyle: "short", hour12: false }).format(date);
}

function failureKind(failure: FailureData) {
  return failure.kind === "notification"
    ? <Tag color="error">通知异常</Tag>
    : <Tag color="warning">抓取异常</Tag>;
}

export function FailuresPage() {
  const queryClient = useQueryClient();
  const [query, setQuery] = useState<FailureQuery>({ page: 1, pageSize: 20 });
  const [retryingFailure, setRetryingFailure] = useState<FailureData | null>(null);
  const [messageApi, contextHolder] = message.useMessage();
  const failures = useQuery({
    queryKey: ["failures", query],
    queryFn: () => api.get<PaginatedData<FailureData>>(failureListPath(query)),
    refetchInterval: retryingFailure !== null ? 2000 : false,
  });

  useEffect(() => {
    if (!retryingFailure || failures.isFetching || !failures.data) return;
    const current = failures.data.items.find(
      (failure) => failure.kind === "crawl" && failure.product.id === retryingFailure.product.id,
    );
    if (!current) {
      messageApi.success("重新检查成功，异常已恢复");
      setRetryingFailure(null);
    } else if (current.id !== retryingFailure.id) {
      messageApi.error("重新检查仍然失败，已保留最新异常");
      setRetryingFailure(null);
    }
  }, [failures.data, failures.isFetching, messageApi, retryingFailure]);

  const retryFailure = async (failure: FailureData) => {
    setRetryingFailure(failure);
    try {
      await api.post<{ queued: boolean }>(`failures/${failure.id}/retry`);
      await queryClient.invalidateQueries({ queryKey: ["failures"] });
      if (failure.kind === "notification") {
        messageApi.success("已提交重新发送");
        setRetryingFailure(null);
      } else {
        messageApi.info("正在重新检查商品");
      }
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "提交重试失败，请稍后重试");
      setRetryingFailure(null);
    }
  };

  const columns = useMemo<ProColumns<FailureData>[]>(() => [
    { title: "类型", key: "kind", width: 112, search: false, render: (_, failure) => failureKind(failure) },
    { title: "商品", dataIndex: ["product", "name"], width: 240, ellipsis: true, search: false },
    { title: "商城", dataIndex: ["site", "name"], width: 156, ellipsis: true, search: false },
    { title: "异常说明", dataIndex: "message", ellipsis: true, search: false },
    { title: "发生时间", dataIndex: "occurred_at", width: 176, search: false, render: (_, failure) => formatDate(failure.occurred_at) },
    {
      title: "操作",
      valueType: "option",
      width: 116,
      fixed: "right",
      render: (_, failure) => (
        <Button
          type="link"
          size="small"
          loading={retryingFailure?.id === failure.id}
          disabled={retryingFailure !== null && retryingFailure.id !== failure.id}
          onClick={() => void retryFailure(failure)}
        >
          {failure.kind === "notification" ? "重新发送" : "重新检查"}
        </Button>
      ),
    },
  ], [retryingFailure]);

  return (
    <div>
      {contextHolder}
      {failures.isError && <Alert type="error" showIcon message="异常记录加载失败，请稍后重试" style={{ marginBottom: 16 }} />}
      <ProTable<FailureData>
        rowKey="id"
        columns={columns}
        dataSource={failures.data?.items ?? []}
        loading={failures.isLoading || failures.isFetching}
        search={false}
        options={false}
        pagination={{
          current: query.page,
          pageSize: query.pageSize,
          total: failures.data?.total ?? 0,
          showSizeChanger: true,
          onChange: (page, pageSize) => setQuery({ page, pageSize }),
        }}
        scroll={{ x: 1040 }}
        locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无异常记录" /> }}
      />
    </div>
  );
}
