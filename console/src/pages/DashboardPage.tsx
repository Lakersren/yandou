import { ReloadOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Alert, Button, Card, Col, Empty, Row, Spin, Table, Tag, Typography, message } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect, useMemo, useState } from "react";

import { api } from "../api/client";
import type { DashboardData, FailureData, ProductSummary, RegionDashboardData } from "../api/types";
import "./dashboard.css";

const { Text, Title } = Typography;

export const stockTag = {
  in_stock: { color: "success", label: "有货" },
  partial_stock: { color: "warning", label: "部分有货" },
  out_of_stock: { color: "default", label: "缺货" },
  discontinued: { color: "default", label: "已下架" },
  unknown: { color: "warning", label: "确认中" },
} as const;

function formatDate(value?: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "-"
    : new Intl.DateTimeFormat("zh-CN", { dateStyle: "short", timeStyle: "short", hour12: false }).format(date);
}

function ProductStatus({ status, label }: { status: string; label?: string }) {
  const config = stockTag[status as keyof typeof stockTag] ?? stockTag.unknown;
  return <Tag color={config.color}>{label || config.label}</Tag>;
}

const productColumns: ColumnsType<ProductSummary> = [
  {
    title: "商品",
    dataIndex: "name",
    ellipsis: true,
    render: (name: string, product) => (
      <div className="dashboard-product-name">
        <Typography.Link href={product.url} target="_blank" rel="noreferrer" strong ellipsis title={name}>
          {name}
        </Typography.Link>
        <Text className="dashboard-product-site" type="secondary">{product.site.name}</Text>
      </div>
    ),
  },
  {
    title: "库存",
    dataIndex: "stock_status",
    width: 124,
    render: (status: string, product) => <ProductStatus status={status} label={product.stock_status_label} />,
  },
  { title: "最近检查", dataIndex: "last_checked_at", width: 168, responsive: ["md"], render: formatDate },
];

function RegionCard({ summary, selected, onSelect }: {
  summary: RegionDashboardData;
  selected: boolean;
  onSelect: () => void;
}) {
  const status = summary.monitored_products === 0
    ? { color: "default", text: "暂无商品" }
    : summary.active_failures > 0
      ? { color: "warning", text: "需要关注" }
      : { color: "success", text: "运行正常" };

  return (
    <Card
      className={`dashboard-region${selected ? " dashboard-region--selected" : ""}`}
      size="small"
      hoverable
      role="button"
      tabIndex={0}
      aria-pressed={selected}
      onClick={onSelect}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelect();
        }
      }}
    >
      <div className="dashboard-region__header">
        <Text strong>{summary.label}</Text>
        <Tag color={status.color}>{status.text}</Tag>
      </div>
      <div className="dashboard-region__metrics">
        <div><strong>{summary.monitored_products}</strong><span>监控商品</span></div>
        <div><strong>{summary.in_stock_variants}</strong><span>有货规格</span></div>
        <div><strong>{summary.restocks_24h}</strong><span>24h 补货</span></div>
        <div><strong>{summary.active_failures}</strong><span>当前异常</span></div>
      </div>
      <Text className="dashboard-region__checked" type="secondary">最近检查 {formatDate(summary.last_checked_at)}</Text>
    </Card>
  );
}

