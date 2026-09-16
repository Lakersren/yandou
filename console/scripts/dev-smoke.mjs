import assert from "node:assert/strict";
import { createServer as createHttpServer } from "node:http";
import { once } from "node:events";
import { createServer, resolveConfig } from "vite";

// An isolated upstream verifies proxy ownership and cookie forwarding without Django or external requests.
const upstream = createHttpServer((request, response) => {
  response.setHeader("Content-Type", "application/json");
  response.setHeader("Set-Cookie", "csrftoken=smoke; Path=/");
  response.end(JSON.stringify({ path: request.url, cookie: request.headers.cookie }));
});
let vite;
try {
  upstream.listen(0, "127.0.0.1");
  await once(upstream, "listening");
  const upstreamUrl = `http://127.0.0.1:${upstream.address().port}`;
  const devConfig = await resolveConfig({}, "serve");
  assert.equal(devConfig.base, "/console/");
  assert.equal(devConfig.server.proxy["/console"], undefined);
  const proxy = {};
  for (const path of ["/api", "/admin", "/static/admin"]) {
    assert.equal(devConfig.server.proxy[path], "http://127.0.0.1:8000");
    proxy[path] = upstreamUrl;
  }
  const buildConfig = await resolveConfig({}, "build");
  assert.equal(buildConfig.base, "/static/console/");
  vite = await createServer({ server: { host: "127.0.0.1", port: 0, proxy } });
  await vite.listen();
  const origin = `http://127.0.0.1:${vite.httpServer.address().port}`;
  for (const path of ["/console/", "/console/products"]) {
    const response = await fetch(`${origin}${path}`);
    assert.equal(response.status, 200);
    const html = await response.text();
    assert.match(html, /\/console\/@vite\/client/);
    assert.match(html, /\/console\/src\/main\.tsx/);
    assert.doesNotMatch(html, /assets\/app\.js/);
  }
  const source = await fetch(`${origin}/console/src/main.tsx`);
  assert.equal(source.status, 200);
  assert.match(await source.text(), /createRoot/);
  for (const path of ["/api/console/v1/session", "/admin/login/?next=%2Fconsole%2Fproducts", "/static/admin/css/base.css"]) {
    const response = await fetch(`${origin}${path}`, { headers: { Cookie: "sessionid=smoke" } });
    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), { path, cookie: "sessionid=smoke" });
    assert.equal(response.headers.get("set-cookie"), "csrftoken=smoke; Path=/");
  }
  console.log("PASS: Vite owns /console/ and nested routes; source entry loads; API, admin and login assets proxy with cookies; production asset base is preserved.");
} finally {
  if (vite) await vite.close();
  upstream.closeAllConnections();
  await new Promise((resolve) => upstream.close(resolve));
}
