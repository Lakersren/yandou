import { ConfigProvider, theme } from "antd";
import "antd/dist/reset.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./app";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ConfigProvider
      theme={{
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
        components: {
          Layout: { siderBg: "#001529" },
        },
      }}
    >
      <App />
    </ConfigProvider>
  </StrictMode>,
);
