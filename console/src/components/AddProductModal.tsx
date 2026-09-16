import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button, Form, Input, Modal, message } from "antd";

import { ApiError, api } from "../api/client";
import type { ProductData } from "../api/types";

type ProductOutcome = "created" | "existing" | "restored";

interface AddProductResponse {
  product: ProductData;
  outcome: ProductOutcome;
}

interface AddProductModalProps {
  open: boolean;
  onClose: () => void;
  onCreated: (product: ProductData, outcome: ProductOutcome) => void;
}

export function AddProductModal({ open, onClose, onCreated }: AddProductModalProps) {
  const [form] = Form.useForm<{ url: string }>();
  const queryClient = useQueryClient();
  const [messageApi, contextHolder] = message.useMessage();
  const addProduct = useMutation({
    mutationFn: (url: string) => api.post<AddProductResponse>("products", { url }),
  });

  const close = () => {
    if (addProduct.isPending) return;
    form.resetFields();
    onClose();
  };

  const submit = async ({ url }: { url: string }) => {
    try {
      const result = await addProduct.mutateAsync(url.trim());
      void queryClient.invalidateQueries({ queryKey: ["products"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      void queryClient.invalidateQueries({ queryKey: ["product"] });
      messageApi.success(result.outcome === "existing" ? "已打开已有监控商品" : "已开始监控商品");
      form.resetFields();
      onCreated(result.product, result.outcome);
      onClose();
    } catch (error) {
      if (error instanceof ApiError && error.fields?.url) {
        const message = Array.isArray(error.fields.url) ? error.fields.url[0] : error.fields.url;
        form.setFields([{ name: "url", errors: [message] }]);
      } else {
        messageApi.error(error instanceof Error ? error.message : "添加失败，请稍后重试");
      }
    }
  };

  return (
    <Modal title="添加监控商品" open={open} onCancel={close} footer={null} destroyOnHidden>
      {contextHolder}
      <Form form={form} layout="vertical" onFinish={submit} requiredMark={false}>
        <Form.Item
          label="商品 URL"
          name="url"
          rules={[
            { required: true, message: "请输入商品 URL" },
            { type: "url", message: "请输入有效的商品 URL" },
          ]}
        >
          <Input autoFocus placeholder="粘贴支持商城的商品链接" inputMode="url" />
        </Form.Item>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <Button onClick={close} disabled={addProduct.isPending}>取消</Button>
          <Button type="primary" htmlType="submit" loading={addProduct.isPending} disabled={addProduct.isPending}>开始监控</Button>
        </div>
      </Form>
    </Modal>
  );
}
