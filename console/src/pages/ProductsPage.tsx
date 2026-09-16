import { DeleteOutlined, GlobalOutlined, MoreOutlined, PlusOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Dropdown, Popconfirm, Tag, Typography, message } from "antd";
import { ProTable, type ProColumns, type ProFormInstance } from "@ant-design/pro-components";
import { useMemo, useRef, useState } from "react";

import { AddProductModal } from "../components/AddProductModal";
import { ProductDrawer } from "../components/ProductDrawer";
import { api } from "../api/client";
import type { PaginatedData, ProductData } from "../api/types";

import "./products.css";

type ProductListItem = ProductData;

interface ProductQuery {
  q?: string;
  site?: string;
  status?: string;
  page: number;
  pageSize: number;
}

const initialQuery: ProductQuery = { page: 1, pageSize: 20 };
const disabledRowStyle = { opacity: 0.58 };

const stockTags: Record<string, { color: string; label: string }> = {
  in_stock: { color: "success", label: "有货" },
  partial_stock: { color: "warning", label: "部分有货" },
  out_of_stock: { color: "default", label: "缺货" },
  discontinued: { color: "default", label: "已下架" },
  unknown: { color: "warning", label: "确认中" },
};

const siteOptions = {
  sp: { text: "Smokingpipes" },
  dp: { text: "Dreaming Pipes" },
  "4n": { text: "4Noggins" },
  np: { text: "Nova Pipes & Tobacco" },
  "70": { text: "70 Cigars" },
  tecon: { text: "Tecon" },
  ph: { text: "Peter Heinrichs" },
  pipeuncle: { text: "Pipe Uncle" },
  lifestyle: { text: "Tobacco Lifestyle" },
  ps: { text: "Pipes Space" },
  cg: { text: "C.Gars" },
  gq: { text: "GQ Tobaccos" },
  hh: { text: "Hava Havana" },
  havanahouse: { text: "Havana House" },
  jb: { text: "James Barber" },
};

const officialSiteGroups = [
  {
    label: "美站",
    sites: [
      ["Smokingpipes", "https://smokingpipes.com/"],
      ["Dreaming Pipes", "https://dreamingpipes.com/"],
      ["4Noggins", "https://www.4noggins.com/"],
      ["Nova Pipes & Tobacco", "https://novapipesandtobacco.com/"],
      ["70 Cigars", "https://70cigars.com/"],
    ],
  },
  {
    label: "德站",
    sites: [
      ["Tecon", "https://www.tecon-gmbh.de/"],
      ["Peter Heinrichs", "https://www.peterheinrichs.de/"],
    ],
  },
  {
    label: "港站",
    sites: [
      ["Pipe Uncle", "https://www.pipeuncle.com/"],
      ["Tobacco Lifestyle", "https://tobaccolifestyle.com/"],
    ],
  },
  {
    label: "新加坡站",
    sites: [["Pipes Space", "https://pipesspace.com/"]],
  },
  {
    label: "英站",
    sites: [
      ["C.Gars", "https://www.cgarsltd.co.uk/"],
      ["GQ Tobaccos", "https://www.gqtobaccos.com/"],
      ["Hava Havana", "https://www.havahavana.com/"],
      ["Havana House", "https://www.havanahouse.co.uk/"],
      ["James Barber", "https://www.smoke.co.uk/"],
    ],
  },
] as const;

const officialSiteMenuItems = officialSiteGroups.map((group) => ({
  type: "group" as const,
  key: group.label,
  label: group.label,
  children: group.sites.map(([name, url]) => ({
    key: url,
    label: <a href={url} target="_blank" rel="noreferrer">{name}</a>,
  })),
}));

const statusOptions = {
  in_stock: { text: "含有货规格" },
  out_of_stock: { text: "缺货" },
  discontinued: { text: "已下架" },
  unknown: { text: "确认中" },
};

export function productListPath(query: ProductQuery): string {
  const params = new URLSearchParams();
  if (query.q) params.set("q", query.q);
  if (query.site) params.set("site", query.site);
  if (query.status) params.set("status", query.status);
  params.set("page", String(query.page));
  params.set("page_size", String(query.pageSize));
  return `products?${params.toString()}`;
}

