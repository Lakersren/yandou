import { PauseCircleOutlined, PlayCircleOutlined, ReloadOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Descriptions, Drawer, Space, Spin, Table, Tag, Typography, message } from "antd";
import type { ColumnsType } from "antd/es/table";

import { api } from "../api/client";
import type { ProductData, VariantData } from "../api/types";

interface ProductDrawerProps {
  productId: number | null;
  onClose: () => void;
}

const statusConfig: Record<string, { color: string; label: string }> = {
  in_stock: { color: "success", label: "有货" },
  partial_stock: { color: "warning", label: "部分有货" },
  out_of_stock: { color: "default", label: "缺货" },
  discontinued: { color: "default", label: "已下架" },
  unknown: { color: "warning", label: "确认中" },
};

function StatusTag({ status, label }: { status: string; label?: string }) {
  const config = statusConfig[status] ?? statusConfig.unknown;
  return <Tag color={config.color}>{label || config.label}</Tag>;
}

function formatDate(value?: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "-"
    : new Intl.DateTimeFormat("zh-CN", { dateStyle: "short", timeStyle: "short", hour12: false }).format(date);
}

const variantColumns: ColumnsType<VariantData> = [
  { title: "规格", dataIndex: "name", ellipsis: true },
  { title: "价格", width: 130, render: (_, variant) => variant.price ? `${variant.currency} ${variant.price}` : "-" },
  { title: "库存", dataIndex: "status", width: 96, render: (status: string) => <StatusTag status={status} /> },
];

interface SnapshotRow {
  key: string;
  checkedAt: string;
  variantName: string;
  status: string;
  price: string;
}

function safeText(value: unknown, fallback = "-"): string {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

function recentSnapshotRows(snapshots: ProductData["snapshots"]): SnapshotRow[] {
  return (snapshots ?? []).slice(0, 20).map((snapshot, index) => {
    const price = safeText(snapshot.price);
    const currency = safeText(snapshot.currency, "");
    return {
      key: `${safeText(snapshot.checked_at, "unknown")}-${safeText(snapshot.variant_name)}-${index}`,
      checkedAt: formatDate(snapshot.checked_at),
      variantName: safeText(snapshot.variant_name),
      status: safeText(snapshot.observed_status, "unknown"),
      price: price === "-" ? price : [currency, price].filter(Boolean).join(" "),
    };
  });
}

const snapshotColumns: ColumnsType<SnapshotRow> = [
  { title: "检查时间", dataIndex: "checkedAt", width: 150 },
  { title: "规格", dataIndex: "variantName", ellipsis: true },
  { title: "库存", dataIndex: "status", width: 96, render: (status: string) => <StatusTag status={status} /> },
  { title: "价格", dataIndex: "price", width: 130, ellipsis: true },
];

export function ProductDrawer({ productId, onClose }: ProductDrawerProps) {
  const queryClient = useQueryClient();
  const [messageApi, contextHolder] = message.useMessage();
  const product = useQuery({
    queryKey: ["product", productId],
    queryFn: () => api.get<ProductData>(`products/${productId}`),
    enabled: productId !== null,
  });
  const check = useMutation({ mutationFn: (id: number) => api.post<{ queued: boolean }>(`products/${id}/check`) });
  const updateEnabled = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) => api.patch<ProductData>(`products/${id}`, { enabled }),
  });

  const refreshProducts = () => {
    void queryClient.invalidateQueries({ queryKey: ["products"] });
    void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    void queryClient.invalidateQueries({ queryKey: ["product", productId] });
  };

  const submitCheck = async () => {
    if (productId === null) return;
    try {
      await check.mutateAsync(productId);
      messageApi.success("已提交立即检查");
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "提交检查失败，请稍后重试");
    }
  };

  const toggleEnabled = async () => {
    if (!product.data) return;
    try {
      await updateEnabled.mutateAsync({ id: product.data.id, enabled: !product.data.enabled });
      refreshProducts();
      messageApi.success(product.data.enabled ? "已暂停监控" : "已恢复监控");
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "更新监控状态失败，请稍后重试");
    }
  };

  const data = product.data;
  const snapshots = recentSnapshotRows(data?.snapshots);
  return (
    <Drawer title="商品详情" open={productId !== null} onClose={onClose} width="min(560px, 100vw)" destroyOnHidden>
      {contextHolder}
      {product.isLoading && <div style={{ padding: "36px 0", textAlign: "center" }}><Spin aria-label="正在加载商品详情" /></div>}
      {product.isError && <Alert type="error" showIcon message="商品详情加载失败，请稍后重试" />}
      {data && (
        <Space direction="vertical" size="large" style={{ display: "flex" }}>
          <Space wrap>
            <Button icon={<ReloadOutlined />} loading={check.isPending} onClick={submitCheck}>立即检查</Button>
            <Button
              icon={data.enabled ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
              loading={updateEnabled.isPending}
              onClick={toggleEnabled}
            >
              {data.enabled ? "暂停监控" : "恢复监控"}
            </Button>
          </Space>
          <Descriptions column={1} size="small" bordered>
            <Descriptions.Item label="商品链接">
              <Typography.Text ellipsis={{ tooltip: data.url }} style={{ display: "block" }}>
                <Typography.Link href={data.url} target="_blank" rel="noreferrer">{data.url}</Typography.Link>
              </Typography.Text>
            </Descriptions.Item>
            <Descriptions.Item label="商城">{data.site.name}</Descriptions.Item>
            <Descriptions.Item label="当前状态"><StatusTag status={data.stock_status} label={data.stock_status_label} /></Descriptions.Item>
            <Descriptions.Item label="最近检查">{formatDate(data.last_checked_at)}</Descriptions.Item>
            <Descriptions.Item label="最近可读错误">{data.last_error ? "最近检查未成功，请稍后重试" : "-"}</Descriptions.Item>
          </Descriptions>
          <div>
            <Typography.Title level={5}>规格</Typography.Title>
            <Table<VariantData>
              columns={variantColumns}
              dataSource={data.variants}
              rowKey="id"
              pagination={false}
              size="small"
            />
          </div>
          <div>
            <Typography.Title level={5}>最近观察</Typography.Title>
            <Table<SnapshotRow>
              columns={snapshotColumns}
              dataSource={snapshots}
              rowKey="key"
              pagination={false}
              size="small"
            />
          </div>
        </Space>
      )}
    </Drawer>
  );
}