export function DashboardPage() {
  const [selectedRegion, setSelectedRegion] = useState("ALL");
  const [retryingFailure, setRetryingFailure] = useState<FailureData | null>(null);
  const [messageApi, contextHolder] = message.useMessage();
  const dashboard = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api.get<DashboardData>("dashboard"),
    refetchInterval: retryingFailure ? 2000 : false,
  });

  useEffect(() => {
    if (!retryingFailure || dashboard.isFetching || !dashboard.data) return;
    const current = dashboard.data.pending_failures.find(
      (failure) => failure.kind === "crawl" && failure.product.id === retryingFailure.product.id,
    );
    if (!current) {
      messageApi.success("重新检查成功，异常已恢复");
      setRetryingFailure(null);
    } else if (current.id !== retryingFailure.id) {
      messageApi.error("重新检查仍然失败，已保留最新异常");
      setRetryingFailure(null);
    }
  }, [dashboard.data, dashboard.isFetching, messageApi, retryingFailure]);

  const retryFailure = async (failure: FailureData) => {
    setRetryingFailure(failure);
    try {
      await api.post<{ queued: boolean }>(`failures/${failure.id}/retry`);
      messageApi.info("正在重新检查商品");
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "提交重试失败，请稍后重试");
      setRetryingFailure(null);
    }
  };

  const failureColumns = useMemo<ColumnsType<FailureData>>(() => [
    {
      title: "商品",
      dataIndex: ["product", "name"],
      ellipsis: true,
      render: (name: string, failure) => (
        <div className="dashboard-product-name">
          <Text ellipsis={{ tooltip: name }}>{name}</Text>
          <Text type="secondary">{failure.product.site_name}</Text>
        </div>
      ),
    },
    { title: "原因", dataIndex: "message", ellipsis: true, responsive: ["sm"] },
    { title: "时间", dataIndex: "occurred_at", width: 150, render: formatDate },
    {
      title: "操作",
      width: 116,
      render: (_, failure) => failure.kind === "crawl" ? (
        <Button
          type="link"
          size="small"
          icon={<ReloadOutlined />}
          loading={retryingFailure?.product.id === failure.product.id}
          disabled={retryingFailure !== null && retryingFailure.product.id !== failure.product.id}
          onClick={() => void retryFailure(failure)}
        >
          重新检查
        </Button>
      ) : null,
    },
  ], [retryingFailure]);

  if (dashboard.isLoading) {
    return <div className="dashboard-state"><Spin aria-label="正在加载工作台" /></div>;
  }

  if (dashboard.isError) {
    return <Alert type="error" showIcon message="工作台数据加载失败，请稍后重试" />;
  }

  const data = dashboard.data;
  if (!data) {
    return <Empty description="暂无工作台数据" />;
  }

  const statistics = [
    { title: "监控商品", value: data.monitored_products },
    { title: "24 小时补货", value: data.restocks_24h },
    { title: "当前异常", value: data.active_failures },
  ];
  const selectedSummary = data.region_summaries.find((summary) => summary.region === selectedRegion);
  const displayedProducts = selectedSummary
    ? selectedSummary.products
    : data.region_summaries.flatMap((summary) => summary.products);
  const selectedLabel = selectedSummary?.label ?? "全部站点";

  return (
    <div className="dashboard-page">
      {contextHolder}
      <Row gutter={[16, 16]}>
        {statistics.map((statistic) => (
          <Col key={statistic.title} xs={24} sm={12} xl={8}>
            <Card className="dashboard-statistic" size="small">
              <Text type="secondary">{statistic.title}</Text>
              <div className="dashboard-statistic__value">{statistic.value}</div>
            </Card>
          </Col>
        ))}
      </Row>

      <section className="dashboard-band" aria-labelledby="region-overview-heading">
        <div className="dashboard-section-heading">
          <Title id="region-overview-heading" level={4}>站点概览</Title>
          {selectedRegion !== "ALL" && (
            <Button type="link" onClick={() => setSelectedRegion("ALL")}>查看全部站点</Button>
          )}
        </div>
        <div className="dashboard-regions">
          {data.region_summaries.map((summary) => (
            <RegionCard
              key={summary.region}
              summary={summary}
              selected={selectedRegion === summary.region}
              onSelect={() => setSelectedRegion(summary.region)}
            />
          ))}
        </div>
      </section>

      <section className="dashboard-band" aria-labelledby="site-products-heading">
        <Title id="site-products-heading" level={4}>{selectedLabel}商品状态</Title>
        <Table<ProductSummary>
          columns={productColumns}
          dataSource={displayedProducts}
          rowKey="id"
          pagination={displayedProducts.length > 10 ? { pageSize: 10, showSizeChanger: false } : false}
          size="middle"
          locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无监控商品" /> }}
        />
      </section>

      <section className="dashboard-band" aria-labelledby="pending-failures-heading">
        <Title id="pending-failures-heading" level={4}>待处理异常</Title>
        <Table<FailureData>
          columns={failureColumns}
          dataSource={data.pending_failures}
          rowKey="id"
          pagination={false}
          size="small"
          locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前没有待处理异常" /> }}
        />
      </section>
    </div>
  );
}