function formatDate(value?: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "-"
    : new Intl.DateTimeFormat("zh-CN", { dateStyle: "short", timeStyle: "short", hour12: false }).format(date);
}

function StockTag({ status, label }: { status: string; label?: string }) {
  const config = stockTags[status] ?? stockTags.unknown;
  return <Tag color={config.color}>{label || config.label}</Tag>;
}

function variantSummary(product: ProductListItem): string {
  if (!product.variants.length) return "-";
  return product.variants.map((variant) => {
    const price = variant.price ? ` ${variant.currency} ${variant.price}` : "";
    const status = stockTags[variant.status]?.label ?? stockTags.unknown.label;
    return `${variant.name}${price} · ${status}`;
  }).join("，");
}

export function ProductsPage() {
  const queryClient = useQueryClient();
  const searchForm = useRef<ProFormInstance>(undefined);
  const [query, setQuery] = useState<ProductQuery>(initialQuery);
  const [addOpen, setAddOpen] = useState(false);
  const [selectedProductId, setSelectedProductId] = useState<number | null>(null);
  const [removingProductId, setRemovingProductId] = useState<number | null>(null);
  const [messageApi, contextHolder] = message.useMessage();
  const products = useQuery({
    queryKey: ["products", query],
    queryFn: () => api.get<PaginatedData<ProductListItem>>(productListPath(query)),
  });
  const check = useMutation({ mutationFn: (id: number) => api.post<{ queued: boolean }>(`products/${id}/check`) });
  const updateEnabled = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) => api.patch<ProductListItem>(`products/${id}`, { enabled }),
  });
  const remove = useMutation({ mutationFn: (id: number) => api.delete(`products/${id}`) });

  const refreshProducts = () => {
    void queryClient.invalidateQueries({ queryKey: ["products"] });
    void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
  };

  const submitCheck = async (id: number) => {
    try {
      await check.mutateAsync(id);
      messageApi.success("已提交立即检查");
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "提交检查失败，请稍后重试");
    }
  };

  const toggleEnabled = async (product: ProductListItem) => {
    try {
      await updateEnabled.mutateAsync({ id: product.id, enabled: !product.enabled });
      refreshProducts();
      messageApi.success(product.enabled ? "已暂停监控" : "已恢复监控");
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "更新监控状态失败，请稍后重试");
    }
  };

  const confirmRemove = async (id: number) => {
    try {
      await remove.mutateAsync(id);
      refreshProducts();
      messageApi.success("已移除监控商品");
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : "移除失败，请稍后重试");
    }
  };

  const columns = useMemo<ProColumns<ProductListItem>[]>(() => [
    {
      title: "商品",
      dataIndex: "name",
      width: 280,
      ellipsis: true,
      search: false,
      render: (_, product) => (
        <div style={{ minWidth: 0 }}>
          <Button type="link" style={{ padding: 0, height: "auto", maxWidth: "100%" }} onClick={() => setSelectedProductId(product.id)}>
            <Typography.Text strong ellipsis={{ tooltip: product.name }}>{product.name}</Typography.Text>
          </Button>
          <Typography.Text type="secondary" ellipsis={{ tooltip: product.url }} style={{ display: "block", maxWidth: "100%" }}>
            {product.url}
          </Typography.Text>
        </div>
      ),
    },
    { title: "商城", dataIndex: ["site", "name"], width: 148, ellipsis: true, search: false },
    { title: "规格 / 价格", key: "variants", width: 190, ellipsis: true, search: false, render: (_, product) => <Typography.Text ellipsis={{ tooltip: variantSummary(product) }}>{variantSummary(product)}</Typography.Text> },
    { title: "库存", dataIndex: "stock_status", width: 124, search: false, render: (_dom, product) => <StockTag status={product.stock_status} label={product.stock_status_label} /> },
    { title: "最近检查", dataIndex: "last_checked_at", width: 168, search: false, render: (_dom, product) => formatDate(product.last_checked_at) },
    { title: "状态", dataIndex: "enabled", width: 96, search: false, render: (_dom, product) => <Tag color={product.enabled ? "processing" : "default"}>{product.enabled ? "监控中" : "已暂停"}</Tag> },
    {
      title: "操作",
      valueType: "option",
      width: 112,
      fixed: "right",
      render: (_, product) => (
        <>
          <Button type="link" size="small" onClick={() => setSelectedProductId(product.id)}>详情</Button>
          <Dropdown
            menu={{
              items: [
                { key: "check", label: check.isPending ? "正在提交检查" : "立即检查", disabled: check.isPending },
                { key: "toggle", label: product.enabled ? "暂停监控" : "恢复监控" },
                { type: "divider" },
                { key: "remove", danger: true, icon: <DeleteOutlined />, label: "移除" },
              ],
              onClick: ({ key }) => {
                if (key === "check") void submitCheck(product.id);
                if (key === "toggle") void toggleEnabled(product);
                if (key === "remove") setRemovingProductId(product.id);
              },
            }}
            trigger={["click"]}
          >
            <Button type="text" size="small" icon={<MoreOutlined />} aria-label="更多操作" />
          </Dropdown>
          <Popconfirm
            open={removingProductId === product.id}
            title="确认移除该商品？"
            description="移除后将停止监控，历史记录会保留。"
            okText="确认移除"
            cancelText="取消"
            okButtonProps={{ loading: remove.isPending }}
            onOpenChange={(open) => setRemovingProductId(open ? product.id : null)}
            onConfirm={async () => {
              await confirmRemove(product.id);
              setRemovingProductId(null);
            }}
          >
            <Button
              type="text"
              size="small"
              danger
              icon={<DeleteOutlined />}
              aria-label="移除"
              title="移除"
              onClick={() => setRemovingProductId(product.id)}
            />
          </Popconfirm>
        </>
      ),
    },
    { title: "名称 / URL", dataIndex: "q", hideInTable: true, fieldProps: { placeholder: "输入名称或商品链接" } },
    { title: "商城", dataIndex: "site", hideInTable: true, valueType: "select", valueEnum: siteOptions },
    { title: "库存状态", dataIndex: "status", hideInTable: true, valueType: "select", valueEnum: statusOptions },
  ], [check.isPending, remove.isPending, removingProductId, updateEnabled.isPending]);

  return (
    <div className="products-page">
      {contextHolder}
      {products.isError && <Alert type="error" showIcon message="商品列表加载失败，请稍后重试" style={{ marginBottom: 16 }} />}
      <ProTable<ProductListItem>
        formRef={searchForm}
        rowKey="id"
        columns={columns}
        dataSource={products.data?.items ?? []}
        loading={products.isLoading || products.isFetching}
        search={{ labelWidth: "auto", defaultColsNumber: 3 }}
        form={{ ignoreRules: false }}
        pagination={{
          current: query.page,
          pageSize: query.pageSize,
          total: products.data?.total ?? 0,
          showSizeChanger: true,
          onChange: (page, pageSize) => setQuery((current) => ({ ...current, page, pageSize })),
        }}
        options={false}
        scroll={{ x: 1120 }}
        rowClassName={(product) => product.enabled ? "" : "products-page__row--disabled"}
        onRow={(product) => product.enabled ? {} : { style: disabledRowStyle }}
        toolBarRender={() => [
          <Dropdown key="official-sites" menu={{ items: officialSiteMenuItems }} trigger={["click"]}>
            <Button icon={<GlobalOutlined />}>商城官网</Button>
          </Dropdown>,
          <Button key="add" type="primary" icon={<PlusOutlined />} onClick={() => setAddOpen(true)}>添加监控商品</Button>,
        ]}
        onSubmit={(values) => setQuery({
          q: values.q?.trim() || undefined,
          site: values.site || undefined,
          status: values.status || undefined,
          page: 1,
          pageSize: query.pageSize,
        })}
        onReset={() => {
          setQuery({ ...initialQuery, pageSize: query.pageSize });
        }}
      />
      <AddProductModal
        open={addOpen}
        onClose={() => setAddOpen(false)}
        onCreated={(product, outcome) => {
          if (outcome === "existing") {
            setSelectedProductId(product.id);
          } else {
            searchForm.current?.resetFields();
            setQuery((current) => ({ ...initialQuery, pageSize: current.pageSize }));
            refreshProducts();
          }
        }}
      />
      <ProductDrawer productId={selectedProductId} onClose={() => setSelectedProductId(null)} />
    </div>
  );
}
