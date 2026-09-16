import {
  DashboardOutlined,
  MessageOutlined,
  NotificationOutlined,
  ShoppingOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import { queryOptions, useQuery } from "@tanstack/react-query";
import { Badge, ConfigProvider, Dropdown, Spin, theme } from "antd";
import { ProConfigProvider, ProLayout, type MenuDataItem } from "@ant-design/pro-components";
import type { ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { api } from "../api/client";
import type { SessionData } from "../api/types";
import "./layout.css";

const menuRoutes: MenuDataItem[] = [
  { path: "/", name: "工作台", icon: <DashboardOutlined /> },
  { path: "/products", name: "商品监控", icon: <ShoppingOutlined /> },
  { path: "/events", name: "补货记录", icon: <NotificationOutlined /> },
  { path: "/failures", name: "异常记录", icon: <WarningOutlined /> },
  { path: "/feishu", name: "飞书群", icon: <MessageOutlined /> },
];

interface ConsoleLayoutProps {
  children: ReactNode;
}

export const sessionQueryOptions = queryOptions({
  queryKey: ["session"],
  queryFn: () => api.get<SessionData>("session"),
  refetchInterval: 60_000,
});

export function ConsoleLayout({ children }: ConsoleLayoutProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const session = useQuery(sessionQueryOptions);

  const schedulerStatus = session.isError
    ? "unknown"
    : session.data?.scheduler === "healthy"
      ? "healthy"
      : "unhealthy";
  const schedulerText = {
    healthy: "调度正常",
    unhealthy: "调度异常",
    unknown: "服务状态未知",
  }[schedulerStatus];

  const logout = async () => {
    const result = await api.post<{ redirect: string }>("logout");
    window.location.assign(result.redirect);
  };

  return (
    <ProLayout
      className="console-layout"
      title="补货监控"
      layout="mix"
      fixedHeader
      fixSiderbar
      siderWidth={208}
      breakpoint="lg"
      route={{ path: "/", routes: menuRoutes }}
      location={{ pathname: location.pathname }}
      menuItemRender={(item, dom) => (
        <a
          href={item.path}
          onClick={(event) => {
            event.preventDefault();
            if (item.path) {
              navigate(item.path);
            }
          }}
        >
          {dom}
        </a>
      )}
      rightContentRender={() => (
        <div className="console-layout__header-actions">
          {session.isLoading ? (
            <Spin size="small" aria-label="正在加载服务状态" />
          ) : (
            <Badge
              status={schedulerStatus === "healthy" ? "success" : schedulerStatus === "unhealthy" ? "error" : "default"}
              text={schedulerText}
            />
          )}
          <Dropdown
            menu={{
              items: [{ key: "logout", label: "退出登录" }],
              onClick: () => void logout(),
            }}
          >
            <a className="console-layout__user" href="/admin/login/" onClick={(event) => event.preventDefault()}>
              {session.data?.user?.username ?? "当前用户"}
            </a>
          </Dropdown>
        </div>
      )}
    >
      <ProConfigProvider dark={false}>
        <ConfigProvider
          theme={{
            inherit: false,
            algorithm: theme.defaultAlgorithm,
            token: {
              colorPrimary: "#1677ff",
              colorSuccess: "#52c41a",
              colorWarning: "#faad14",
              colorError: "#ff4d4f",
              colorBgLayout: "#f0f2f5",
              colorBgContainer: "#ffffff",
              colorText: "rgba(0, 0, 0, 0.88)",
              colorTextSecondary: "rgba(0, 0, 0, 0.45)",
              colorBorder: "#f0f0f0",
            },
          }}
        >
          <main className="console-layout__content">{children}</main>
        </ConfigProvider>
      </ProConfigProvider>
    </ProLayout>
  );
}
