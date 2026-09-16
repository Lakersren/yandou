import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { ConsoleLayout } from "./layout/ConsoleLayout";
import { ChannelsPage } from "./pages/ChannelsPage";
import { DashboardPage } from "./pages/DashboardPage";
import { EventsPage } from "./pages/EventsPage";
import { FailuresPage } from "./pages/FailuresPage";
import { ProductsPage } from "./pages/ProductsPage";

export function ConsoleRoutes() {
  return (
    <Routes>
      <Route path="/" element={<ConsoleLayout><DashboardPage /></ConsoleLayout>} />
      <Route path="/products" element={<ConsoleLayout><ProductsPage /></ConsoleLayout>} />
      <Route path="/events" element={<ConsoleLayout><EventsPage /></ConsoleLayout>} />
      <Route path="/failures" element={<ConsoleLayout><FailuresPage /></ConsoleLayout>} />
      <Route path="/feishu" element={<ConsoleLayout><ChannelsPage /></ConsoleLayout>} />
      <Route path="/dingtalk" element={<Navigate to="/feishu" replace />} />
    </Routes>
  );
}

export function App() {
  const [queryClient] = useState(() => new QueryClient());

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter
        basename="/console"
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <ConsoleRoutes />
      </BrowserRouter>
    </QueryClientProvider>
  );
}
